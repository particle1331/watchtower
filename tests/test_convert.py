"""Tests for watchtower.convert — import_notebook and import_chapter."""


import shutil
from pathlib import Path

import nbformat
import pytest

from watchtower import convert, scaffold

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def external_nb(tmp_path):
    """A standalone .ipynb outside the repo (absolute path)."""
    path = tmp_path / "external.ipynb"
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("# External")]
    nbformat.write(nb, path)
    return path


@pytest.fixture
def repo_with_course(tmp_path, monkeypatch):
    """Isolated repo with a pre-created 'ml' course."""
    monkeypatch.chdir(tmp_path)
    shutil.copy(FIXTURES_DIR / "quarto.yml", tmp_path / "_quarto.yml")
    scaffold.new_course("ml", "Machine Learning")
    return tmp_path


# ---------------------------------------------------------------------------
# import_notebook (flat tiers)
# ---------------------------------------------------------------------------

def test_import_notebook_to_notes(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    dest = convert.import_notebook(str(external_nb), "notes")
    assert dest.exists()
    assert dest == Path("notes") / "external.ipynb"


def test_import_notebook_to_articles(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    dest = convert.import_notebook(str(external_nb), "articles")
    assert dest.exists()
    assert dest == Path("articles") / "external.ipynb"


def test_import_notebook_custom_name(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    dest = convert.import_notebook(str(external_nb), "notes", "my-note")
    assert dest == Path("notes") / "my-note.ipynb"


def test_import_notebook_preserves_cells(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    dest = convert.import_notebook(str(external_nb), "notes")
    nb = nbformat.read(dest, as_version=nbformat.NO_CONVERT)
    assert nb.cells[0].source == "# External"


def test_import_strips_duplicate_h1_same_cell(tmp_path, monkeypatch):
    """A `# Title` heading right after frontmatter is dropped (no double H1)."""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src.ipynb"
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            '---\ntitle: "Weak Supervision"\ndate: "2026-04-30"\n'
            'categories: [weak-supervision]\n---\n\n# Weak Supervision\n'
        ),
        nbformat.v4.new_markdown_cell("## Introduction\n\nbody\n"),
    ]
    nbformat.write(nb, src)

    dest = convert.import_notebook(str(src), "notes")
    out = nbformat.read(dest, as_version=nbformat.NO_CONVERT)
    assert out.cells[0].source.startswith("---")
    assert "# Weak Supervision" not in out.cells[0].source
    assert out.cells[1].source == "## Introduction\n\nbody\n"


def test_import_strips_duplicate_h1_next_cell(tmp_path, monkeypatch):
    """A `# Title` heading in the cell after the frontmatter is dropped too."""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src.ipynb"
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell('---\ntitle: "Weak Supervision"\n---\n'),
        nbformat.v4.new_markdown_cell("# Weak Supervision\n"),
        nbformat.v4.new_markdown_cell("## Introduction\n\nbody\n"),
    ]
    nbformat.write(nb, src)

    dest = convert.import_notebook(str(src), "notes")
    out = nbformat.read(dest, as_version=nbformat.NO_CONVERT)
    # H1-only cell is removed; body cell becomes cell 1.
    assert out.cells[0].source.startswith("---")
    assert out.cells[1].source == "## Introduction\n\nbody\n"


def test_import_keeps_h1_without_frontmatter(tmp_path, monkeypatch):
    """Without frontmatter there is no duplicate title, so the H1 is kept."""
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "src.ipynb"
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("# Just A Title\n\nbody\n")]
    nbformat.write(nb, src)

    dest = convert.import_notebook(str(src), "notes")
    out = nbformat.read(dest, as_version=nbformat.NO_CONVERT)
    assert out.cells[0].source == "# Just A Title\n\nbody\n"


def test_import_notebook_duplicate_raises(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    convert.import_notebook(str(external_nb), "notes")
    with pytest.raises(FileExistsError):
        convert.import_notebook(str(external_nb), "notes")


def test_import_notebook_courses_raises(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="courses"):
        convert.import_notebook(str(external_nb), "courses")


def test_import_notebook_missing_source_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        convert.import_notebook("/nonexistent/path.ipynb", "notes")


# ---------------------------------------------------------------------------
# import_chapter (courses — nested one level deeper)
# ---------------------------------------------------------------------------

def test_import_chapter_default_name(repo_with_course, external_nb):
    dest = convert.import_chapter(str(external_nb), "ml")
    # result is at courses/ml/<stem>.ipynb
    assert dest.exists()
    assert dest.parent.name == "ml"
    assert dest.name == "external.ipynb"


def test_import_chapter_custom_name(repo_with_course, external_nb):
    dest = convert.import_chapter(str(external_nb), "ml", chapter="02-regression")
    assert dest == Path("courses") / "ml" / "02-regression.ipynb"
    assert dest.exists()


def test_import_chapter_missing_course_raises(tmp_path, monkeypatch, external_nb):
    monkeypatch.chdir(tmp_path)
    shutil.copy(FIXTURES_DIR / "quarto.yml", tmp_path / "_quarto.yml")
    with pytest.raises(FileNotFoundError, match="course directory"):
        convert.import_chapter(str(external_nb), "nonexistent")


def test_import_chapter_duplicate_raises(repo_with_course, external_nb):
    convert.import_chapter(str(external_nb), "ml")
    with pytest.raises(FileExistsError):
        convert.import_chapter(str(external_nb), "ml")
