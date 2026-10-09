"""Catalog-backed navigation and source search for ``wt``."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat

from . import knowledge

TEXT_SUFFIXES = {".md", ".qmd", ".py", ".yaml", ".yml", ".toml"}
SKIP_DIRS = {".git", ".tmp", ".ruff_cache", ".pytest_cache", "__pycache__", "pdf", "artifacts"}


def list_ipynb(src_dir: Path) -> list[str]:
    """List registered notebooks in a tier."""
    return sorted(
        str(a["path"])
        for a in knowledge.load_catalog()
        if a.get("kind") in {"post", "chapter"}
        and Path(str(a.get("path"))).is_relative_to(src_dir)
        and Path(str(a.get("path"))).suffix == ".ipynb"
    )


def list_projects() -> list[dict]:
    return [
        {"name": Path(str(a["path"])).name, "path": a["path"], "has_agents_md": (Path(str(a["path"])) / "AGENTS.md").exists()}
        for a in knowledge.load_catalog() if a.get("kind") == "project"
    ]


def list_tier(tier: str) -> list[str]:
    kinds = {"posts": "post", "courses": "course", "projects": "project", "portfolio": "portfolio", "personal": "personal", "gallery": "gallery"}
    if tier not in kinds:
        raise ValueError(f"unknown tier: {tier}. try posts|courses|projects|portfolio")
    artifacts = knowledge.load_catalog()
    if tier == "courses":
        lines: list[str] = []
        for course in artifacts:
            if course.get("kind") != "course":
                continue
            lines.append(str(course["path"]))
            lines.append(str(Path(str(course["path"])) / "index.ipynb"))
            lines.extend(str(a["path"]) for a in artifacts if a.get("kind") == "chapter" and a.get("parent") == course.get("id"))
        return lines
    return [str(a["path"]) for a in artifacts if a.get("kind") == kinds[tier]]


def repo_map() -> dict:
    artifacts = knowledge.load_catalog()
    courses: list[dict] = []
    for course in artifacts:
        if course.get("kind") != "course":
            continue
        children = [a for a in artifacts if a.get("kind") == "chapter" and a.get("parent") == course.get("id")]
        overview = next((a["path"] for a in children if Path(str(a["path"])).stem.endswith("overview")), None)
        courses.append({
            "id": course["id"], "path": course["path"],
            "home": str(Path(str(course["path"])) / "index.ipynb"),
            "overview": overview,
            "chapters": [a["path"] for a in children if a["path"] != overview],
        })
    return {
        "catalog": "backend/data/catalog.yaml" if Path("backend/data/catalog.yaml").exists() else str(knowledge.CATALOG_PATH),
        "posts": [a for a in artifacts if a.get("kind") == "post"],
        "courses": courses,
        "portfolio": [a for a in artifacts if a.get("kind") == "portfolio"],
        "projects": [a for a in artifacts if a.get("kind") == "project"],
        "personal": [a for a in artifacts if a.get("kind") in {"personal", "gallery"}] if Path("backend/data/catalog.yaml").exists() else "nb/photos/photos.ipynb", "rules": "AGENTS.md",
    }


def archive_map() -> dict:
    root = knowledge.ARCHIVE_PATH
    return {
        "archive": str(root),
        "posts": sorted(str(p) for p in (root / "nb/posts").glob("*.ipynb")),
        "courses": sorted(str(p) for p in (root / "nb/courses").glob("*/*.ipynb")),
        "portfolio": sorted(str(p) for p in (root / "nb/portfolio").glob("*.qmd")),
        "projects": sorted(str(p) for p in (root / "projects").iterdir() if p.is_dir()) if (root / "projects").exists() else [],
    }


def repo_map_json(*, archive: bool = False) -> str:
    return json.dumps(archive_map() if archive else repo_map(), indent=2, ensure_ascii=False)


def _sources_for(artifact: dict) -> list[Path]:
    path = Path(str(artifact["path"]))
    if artifact.get("kind") == "course":
        return [p for p in (knowledge.course_file(artifact), path / "index.ipynb") if p.exists()]
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    return sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix in TEXT_SUFFIXES | {".ipynb"}
        and not any(part in SKIP_DIRS for part in p.parts)
    )


def _matching_lines(path: Path, query: str) -> list[str]:
    if path.suffix == ".ipynb":
        try:
            notebook = nbformat.read(path, as_version=nbformat.NO_CONVERT)
        except (OSError, ValueError):
            return []
        matches: list[str] = []
        for index, cell in enumerate(notebook.get("cells", [])):
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)
            for line in source.splitlines():
                if query in line.lower():
                    matches.append(f"{path} [cell {index}]: {line}")
        return matches
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return [f"{path}:{index}: {line}" for index, line in enumerate(lines, 1) if query in line.lower()]


def find_in_src(query: str, *, archive: bool = False) -> str:
    if archive:
        root = knowledge.ARCHIVE_PATH
        paths = sorted(
            p for p in root.rglob("*")
            if p.is_file() and p.suffix in TEXT_SUFFIXES | {".ipynb"}
            and not any(part in SKIP_DIRS for part in p.relative_to(root).parts)
        ) if root.exists() else []
    else:
        paths = sorted({p for artifact in knowledge.load_catalog() for p in _sources_for(artifact)})
    needle = query.lower()
    return "\n".join(match for path in paths for match in _matching_lines(path, needle))


def resolve_ipynb(name: str) -> Path:
    """Resolve a registered notebook ID or a direct notebook path."""
    artifact = knowledge.get_artifact(name)
    if artifact is not None:
        path = Path(str(artifact["path"]))
        if artifact.get("kind") == "course":
            path = path / "index.ipynb"
        if path.suffix == ".ipynb" and path.exists():
            return path.resolve()
    path = Path(name)
    if path.suffix != ".ipynb":
        path = path.with_suffix(".ipynb")
    if path.exists():
        return path.resolve()
    active = Path("content/notebooks") if Path("backend/data/catalog.yaml").exists() else Path("nb")
    if Path(name).parts[:1] in {("posts",), ("courses",), ("personal",), ("portfolio",)}:
        short = active / path
        if short.exists():
            return short.resolve()
    matches = [Path(str(a["path"])) for a in knowledge.load_catalog() if Path(str(a.get("path", ""))).stem == name]
    if len(matches) == 1 and matches[0].suffix == ".ipynb":
        return matches[0].resolve()
    # A bare stem remains a convenient direct read for a notebook that has not
    # yet been registered; discovery commands still use only the catalog.
    for base in (active / "posts", active / "courses", active / "portfolio", active / "personal"):
        for candidate in sorted(base.rglob(f"{name}.ipynb")):
            if ".ipynb_checkpoints" not in candidate.parts:
                return candidate.resolve()
    raise FileNotFoundError(f"no registered notebook named '{name}'. try `wt map`.")


from .services.notebooks import managed  # noqa: E402

for _operation in ("list_ipynb", "list_projects", "list_tier", "repo_map", "find_in_src", "resolve_ipynb"):
    globals()[_operation] = managed(globals()[_operation])
