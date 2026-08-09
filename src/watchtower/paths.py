"""Repo path resolution helpers for workspace projects."""

from pathlib import Path

# Tier directories (relative to repo root / cwd).
NOTES_DIR = Path("notes")
ARTICLES_DIR = Path("articles")
COURSES_DIR = Path("courses")
PROJECTS_DIR = Path("projects")
CONTENT_DIRS: tuple[Path, ...] = (ARTICLES_DIR, NOTES_DIR, COURSES_DIR)


def repo_root() -> Path:
    """Return the watchtower repo root."""
    return Path(__file__).parents[2]
