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
from typing import Any

import nbformat
import ruamel.yaml

NOTES_DIR = Path("notes")
ARTICLES_DIR = Path("articles")
COURSES_DIR = Path("courses")
PROJECTS = Path("projects")

_yaml = ruamel.yaml.YAML(typ="rt")
_yaml.indent(mapping=2, sequence=4, offset=2)
_yaml.preserve_quotes = True


def _load_yaml(path: Path) -> Any:
    """Load YAML with ruamel round-trip parser."""
    with open(path) as f:
        return _yaml.load(f)


def _dump_yaml(path: Path, data: Any) -> None:
    """Dump YAML preserving comments, key order, and quoting."""
    with open(path, "w") as f:
        _yaml.dump(data, f)


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
{date_line}categories: []
---"""
    nb.cells = [nbformat.v4.new_markdown_cell(frontmatter + body)]
    nbformat.write(nb, path)


def new_note(name: str, title: str | None = None) -> Path:
    """Create notes/<name>.ipynb with a date and title frontmatter.

    If `title` is None, the notebook name is used as the title.
    """
    date = datetime.now().strftime("%Y-%m-%d")
    path = NOTES_DIR / f"{name}.ipynb"
    _write_ipynb(path, title if title is not None else name, date=date)
    return path


def new_article(name: str, title: str | None = None) -> Path:
    """Create articles/<name>.ipynb with a date and title frontmatter.

    If `title` is None, a title is derived from the name by replacing
    separators with spaces and title-casing (e.g. "my-article" -> "My Article").
    """
    date = datetime.now().strftime("%Y-%m-%d")
    path = ARTICLES_DIR / f"{name}.ipynb"
    if title is None:
        title = name.replace("-", " ").title()
    _write_ipynb(path, title, date=date)
    return path


def _find_course_sidebar_entry(data: Any, name: str) -> dict | None:
    """Find a course entry in _quarto.yml's sidebar by id."""
    sidebar = data.get("website", {}).get("sidebar", [])
    for entry in sidebar:
        if isinstance(entry, dict) and entry.get("id") == name:
            return entry
    return None


def _register_course(name: str) -> None:
    """Add a sidebar entry for course *name* to _quarto.yml if not present."""
    quarto = Path("_quarto.yml")
    data = _load_yaml(quarto)
    if _find_course_sidebar_entry(data, name) is not None:
        return  # already registered — idempotent

    sidebar: list = data["website"]["sidebar"]
    new_entry = {
        "id": name,
        "style": "floating",
        "collapse-level": 2,
        "align": "left",
        "contents": [
            {
                "section": "",
                "href": f"courses/{name}/index.ipynb",
                "contents": [
                    {"text": "Overview", "href": f"courses/{name}/index.ipynb"},
                    {
                        "text": "01. Introduction",
                        "href": f"courses/{name}/01-introduction.ipynb",
                    },
                ],
            }
        ],
    }
    sidebar.append(new_entry)
    _dump_yaml(quarto, data)


def new_course(name: str, title: str) -> Path:
    """Create courses/<name>/ with an index notebook and a first lesson stub."""
    course_dir = COURSES_DIR / name
    course_dir.mkdir(parents=True, exist_ok=True)

    # index.ipynb — no H1 in body; Quarto renders the frontmatter `title` as the H1.
    index_path = course_dir / "index.ipynb"
    _write_ipynb(index_path, title, body="\n\nTODO: course overview.\n")

    # first lesson — same: frontmatter `title` becomes the H1.
    lesson_path = course_dir / "01-introduction.ipynb"
    _write_ipynb(lesson_path, "Introduction", body="\n\nTODO: lesson content.\n")

    # register in _quarto.yml sidebar
    _register_course(name)

    return course_dir


def new_course_chapter(
    course: str,
    name: str,
    title: str | None = None,
    section: str | None = None,
) -> Path:
    """Create courses/<course>/<name>.ipynb and register it in the course sidebar.

    If `title` is None, a placeholder is derived from `name` for both the
    notebook frontmatter and the sidebar text. The two are independent
    surfaces — edit either or both after scaffolding.
    """
    course_dir = COURSES_DIR / course
    if not course_dir.is_dir():
        raise FileNotFoundError(f"course directory {course_dir} does not exist")

    path = course_dir / f"{name}.ipynb"
    if path.exists():
        raise FileExistsError(f"{path} already exists")

    if title is None:
        # e.g. test_missing_section4 -> "Test Missing Section4"
        title = name.replace("-", " ").replace("_", " ").title()

    _write_ipynb(path, title)
    _register_chapter_in_sidebar(course, name, title, section)
    return path


def _register_chapter_in_sidebar(
    course: str,
    name: str,
    title: str,
    section: str | None,
) -> None:
    """Add a chapter entry to a course's sidebar in _quarto.yml.

    If `section` is None, appends to the last entry in the contents list
    (which may be the unnamed top-level section if it's the only entry).
    Raises if the course is not registered or the named section is missing.
    """
    quarto = Path("_quarto.yml")
    data = _load_yaml(quarto)
    course_entry = _find_course_sidebar_entry(data, course)
    if course_entry is None:
        raise ValueError(
            f"course '{course}' not registered in _quarto.yml sidebar. "
            f"Run 'wt new course {course}' first."
        )

    contents: list = course_entry.setdefault("contents", [])

    # Find target section
    if section is not None:
        target = None
        for sec in contents:
            if isinstance(sec, dict) and sec.get("section") == section:
                target = sec
                break
        if target is None:
            raise ValueError(
                f"section '{section}' not found in course '{course}'. "
                f"Run 'wt new section {course} \"{section}\"' first."
            )
    else:
        # No --section: append to the last entry in the contents list.
        # This may be the unnamed top-level section if it's the only entry.
        if not contents:
            raise ValueError(
                f"course '{course}' has no sections. "
                f"Run 'wt new section {course} \"<name>\"' first."
            )
        target = contents[-1]

    section_contents: list = target.setdefault("contents", [])
    section_contents.append({
        "text": title,
        "href": f"courses/{course}/{name}.ipynb",
    })

    # If the section has no href, set it to this chapter
    if "href" not in target or target["href"] is None:
        target["href"] = f"courses/{course}/{name}.ipynb"

    _dump_yaml(quarto, data)


def new_course_section(course: str, name: str) -> None:
    """Add a section header to a course's sidebar in _quarto.yml."""
    course_dir = COURSES_DIR / course
    if not course_dir.is_dir():
        raise FileNotFoundError(f"course directory {course_dir} does not exist")

    quarto = Path("_quarto.yml")
    data = _load_yaml(quarto)
    course_entry = _find_course_sidebar_entry(data, course)
    if course_entry is None:
        raise ValueError(
            f"course '{course}' not registered in _quarto.yml sidebar. "
            f"Run 'wt new course {course}' first."
        )

    contents: list = course_entry.setdefault("contents", [])
    for sec in contents:
        if isinstance(sec, dict) and sec.get("section") == name:
            raise ValueError(
                f"section '{name}' already exists in course '{course}'"
            )

    contents.append({"section": name, "contents": []})
    _dump_yaml(quarto, data)


def new_project(name: str) -> Path:
    """uv init projects/<name> as a workspace member."""
    path = PROJECTS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "init", "--package", str(path)], check=True)
    return path