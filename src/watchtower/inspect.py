"""Agent-facing inspection helpers: repo structure, search, file content.

These produce plain stdout (JSON or text) suitable for an AI agent calling
`wt map`, `wt find`, or `wt cat` via bash. The canonical source is `.ipynb`
notebooks in the content dirs; cell sources (no JSON noise) are exposed via
jupytext for low-token agent reads.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

NOTES_DIR = Path("notes")
ESSAYS_DIR = Path("essays")
LEARNING_DIR = Path("learning")

CONTENT_DIRS: tuple[Path, ...] = (NOTES_DIR, ESSAYS_DIR, LEARNING_DIR)


def list_ipynb(src_dir: Path) -> list[str]:
    if not src_dir.exists():
        return []
    return sorted(
        str(p.relative_to("."))
        for p in src_dir.rglob("*.ipynb")
        if p.name != "index.ipynb" and ".ipynb_checkpoints" not in p.parts
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
        "notes": list_ipynb(NOTES_DIR),
        "essays": list_ipynb(ESSAYS_DIR),
        "learning": list_ipynb(LEARNING_DIR),
        "projects": list_projects(),
        "portfolio": "portfolio.ipynb",
        "rules": "AGENTS.md",
    }


def repo_map_json() -> str:
    return json.dumps(repo_map(), indent=2)


def find_in_src(query: str) -> str:
    """Search `.ipynb` cell sources across all content dirs.

    Uses ripgrep to cheaply list notebooks whose raw JSON contains the
    query, then parses each hit file once with ``json.load`` to report
    matches keyed by cell index. Output is always:

        path [cell N]: matching text

    so agents can follow up directly with ``wt cat <path> --index N``.
    """
    q = query.lower()
    rg = subprocess.run(
        ["rg", "-i", "-l", query, *[str(d) for d in CONTENT_DIRS],
         "-g", "*.ipynb"],
        capture_output=True,
        text=True,
    )
    files = [Path(ln) for ln in rg.stdout.splitlines() if ln]
    results: list[str] = []
    for p in sorted(files):
        if ".ipynb_checkpoints" in p.parts:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                nb = json.load(f)
        except Exception:
            continue
        for i, cell in enumerate(nb.get("cells", [])):
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            if q not in src.lower():
                continue
            for line in src.splitlines():
                if q in line.lower():
                    results.append(f"{p} [cell {i}]: {line}")
    return "\n".join(results)


def resolve_ipynb(name: str) -> Path:
    """Find a `.ipynb` by stem, tier-prefixed stem, or full path.

    Accepted forms:
      - 001-testnote                 bare stem (searched across tiers)
      - notes/001-testnote           tier-prefixed stem (--index, --limit: 0)
      - notes/001-testnote.ipynb     full path
    """
    # Full path: direct check
    maybe = Path(name)
    if maybe.exists() and maybe.suffix == ".ipynb":
        return maybe.resolve()
    # Tier-prefixed stem: strip the tier dir prefix
    parts = name.split("/", 1)
    if len(parts) == 2 and parts[0] in {"notes", "essays", "learning"}:
        tier, stem = parts
        # Strip optional .ipynb suffix
        if stem.endswith(".ipynb"):
            stem = stem[:-len(".ipynb")]
        path = Path(tier) / f"{stem}.ipynb"
        if path.exists():
            return path
    # Bare stem: search across tiers
    for base in CONTENT_DIRS:
        for p in base.rglob(f"{name}.ipynb"):
            if p.exists() and ".ipynb_checkpoints" not in p.parts:
                return p
    raise FileNotFoundError(f"no ipynb named '{name}'. try `wt ls notes|essays|learning`.")