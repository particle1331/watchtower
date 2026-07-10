"""Agent-facing inspection helpers: repo structure, search, mirror content.

These produce plain stdout (JSON or text) suitable for an AI agent calling
`wt map`, `wt find`, or `wt cat` via bash. Output is always derived from
mirror files, never notebooks — preserves the knowledge-base contract.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def list_mirrors(mirror_dir: Path) -> list[str]:
    if not mirror_dir.exists():
        return []
    return sorted(str(p.relative_to(".")) for p in mirror_dir.rglob("*.md"))


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
        "notes": list_mirrors(Path("notes/mirror")),
        "writings": list_mirrors(Path("writings/mirror")),
        "projects": list_projects(),
        "portfolio": "portfolio.qmd",
        "rules": "AGENTS.md",
    }


def repo_map_json() -> str:
    return json.dumps(repo_map(), indent=2)


def find_mirrors(query: str) -> str:
    """Search across mirror md files only (respects .ignore — never .ipynb)."""
    result = subprocess.run(
        ["rg", "-i", "-n", query, "notes/mirror", "writings/mirror"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def cat_mirror(name: str) -> str:
    """Read a single mirror's content by stem name."""
    for base in (Path("notes/mirror"), Path("writings/mirror")):
        for p in base.rglob(f"{name}.md"):
            if p.exists():
                return p.read_text()
    raise FileNotFoundError(f"no mirror named '{name}'. try `wt ls notes|writings`.")