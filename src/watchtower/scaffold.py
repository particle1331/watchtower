"""Scaffold new artifacts: notes, essays, projects.

Notes and essays are Quarto markdown (`.qmd`) files — plain text, so the
source doubles directly as the knowledge base. Project scaffolding delegates
to `uv init`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path("notes")
ESSAYS_DIR = Path("essays")
PROJECTS = Path("projects")


def _minimal_qmd(title: str) -> str:
    return f"""---
title: "{title}"
---

"""


def _write_qmd(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_minimal_qmd(title))


def new_note(name: str) -> Path:
    """Create notes/<name>.qmd with a minimal front-matter stub."""
    path = NOTES_DIR / f"{name}.qmd"
    _write_qmd(path, name)
    return path


def new_essay(slug: str) -> Path:
    """Create essays/<YYYY-MM-DD>-<slug>.qmd."""
    date = datetime.now().strftime("%Y-%m-%d")
    title = slug.replace("-", " ")
    path = ESSAYS_DIR / f"{date}-{slug}.qmd"
    _write_qmd(path, title)
    return path


def new_project(name: str) -> Path:
    """uv init projects/<name> as a workspace member."""
    path = PROJECTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], check=True)
    return path