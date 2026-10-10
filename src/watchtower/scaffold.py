"""Scaffold post and course notebooks.

Posts are Jupyter notebooks (`.ipynb`) — edited in JupyterLab
as notebooks (agents read them through the `wt` CLI), and rendered by
Quarto with inline outputs (no execution). Courses are directory trees with
an index notebook and sequential lessons.
"""


from datetime import datetime
from pathlib import Path
from typing import Any

import nbformat
import ruamel.yaml
import yaml

from . import knowledge
from .paths import COURSES_DIR, POSTS_DIR

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


def _write_ipynb(path: Path, title: str, date: str | None = None, body: str = "", *, include_tags: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    lines = ["---", f'title: "{title}"']
    if date:
        lines.append(f'date: "{date}"')
    if include_tags:
        lines.append("tags: []")
    lines.append("---")
    nb.cells = [nbformat.v4.new_markdown_cell("\n".join(lines) + body)]
    nbformat.write(nb, path)


def new_post(name: str, title: str | None = None) -> Path:
    """Create nb/posts/<name>.ipynb with a date and title frontmatter.

    If `title` is None, a title is derived from the name by replacing
    separators with spaces and title-casing (e.g. "my-post" -> "My Post").
    """
    date = datetime.now().strftime("%Y-%m-%d")
    path = POSTS_DIR / f"{name}.ipynb"
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    if title is None:
        title = name.replace("-", " ").replace("_", " ").title()
    _write_ipynb(path, title, date=date, include_tags=True)
    knowledge.add_artifact(f"post/{name}", "post", path, title)
    return path


def _find_course_sidebar_entry(data: Any, name: str) -> dict | None:
    """Find a course entry in the authored sidebar by id."""
    sidebar = data.get("website", {}).get("sidebar", [])
    for entry in sidebar:
        if isinstance(entry, dict) and entry.get("id") == name:
            return entry
    return None


def _course_href(course: str, filename: str) -> str:
    """Return a Quarto href for a notebook in a course."""
    return f"{COURSES_DIR.as_posix()}/{course}/{filename}"


def _register_course(name: str) -> None:
    """Add a sidebar entry for course *name* if not present."""
    sidebar_path = knowledge.SIDEBAR_PATH
    data = knowledge.load_sidebar_source()
    if _find_course_sidebar_entry(data, name) is not None:
        return  # already registered — idempotent

    sidebar: list = data["website"].setdefault("sidebar", [])
    new_entry = {
        "id": name,
        "style": "floating",
        "collapse-level": 2,
        "align": "left",
        "contents": [
            {
                "section": "",
                "href": _course_href(name, "index.ipynb"),
                "contents": [{"text": "01. Introduction", "href": _course_href(name, "01-introduction.ipynb")}],
            }
        ],
    }
    sidebar.append(new_entry)
    _dump_yaml(sidebar_path, data)


def new_course(name: str, title: str) -> Path:
    """Create nb/courses/<name>/ with an index notebook and a first lesson stub."""
    course_dir = COURSES_DIR / name
    course_dir.mkdir(parents=True, exist_ok=True)

    # Stub files are written only when missing, so re-running 'wt new course'
    # never clobbers content. No H1 in the body: Quarto renders the
    # frontmatter `title` as the H1.
    index_path = course_dir / "index.ipynb"
    if not index_path.exists():
        _write_ipynb(index_path, title, body=f"\n\n{knowledge.INCLUDE_MARKER}\n\nTODO: course introduction.\n")
    course_yaml = course_dir / "course.yaml"
    if not course_yaml.exists():
        course_yaml.write_text(
            yaml.safe_dump({
                "id": f"course/{name}", "purpose": "", "audience": "",
                "planned": {"summary": ""}, "actualized": {"summary": ""},
            }, sort_keys=False),
            encoding="utf-8",
        )
    lesson_path = course_dir / "01-introduction.ipynb"
    if not lesson_path.exists():
        _write_ipynb(lesson_path, "Introduction", body="\n\nTODO: lesson content.\n")

    # Register the authored sidebar before adding the catalog records.
    _register_course(name)
    if knowledge.get_artifact(f"course/{name}") is None:
        knowledge.add_artifact(f"course/{name}", "course", course_dir, title)
    if knowledge.get_artifact(f"course/{name}/01-introduction") is None:
        knowledge.add_artifact(
            f"course/{name}/01-introduction", "chapter", lesson_path,
            "Introduction", parent=f"course/{name}",
        )
    knowledge.render_course_includes()
    knowledge.sync_site()

    return course_dir


def new_course_chapter(
    course: str,
    name: str,
    title: str | None = None,
    section: str | None = None,
) -> Path:
    """Create nb/courses/<course>/<name>.ipynb and register it in the course sidebar.

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
    knowledge.add_artifact(f"course/{course}/{name}", "chapter", path, title, parent=f"course/{course}")
    knowledge.sync_site()
    return path


def _register_chapter_in_sidebar(
    course: str,
    name: str,
    title: str,
    section: str | None,
) -> None:
    """Add a chapter entry to a course's authored sidebar.

    If `section` is None, appends to the last entry in the contents list
    (which may be the unnamed top-level section if it's the only entry).
    Raises if the course is not registered or the named section is missing.
    """
    sidebar_path = knowledge.SIDEBAR_PATH
    data = knowledge.load_sidebar_source()
    course_entry = _find_course_sidebar_entry(data, course)
    if course_entry is None:
        raise ValueError(
            f"course '{course}' not registered in the authored sidebar. "
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
        "href": _course_href(course, f"{name}.ipynb"),
    })

    # If the section has no href, set it to this chapter
    if "href" not in target or target["href"] is None:
        target["href"] = _course_href(course, f"{name}.ipynb")

    _dump_yaml(sidebar_path, data)


def new_course_section(course: str, name: str) -> None:
    """Add a section header to a course's authored sidebar."""
    course_dir = COURSES_DIR / course
    if not course_dir.is_dir():
        raise FileNotFoundError(f"course directory {course_dir} does not exist")

    sidebar_path = knowledge.SIDEBAR_PATH
    data = knowledge.load_sidebar_source()
    course_entry = _find_course_sidebar_entry(data, course)
    if course_entry is None:
        raise ValueError(
            f"course '{course}' not registered in the authored sidebar. "
            f"Run 'wt new course {course}' first."
        )

    contents: list = course_entry.setdefault("contents", [])
    for sec in contents:
        if isinstance(sec, dict) and sec.get("section") == name:
            raise ValueError(
                f"section '{name}' already exists in course '{course}'"
            )

    contents.append({"section": name, "contents": []})
    _dump_yaml(sidebar_path, data)
    knowledge.sync_site()
