"""File-oriented builtin tools.

This module combines the read, write, edit, glob, grep, and directory-listing
tools while keeping their individual schemas and result contracts intact.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from agent_harness.tools.base import (
    FileDiff,
    Tool,
    ToolConfirmation,
    ToolInvocation,
    ToolKind,
    ToolResult,
)


class PathOutsideWorkspaceError(ValueError):
    """Raised when a file operation resolves outside its working directory."""


def _resolve_path(cwd: Path, path_str: str) -> Path:
    """Resolve a user path and keep it inside the configured workspace."""
    workspace = cwd.resolve()
    path = Path(path_str)
    candidate = path if path.is_absolute() else workspace / path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(workspace):
        raise PathOutsideWorkspaceError(
            f"Path escapes working directory: {path_str} (workspace: {workspace})"
        )
    return resolved


def _is_binary_file(path: Path, sample_size: int = 8192) -> bool:
    try:
        with path.open("rb") as file:
            chunk = file.read(sample_size)
        return b"\x00" in chunk
    except Exception:
        return False


class ReadFileParams(BaseModel):
    path: str = Field(..., description="Path to the file to read (relative to cwd or absolute)")
    offset: int = Field(1, ge=1, description="Line number to start from (1-based)")
    limit: int | None = Field(None, ge=1, description="Maximum number of lines to read")


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a text file. Returns content with line numbers. "
        "For large files, use offset and limit to read specific portions."
    )
    kind = ToolKind.READ
    schema = ReadFileParams

    MAX_FILE_SIZE = 10 * 1024 * 1024

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ReadFileParams(**invocation.params)
        try:
            path = _resolve_path(invocation.cwd, params.path)
        except PathOutsideWorkspaceError as exc:
            return ToolResult.error_result(str(exc))

        if not path.exists():
            return ToolResult.error_result(f"File not found: {path}")
        if not path.is_file():
            return ToolResult.error_result(f"Not a file: {path}")
        if path.stat().st_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(f"File too large: {path.stat().st_size} bytes")
        if _is_binary_file(path):
            return ToolResult.error_result(f"Cannot read binary file: {path.name}")

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        lines = content.splitlines()
        total = len(lines)
        start = max(0, params.offset - 1)
        end = min(start + params.limit, total) if params.limit else total

        formatted = [
            f"{i:6}|{line}"
            for i, line in enumerate(lines[start:end], start=start + 1)
        ]
        output = "\n".join(formatted) if formatted else "File is empty."

        header = ""
        if start > 0 or end < total:
            header = f"Showing lines {start + 1}-{end} of {total}\n\n"

        return ToolResult.success_result(
            output=header + output,
            metadata={
                "path": str(path),
                "total_lines": total,
                "shown_start": start + 1,
                "shown_end": end,
            },
        )


class WriteFileParams(BaseModel):
    path: str = Field(..., description="Path to the file to write")
    content: str = Field(..., description="Content to write to the file")
    create_directories: bool = Field(True, description="Create parent directories if needed")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create or overwrite a file with the given content."
    kind = ToolKind.WRITE
    schema = WriteFileParams

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        params = WriteFileParams(**invocation.params)
        path = _resolve_path(invocation.cwd, params.path)
        old_content = path.read_text(encoding="utf-8") if path.exists() else ""
        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"{'Overwrite' if path.exists() else 'Create'} file: {path}",
            diff=FileDiff(
                path=path,
                old_content=old_content,
                new_content=params.content,
                is_new_file=not path.exists(),
            ),
            affected_paths=[path],
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WriteFileParams(**invocation.params)
        try:
            path = _resolve_path(invocation.cwd, params.path)
        except PathOutsideWorkspaceError as exc:
            return ToolResult.error_result(str(exc))

        old_content = ""
        is_new = not path.exists()

        if not is_new:
            old_content = path.read_text(encoding="utf-8")

        if params.create_directories:
            path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(params.content, encoding="utf-8")
        line_count = len(params.content.splitlines())

        return ToolResult.success_result(
            f"{'Created' if is_new else 'Wrote'} {path} ({line_count} lines)",
            diff=FileDiff(
                path=path,
                old_content=old_content,
                new_content=params.content,
                is_new_file=is_new,
            ),
            metadata={"path": str(path), "is_new_file": is_new, "lines": line_count},
        )


class EditParams(BaseModel):
    path: str = Field(..., description="Path to the file to edit")
    old_string: str = Field("", description="Exact text to find and replace. Empty for new files.")
    new_string: str = Field(..., description="Text to replace old_string with. Can be empty to delete.")
    replace_all: bool = Field(False, description="Replace all occurrences (default: false)")


class EditTool(Tool):
    name = "edit"
    description = (
        "Edit a file by replacing text. old_string must match exactly "
        "(including whitespace) and be unique unless replace_all is true."
    )
    kind = ToolKind.WRITE
    schema = EditParams

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        params = EditParams(**invocation.params)
        path = _resolve_path(invocation.cwd, params.path)
        is_new = not path.exists()
        old_content = "" if is_new else path.read_text(encoding="utf-8")

        if is_new:
            new_content = params.new_string
        elif params.replace_all:
            new_content = old_content.replace(params.old_string, params.new_string)
        else:
            new_content = old_content.replace(params.old_string, params.new_string, 1)

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"{'Create' if is_new else 'Edit'} file: {path}",
            diff=FileDiff(
                path=path,
                old_content=old_content,
                new_content=new_content,
                is_new_file=is_new,
            ),
            affected_paths=[path],
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = EditParams(**invocation.params)
        try:
            path = _resolve_path(invocation.cwd, params.path)
        except PathOutsideWorkspaceError as exc:
            return ToolResult.error_result(str(exc))

        if not path.exists():
            if params.old_string:
                return ToolResult.error_result(
                    f"File does not exist: {path}. Use empty old_string for new files."
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(params.new_string, encoding="utf-8")
            lines = len(params.new_string.splitlines())
            return ToolResult.success_result(
                f"Created {path} ({lines} lines)",
                diff=FileDiff(
                    path=path,
                    old_content="",
                    new_content=params.new_string,
                    is_new_file=True,
                ),
                metadata={"path": str(path), "is_new_file": True, "lines": lines},
            )

        old_content = path.read_text(encoding="utf-8")

        if not params.old_string:
            return ToolResult.error_result(
                "old_string is empty but file exists. Use write_file to overwrite."
            )

        count = old_content.count(params.old_string)
        if count == 0:
            return ToolResult.error_result(f"old_string not found in {path}.")
        if count > 1 and not params.replace_all:
            return ToolResult.error_result(
                f"old_string found {count} times. Provide more context or set replace_all=true."
            )

        if params.replace_all:
            new_content = old_content.replace(params.old_string, params.new_string)
            replace_count = count
        else:
            new_content = old_content.replace(params.old_string, params.new_string, 1)
            replace_count = 1

        if new_content == old_content:
            return ToolResult.error_result("No change — old_string equals new_string.")

        path.write_text(new_content, encoding="utf-8")
        line_diff = len(new_content.splitlines()) - len(old_content.splitlines())
        diff_msg = (
            f" (+{line_diff} lines)"
            if line_diff > 0
            else (f" ({line_diff} lines)" if line_diff < 0 else "")
        )

        return ToolResult.success_result(
            f"Edited {path}: replaced {replace_count} occurrence(s){diff_msg}",
            diff=FileDiff(path=path, old_content=old_content, new_content=new_content),
            metadata={"path": str(path), "replaced_count": replace_count, "line_diff": line_diff},
        )


class GlobParams(BaseModel):
    pattern: str = Field(..., description="Glob pattern to match (e.g. '**/*.py')")
    path: str = Field(".", description="Directory to search in")


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern. Returns matching file paths."
    kind = ToolKind.READ
    schema = GlobParams

    MAX_RESULTS = 500

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GlobParams(**invocation.params)
        try:
            path = _resolve_path(invocation.cwd, params.path)
        except PathOutsideWorkspaceError as exc:
            return ToolResult.error_result(str(exc))

        if not path.exists():
            return ToolResult.error_result(f"Directory not found: {path}")
        if not path.is_dir():
            return ToolResult.error_result(f"Not a directory: {path}")

        results = sorted(path.rglob(params.pattern))
        results = [result for result in results if result.resolve().is_relative_to(invocation.cwd.resolve())]
        total = len(results)
        results = results[: self.MAX_RESULTS]

        lines = []
        for result in results:
            rel = result.relative_to(invocation.cwd) if result.is_relative_to(invocation.cwd) else result
            suffix = "/" if result.is_dir() else ""
            lines.append(f"{rel}{suffix}")

        output = "\n".join(lines) if lines else f"No files matching '{params.pattern}'."
        truncated = total > self.MAX_RESULTS

        if truncated:
            output += f"\n... ({total} total, showing first {self.MAX_RESULTS})"

        return ToolResult.success_result(
            output=output,
            truncated=truncated,
            metadata={"matches": min(total, self.MAX_RESULTS), "total": total},
        )


class GrepParams(BaseModel):
    pattern: str = Field(..., description="Regex pattern to search for")
    path: str = Field(".", description="File or directory to search in")
    include: str | None = Field(None, description="Glob pattern to filter files (e.g. '*.py')")
    case_insensitive: bool = Field(False, description="Case-insensitive search")


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents using regex. Returns matching lines with file paths and line numbers."
    kind = ToolKind.READ
    schema = GrepParams

    MAX_MATCHES = 200

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GrepParams(**invocation.params)
        try:
            path = _resolve_path(invocation.cwd, params.path)
        except PathOutsideWorkspaceError as exc:
            return ToolResult.error_result(str(exc))

        flags = re.IGNORECASE if params.case_insensitive else 0
        try:
            regex = re.compile(params.pattern, flags)
        except re.error as exc:
            return ToolResult.error_result(f"Invalid regex: {exc}")

        matches: list[str] = []
        files_searched = 0

        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = sorted(path.rglob(params.include or "*"))
            files = [file for file in files if file.is_file()]
        else:
            return ToolResult.error_result(f"Path not found: {path}")

        for file in files:
            if not file.resolve().is_relative_to(invocation.cwd.resolve()):
                continue
            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            files_searched += 1
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    rel = file.relative_to(invocation.cwd) if file.is_relative_to(invocation.cwd) else file
                    matches.append(f"{rel}:{i}: {line.rstrip()}")
                    if len(matches) >= self.MAX_MATCHES:
                        break
            if len(matches) >= self.MAX_MATCHES:
                break

        if not matches:
            return ToolResult.success_result(
                f"No matches for '{params.pattern}' in {files_searched} files.",
                metadata={"matches": 0, "files_searched": files_searched},
            )

        output = "\n".join(matches)
        truncated = len(matches) >= self.MAX_MATCHES

        if truncated:
            output += f"\n... (showing first {self.MAX_MATCHES} matches)"

        return ToolResult.success_result(
            output=output,
            truncated=truncated,
            metadata={"matches": len(matches), "files_searched": files_searched},
        )


class ListDirParams(BaseModel):
    path: str = Field(".", description="Directory path to list (relative to cwd or absolute)")
    include_hidden: bool = Field(False, description="Include hidden files/directories")


class ListDirTool(Tool):
    name = "list_dir"
    description = "List the contents of a directory. Returns file/directory names with type indicators."
    kind = ToolKind.READ
    schema = ListDirParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirParams(**invocation.params)
        try:
            path = _resolve_path(invocation.cwd, params.path)
        except PathOutsideWorkspaceError as exc:
            return ToolResult.error_result(str(exc))

        if not path.exists():
            return ToolResult.error_result(f"Directory not found: {path}")
        if not path.is_dir():
            return ToolResult.error_result(f"Not a directory: {path}")

        entries = sorted(path.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower()))
        if not params.include_hidden:
            entries = [entry for entry in entries if not entry.name.startswith(".")]

        lines = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"  {entry.name}{suffix}")

        output = "\n".join(lines) if lines else "(empty directory)"

        return ToolResult.success_result(
            output=output,
            metadata={"path": str(path), "entries": len(entries)},
        )
