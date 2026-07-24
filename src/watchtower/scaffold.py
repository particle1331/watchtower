"""Scaffold new artifacts: notes, articles, projects.

Notes and articles are Jupyter notebooks (`.ipynb`) — sourced as plain cell
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
ARTICLES_DIR = Path("articles")
PROJECTS = Path("projects")


def _write_ipynb(path: Path, title: str, date: str | None = None, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    date_line = f'date: "{date}"\n' if date else ""
    frontmatter = f"""---
title: "{title}"
{date_line}---
"""
    nb.cells = [nbformat.v4.new_markdown_cell(frontmatter + body)]
    nbformat.write(nb, path)


def new_note(name: str) -> Path:
    """Create notes/<name>.ipynb with a minimal title frontmatter."""
    path = NOTES_DIR / f"{name}.ipynb"
    _write_ipynb(path, name)
    return path


def new_article(name: str) -> Path:
    """Create articles/<name>.ipynb with a date and title frontmatter."""
    date = datetime.now().strftime("%Y-%m-%d")
    title = name.replace("-", " ")
    path = ARTICLES_DIR / f"{name}.ipynb"
    _write_ipynb(path, title, date=date)
    return path


def new_project(name: str) -> Path:
    """uv init projects/<name> as a workspace member."""
    path = PROJECTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], check=True)
    return path