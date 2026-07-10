"""Repo path resolution helpers for workspace projects."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return the watchtower repo root by walking up to find AGENTS.md."""
    cwd = Path.cwd()
    for p in (cwd, *cwd.parents):
        if (p / "AGENTS.md").exists() and (p / "pyproject.toml").exists():
            return p
    return cwd