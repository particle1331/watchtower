"""Deterministic Python-first repository ingestion for local change planning."""

import ast
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from change_planner.history import ingest_git_history
from change_planner.retrieval import FixtureCatalog
from change_planner.schemas import FixtureSource, RepositorySnapshot, SourceKind

DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "_site",
        "build",
        "dist",
        "node_modules",
    }
)
CODE_SUFFIXES = frozenset({".go", ".java", ".js", ".jsx", ".py", ".rs", ".ts", ".tsx"})
CONFIG_NAMES = frozenset(
    {
        "Dockerfile",
        "Makefile",
        "Pipfile",
        "pyproject.toml",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
    }
)
CONFIG_SUFFIXES = frozenset({".cfg", ".ini", ".json", ".toml", ".yaml", ".yml"})
DOC_SUFFIXES = frozenset({".md", ".mdx", ".rst", ".txt"})


@dataclass(frozen=True)
class IndexedRepository:
    """A searchable source catalog plus the identity of the indexed snapshot."""

    root: Path
    catalog: FixtureCatalog
    snapshot: RepositorySnapshot


def _revision(root: Path, supplied: str | None) -> str:
    if supplied:
        return supplied
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "working-tree"


def _source_kind(relative_path: Path) -> SourceKind:
    name = relative_path.name
    if name.startswith("test_") or name.endswith("_test.py") or "tests" in relative_path.parts:
        return "test"
    if name in CONFIG_NAMES or relative_path.suffix.lower() in CONFIG_SUFFIXES:
        return "config"
    if relative_path.suffix.lower() in DOC_SUFFIXES or "docs" in relative_path.parts:
        return "docs"
    return "code"


def _python_symbols(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    rows = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    }
    return sorted(rows)


def _tags(relative_path: Path, kind: SourceKind) -> list[str]:
    tags = [kind, *relative_path.parts[:-1]]
    if relative_path.suffix:
        tags.append(relative_path.suffix.removeprefix("."))
    return sorted(set(tags))


def _files(root: Path, ignored: frozenset[str]) -> list[Path]:
    rows: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in ignored for part in relative.parts[:-1]):
            continue
        if any(part.startswith(".") for part in relative.parts[:-1]):
            continue
        if path.suffix.lower() in CODE_SUFFIXES | CONFIG_SUFFIXES | DOC_SUFFIXES or path.name in CONFIG_NAMES:
            rows.append(path)
    return rows


def ingest_repository(
    root: str | Path,
    *,
    repository: str | None = None,
    revision: str | None = None,
    ignored_directories: frozenset[str] = DEFAULT_IGNORED_DIRECTORIES,
    include_history: bool = False,
    max_history_commits: int = 20,
) -> IndexedRepository:
    """Index supported local files without modifying the repository.

    Python files receive AST-derived symbol names. Test-to-code and source
    relationships are inferred from symbol/path mentions and remain candidate
    relationships until a later verification step observes behavior.
    """

    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)
    repo = repository or root_path.name
    commit = _revision(root_path, revision)
    source_rows: list[FixtureSource] = []
    for path in _files(root_path, ignored_directories):
        relative = path.relative_to(root_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        kind = _source_kind(relative)
        source_rows.append(
            FixtureSource(
                id=f"{repo}:{relative.as_posix()}",
                repository=repo,
                revision=commit,
                source_kind=kind,
                path=relative.as_posix(),
                text=text,
                tags=_tags(relative, kind),
                symbols=_python_symbols(text) if path.suffix.lower() == ".py" else [],
            )
        )

    if include_history:
        source_rows.extend(
            ingest_git_history(
                root_path,
                repository=repo,
                revision=commit,
                max_commits=max_history_commits,
            )
        )

    tests = [source for source in source_rows if source.source_kind == "test"]
    updated: list[FixtureSource] = []
    source_by_path = {source.path: source.id for source in source_rows}
    for source in source_rows:
        related_tests = [
            test.id
            for test in tests
            if test.id != source.id and any(symbol in test.text for symbol in source.symbols)
        ]
        related_sources = [
            candidate.id
            for candidate in source_rows
            if candidate.id != source.id
            and (
                any(symbol in source.text for symbol in candidate.symbols)
                or Path(candidate.path).stem in source.text
            )
        ]
        related_sources.extend(
            source_by_path[related]
            for related in source.related_sources
            if related in source_by_path and source_by_path[related] not in related_sources
        )
        updated.append(
            source.model_copy(
                update={
                    "related_tests": sorted(related_tests),
                    "related_sources": sorted(related_sources),
                }
            )
        )

    fingerprint = hashlib.sha256()
    fingerprint.update(repo.encode())
    fingerprint.update(commit.encode())
    for source in updated:
        fingerprint.update(source.path.encode())
        fingerprint.update(source.text.encode())
    digest = fingerprint.hexdigest()
    snapshot = RepositorySnapshot(
        repository=repo,
        revision=commit,
        index_id=f"sha256:{digest[:16]}",
        source_fingerprint=f"sha256:{digest}",
    )
    return IndexedRepository(root=root_path, catalog=FixtureCatalog(updated), snapshot=snapshot)
