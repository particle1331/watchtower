"""Import an external Jupyter notebook into a content tier.

`wt import <src.ipynb> notes|articles` copies a notebook (usually one you ran
elsewhere — Colab, Kaggle, a teammate's machine) into the chosen tier dir.
Outputs are preserved as-is; Quarto renders them without re-execution.

`wt import <src.ipynb> courses <course> [<chapter>]` imports a notebook as
a chapter of an existing course, copying it to `courses/<course>/<stem>.ipynb`
and registering it in the course's sidebar in `_quarto.yml`.
"""


import re
from pathlib import Path

import nbformat

from . import scaffold
from .paths import ARTICLES_DIR, NOTES_DIR

TIERS = ("notes", "articles", "courses")
FLAT_TIERS = ("notes", "articles")

_FLAT_DIRS = {"notes": NOTES_DIR, "articles": ARTICLES_DIR}

_FRONTMATTER_RE = re.compile(
    r"^---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*\r?\n?", re.DOTALL
)
_H1_RE = re.compile(r"^#\s")


def _strip_leading_h1(text: str) -> tuple[str, bool]:
    """Remove a single leading `# ...` heading from *text*.

    Skips blank lines first, so the heading may sit right after the closing
    frontmatter delimiter. Returns `(rest, removed)`; only a top-level `#`
    heading is removed — `##` sections and body text are left untouched.
    """
    lines = text.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and _H1_RE.match(lines[i].lstrip()):
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        return "\n".join(lines[i:]), True
    return text, False


def _strip_duplicate_title(nb) -> None:
    """Drop a leading `# Title` heading that duplicates the frontmatter title.

    Watchtower renders the frontmatter `title` as the page's H1, so an
    imported notebook that keeps its own `# Title` heading right after the
    frontmatter would render two H1s. Remove that heading — whether it sits in
    the same cell as the frontmatter or in the immediately following cell.
    """
    cells = nb.cells
    if not cells:
        return
    first = cells[0]
    if first.cell_type != "markdown":
        return
    match = _FRONTMATTER_RE.match(first.source)
    if match is None:
        return  # no frontmatter -> no separate title H1 to strip
    frontmatter = match.group(0)
    body = first.source[match.end():]

    new_body, removed = _strip_leading_h1(body)
    if removed:
        first.source = frontmatter + new_body
        return

    # Frontmatter is the only content of this cell; look at the next cell.
    if body.strip() == "" and len(cells) > 1:
        nxt = cells[1]
        if nxt.cell_type == "markdown":
            new_src, removed = _strip_leading_h1(nxt.source)
            if removed:
                if new_src.strip() == "":
                    del cells[1]
                else:
                    nxt.source = new_src


def _copy_ipynb(src: Path, dest: Path) -> None:
    """Copy `src` to `dest` via nbformat, normalizing kernelspec if missing.

    Also strips a leading `# Title` heading that would duplicate the
    frontmatter title once Quarto renders it (see `_strip_duplicate_title`).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.read(src, as_version=nbformat.NO_CONVERT)
    if "kernelspec" not in nb.metadata:
        nb.metadata["kernelspec"] = {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        }
    _strip_duplicate_title(nb)
    nbformat.write(nb, dest)


def _validate_source(src: str) -> Path:
    """Resolve and validate an external .ipynb source path."""
    source = Path(src).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix != ".ipynb":
        raise ValueError(f"expected an .ipynb file, got: {source}")
    return source


def import_notebook(src: str, tier: str, name: str | None = None) -> Path:
    """Copy <src.ipynb> into <tier>/<name>.ipynb (default: same stem as src).

    For flat tiers (notes, articles). For courses, use `import_chapter`.
    """
    if tier == "courses":
        raise ValueError(
            "flat import only supports (notes, articles), got: courses. "
            "For courses, use 'wt import <ipynb> courses <course-slug> "
            "[<chapter>] [--section <name>]'."
        )
    tier_dir = _FLAT_DIRS.get(tier)
    if tier_dir is None:
        raise ValueError(
            f"unknown tier: {tier!r}. flat import supports notes|articles."
        )
    source = _validate_source(src)
    stem = name if name is not None else source.stem
    dest = tier_dir / f"{stem}.ipynb"
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    _copy_ipynb(source, dest)
    return dest


def import_chapter(
    src: str,
    course: str,
    chapter: str | None = None,
    section: str | None = None,
) -> Path:
    """Import a notebook as a chapter of a course.

    Copies `<src>.ipynb` to `courses/<course>/<chapter>.ipynb` (default
    chapter name = source filename without extension) and registers it
    in the course's sidebar in `_quarto.yml` under the last section, or
    under `section` if given. The sidebar text is derived from the chapter
    name (same heuristic as `wt new chapter`); edit either the sidebar text
    or the notebook frontmatter after import — they're independent surfaces.
    """
    source = _validate_source(src)
    course_dir = scaffold.COURSES_DIR / course
    if not course_dir.is_dir():
        raise FileNotFoundError(
            f"course directory {course_dir} does not exist. "
            f"Run 'wt new course {course} \"<title>\"' first."
        )

    chapter = chapter if chapter is not None else source.stem
    dest = course_dir / f"{chapter}.ipynb"
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")

    _copy_ipynb(source, dest)
    title = chapter.replace("-", " ").replace("_", " ").title()
    scaffold._register_chapter_in_sidebar(course, chapter, title, section)
    return dest
