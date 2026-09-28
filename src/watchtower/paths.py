"""Repo path resolution helpers for workspace projects."""

from __future__ import annotations

from pathlib import Path

# Absolute repository root. Repo-local generated artifacts should be anchored
# here rather than whichever directory happens to be the caller's cwd.
ROOT_PATH = Path(__file__).parents[2]

# Notebook content is grouped under one root-level directory. These paths are
# relative so the CLI and its isolated tests continue to follow the caller's
# current working directory.
NB_DIR       = Path("nb")
POSTS_DIR    = NB_DIR / "posts"
COURSES_DIR  = NB_DIR / "courses"
PORTFOLIO_DIR = NB_DIR / "portfolio"
PORTFOLIO_PATH = PORTFOLIO_DIR / "portfolio.ipynb"
PROJECTS_DIR = Path("projects")

CONTENT_DIRS: tuple[Path, ...] = (POSTS_DIR, COURSES_DIR)


def repo_root() -> Path:
    """Return the watchtower repo root."""
    return ROOT_PATH
