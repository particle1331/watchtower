"""Agent-facing inspection helpers: repo structure, search, file content.

These produce plain stdout (JSON or text) suitable for an AI agent calling
`wt map`, `wt find`, or `wt cat` via bash. Output is derived directly from
`.qmd` source files in the content dirs — qmd is plain markdown, so the
source IS the knowledge base.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

NOTES_DIR = Path("notes")
ESSAYS_DIR = Path("essays")
LEARNING_DIR = Path("learning")

CONTENT_DIRS: tuple[Path, ...] = (NOTES_DIR, ESSAYS_DIR, LEARNING_DIR)


def list_qmd(src_dir: Path) -> list[str]:
    if not src_dir.exists():
        return []
    return sorted(
        str(p.relative_to("."))
        for p in src_dir.rglob("*.qmd")
        if p.name != "index.qmd"
    )


def list_projects() -> list[dict]:
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []
    out: list[dict] = []
    for d in sorted(projects_dir.iterdir()):
        if d.is_dir() and (d / "pyproject.toml").exists():
            out.append(
                {
                    "name": d.name,
                    "path": str(d),
                    "has_agents_md": (d / "AGENTS.md").exists(),
                }
            )
    return out


def repo_map() -> dict:
    return {
        "notes": list_qmd(NOTES_DIR),
        "essays": list_qmd(ESSAYS_DIR),
        "learning": list_qmd(LEARNING_DIR),
        "projects": list_projects(),
        "portfolio": "portfolio.qmd",
        "rules": "AGENTS.md",
    }


def repo_map_json() -> str:
    return json.dumps(repo_map(), indent=2)


def find_in_src(query: str) -> str:
    """Search across .qmd source files in all content dirs."""
    result = subprocess.run(
        ["rg", "-i", "-n", query, *[str(d) for d in CONTENT_DIRS]],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def cat_qmd(name: str) -> str:
    """Read a single .qmd source file by stem name."""
    for base in CONTENT_DIRS:
        for p in base.rglob(f"{name}.qmd"):
            if p.exists():
                return p.read_text()
    raise FileNotFoundError(f"no qmd named '{name}'. try `wt ls notes|essays|learning`.")