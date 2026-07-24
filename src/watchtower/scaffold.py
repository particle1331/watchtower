"""Scaffold new artifacts: notes, articles, courses, projects.

Notes and articles are Jupyter notebooks (`.ipynb`) — sourced as plain cell
markdown via jupytext for agent reads, edited in JupyterLab as notebooks,
and rendered by Quarto with inline outputs (no execution). Courses are
directory trees with an index notebook and sequential lessons. Project
scaffolding delegates to `uv init`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import nbformat

NOTES_DIR = Path("notes")
ARTICLES_DIR = Path("articles")
COURSES_DIR = Path("courses")
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


def new_course(name: str, title: str | None = None) -> Path:
    """Create courses/<name>/ with an index notebook and a first lesson stub."""
    if title is None:
        title = name.replace("-", " ")
    course_dir = COURSES_DIR / name
    course_dir.mkdir(parents=True, exist_ok=True)

    # index.ipynb
    index_path = course_dir / "index.ipynb"
    _write_ipynb(index_path, title, body=f"\n\n# {title}\n\nTODO: course overview.\n")

    # first lesson
    lesson_path = course_dir / "01-introduction.ipynb"
    _write_ipynb(lesson_path, "Introduction", body=f"\n\n# Introduction\n\nTODO: lesson content.\n")

    # metadata
    metadata_path = course_dir / "_metadata.yml"
    metadata_path.write_text(f'title: "{title}"\ndescription: ""\nlessons:\n  - 01-introduction\n')

    return course_dir


def new_project(name: str) -> Path:
    """uv init projects/<name> as a workspace member."""
    path = PROJECTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], check=True)
    return path