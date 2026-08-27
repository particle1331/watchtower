"""Read-only Git history retrieval with revision-bound evidence records."""

import re
import subprocess
from pathlib import Path

from change_planner.schemas import FixtureSource


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _symbols(patch: str) -> list[str]:
    names = {
        match.group(1)
        for match in re.finditer(r"^[ +]\s*(?:async\s+)?def\s+([A-Za-z_]\w*)", patch, re.MULTILINE)
    }
    return sorted(names)


def ingest_git_history(
    root: str | Path,
    *,
    repository: str,
    revision: str = "HEAD",
    paths: list[str] | None = None,
    max_commits: int = 20,
) -> list[FixtureSource]:
    """Return commit patches as searchable Git evidence without changing Git state."""

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)
    command = ["rev-list", f"--max-count={max_commits}", revision]
    if paths:
        command.extend(["--", *paths])
    commits = [line for line in _git(root_path, *command).splitlines() if line]
    rows: list[FixtureSource] = []
    for commit in commits:
        metadata = _git(root_path, "show", "-s", "--format=%H%x1f%aI%x1f%s", commit)
        fields = metadata.split("\x1f", maxsplit=2)
        sha = fields[0] if fields else ""
        authored_at = fields[1] if len(fields) > 1 else ""
        subject = fields[2] if len(fields) > 2 else ""
        if not sha:
            continue
        touched = [
            line
            for line in _git(root_path, "show", "--format=", "--name-only", commit).splitlines()
            if line
        ]
        patch = _git(root_path, "show", "--format=fuller", "--no-ext-diff", "--unified=3", commit)
        rows.append(
            FixtureSource(
                id=f"{repository}:git:{sha}",
                repository=repository,
                revision=revision,
                source_kind="git",
                path=f"git/{sha}.patch",
                text=patch,
                tags=["git", authored_at, subject, *touched],
                symbols=_symbols(patch),
                related_sources=touched,
            )
        )
    return rows
