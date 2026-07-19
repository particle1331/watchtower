"""Scaffold new artifacts: notes, essays, projects.

Notes and essays are Jupyter notebooks (`.ipynb`) — sourced as plain cell
markdown via jupytext for agent reads, edited in JupyterLab as notebooks,
and rendered by Quarto with inline outputs (no execution). Project
scaffolding delegates to `uv init`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import nbformat

NOTES_DIR = Path("notes")
ESSAYS_DIR = Path("essays")
PROJECTS = Path("projects")


def _write_ipynb(path: Path, title: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    frontmatter = f"""---
title: "{title}"
---

"""
    nb.cells = [nbformat.v4.new_markdown_cell(frontmatter + body)]
    nbformat.write(nb, path)


def new_note(name: str) -> Path:
    """Create notes/<name>.ipynb with a minimal title frontmatter."""
    path = NOTES_DIR / f"{name}.ipynb"
    _write_ipynb(path, name)
    return path


def new_essay(slug: str) -> Path:
    """Create essays/<YYYY-MM-DD>-<slug>.ipynb."""
    date = datetime.now().strftime("%Y-%m-%d")
    title = slug.replace("-", " ")
    path = ESSAYS_DIR / f"{date}-{slug}.ipynb"
    _write_ipynb(path, title)
    return path


def new_project(name: str) -> Path:
    """uv init projects/<name> as a workspace member."""
    path = PROJECTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], check=True)
    return path