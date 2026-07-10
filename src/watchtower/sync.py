"""Mirror synchronization: notebook (.ipynb) -> markdown mirror (.md).

For each notebook in `notes/src/` or `writings/src/`, we write the markdown
mirror to the corresponding path under `*/mirror/` via `jupytext --to md`.

Mirrors contain prose + code only (no outputs) — clean text for LLM retrieval.

`check_drift()` runs sync then `git diff --exit-code` on the mirror dirs.
Used by the pre-commit hook.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

NOTES_SRC = Path("notes/src")
WRITINGS_SRC = Path("writings/src")
NOTES_MIRROR = Path("notes/mirror")
WRITINGS_MIRROR = Path("writings/mirror")


def _mirror_for(nb: Path) -> Path:
    """notes/src/foo.ipynb      -> notes/mirror/foo.md
    notes/src/sub/foo.ipynb    -> notes/mirror/sub/foo.md
    writings/src/foo.ipynb     -> writings/mirror/foo.md
    """
    if nb.is_relative_to(NOTES_SRC):
        rel = nb.relative_to(NOTES_SRC)
        return NOTES_MIRROR / rel.with_suffix(".md")
    return WRITINGS_MIRROR / nb.relative_to(WRITINGS_SRC).with_suffix(".md")


def _all_notebooks() -> list[Path]:
    return [
        *NOTES_SRC.rglob("*.ipynb"),
        *WRITINGS_SRC.rglob("*.ipynb"),
    ]


def _jupytext_to_md(nb: Path, mirror: Path) -> None:
    mirror.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["jupytext", "--to", "md", "--output", str(mirror), str(nb)],
        check=True,
    )


def sync_all() -> None:
    """Regenerate all mirrors in place."""
    for nb in _all_notebooks():
        _jupytext_to_md(nb, _mirror_for(nb))


def check_drift() -> bool:
    """Sync, then check git working tree for drift in mirror dirs.

    Returns True if mirrors were already up to date (no diff after sync).
    """
    sync_all()
    result = subprocess.run(
        ["git", "diff", "--exit-code", "--", str(NOTES_MIRROR), str(WRITINGS_MIRROR)],
        capture_output=True,
    )
    return result.returncode == 0