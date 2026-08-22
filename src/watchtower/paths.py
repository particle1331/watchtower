"""Repo path resolution helpers for workspace projects."""

from __future__ import annotations

from pathlib import Path

# Absolute repository root. Repo-local generated artifacts should be anchored
# here rather than whichever directory happens to be the caller's cwd.
ROOT_PATH = Path(__file__).parents[2]

# Tier directories (relative to repo root / cwd).
NOTES_DIR    = Path("notes")
COURSES_DIR  = Path("courses")
ARTICLES_DIR = Path("articles")
PROJECTS_DIR = Path("projects")

CONTENT_DIRS: tuple[Path, ...] = (ARTICLES_DIR, NOTES_DIR, COURSES_DIR)


def repo_root() -> Path:
    """Return the watchtower repo root."""
    return ROOT_PATH
