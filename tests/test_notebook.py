"""Tests for watchtower.notebook — cell read/write operations."""


import nbformat
import pytest

from watchtower import notebook

# ---------------------------------------------------------------------------
# count_cells
# ---------------------------------------------------------------------------

def test_count_cells(nb_file):
    assert notebook.count_cells("test") == 3


def test_count_cells_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        notebook.count_cells("nonexistent")


# ---------------------------------------------------------------------------
# cat_notebook
# ---------------------------------------------------------------------------

def test_cat_all_cells(nb_file):
    out = notebook.cat_notebook("test")
    assert "# Title" in out
    assert "print('hello')" in out
    assert "## Section" in out


def test_cat_single_index(nb_file):
    out = notebook.cat_notebook("test", index="0")
    assert "# Title" in out
    assert "print('hello')" not in out


def test_cat_range(nb_file):
    out = notebook.cat_notebook("test", index="0:2")
    assert "# Title" in out
    assert "print('hello')" in out
    assert "## Section" not in out


def test_cat_by_tag(nb_file):
    notebook.tag_cell("test", index=0, add=["focus"])
    out = notebook.cat_notebook("test", tag="focus")
    assert "# Title" in out
    assert "## Section" not in out


def test_cat_out_of_bounds_raises(nb_file):
    with pytest.raises(ValueError, match="out of bounds"):
        notebook.cat_notebook("test", index="99")


# ---------------------------------------------------------------------------
# edit_cell
# ---------------------------------------------------------------------------

def test_edit_cell_by_index(nb_file):
    notebook.edit_cell("test", "# Updated", index=0)
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[0].source == "# Updated"


def test_edit_cell_preserves_other_cells(nb_file):
    notebook.edit_cell("test", "# Updated", index=0)
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert len(nb.cells) == 3
    assert nb.cells[1].source == "print('hello')"


def test_edit_cell_by_tag(nb_file):
    notebook.tag_cell("test", index=2, add=["conclusion"])
    notebook.edit_cell("test", "## Conclusion", tag="conclusion")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[2].source == "## Conclusion"


def test_edit_cell_too_long_raises(nb_file):
    with pytest.raises(ValueError, match="too long"):
        notebook.edit_cell("test", "x" * (notebook.MAX_CELL_SOURCE_CHARS + 1), index=0)


# ---------------------------------------------------------------------------
# append_cell
# ---------------------------------------------------------------------------

def test_append_markdown_cell(nb_file):
    notebook.append_cell("test", "new content", cell_type="md")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert len(nb.cells) == 4
    assert nb.cells[-1].source == "new content"
    assert nb.cells[-1].cell_type == "markdown"


def test_append_code_cell(nb_file):
    notebook.append_cell("test", "x = 1", cell_type="code")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[-1].cell_type == "code"
    assert nb.cells[-1].source == "x = 1"


# ---------------------------------------------------------------------------
# insert_cell
# ---------------------------------------------------------------------------

def test_insert_cell_after(nb_file):
    notebook.insert_cell("test", "inserted", after=0, cell_type="md")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[1].source == "inserted"
    assert len(nb.cells) == 4


def test_insert_cell_before(nb_file):
    notebook.insert_cell("test", "inserted", before=1, cell_type="md")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[1].source == "inserted"


def test_insert_cell_by_tag(nb_file):
    notebook.tag_cell("test", index=0, add=["anchor"])
    notebook.insert_cell("test", "after anchor", tag="anchor", cell_type="md")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[1].source == "after anchor"


def test_insert_cell_no_locator_raises(nb_file):
    with pytest.raises(ValueError):
        notebook.insert_cell("test", "x", cell_type="md")


# ---------------------------------------------------------------------------
# remove_cell
# ---------------------------------------------------------------------------

def test_remove_cell_by_index(nb_file):
    notebook.remove_cell("test", index=1)
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert len(nb.cells) == 2
    assert nb.cells[0].source == "# Title"
    assert nb.cells[1].source == "## Section"


def test_remove_cell_by_tag_removes_all(nb_file):
    notebook.tag_cell("test", index=0, add=["del"])
    notebook.tag_cell("test", index=2, add=["del"])
    notebook.remove_cell("test", tag="del")
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert len(nb.cells) == 1


def test_remove_cell_not_found_raises(nb_file):
    with pytest.raises(ValueError, match="no cell matched"):
        notebook.remove_cell("test", tag="nonexistent")


# ---------------------------------------------------------------------------
# tag_cell
# ---------------------------------------------------------------------------

def test_tag_cell_add(nb_file):
    notebook.tag_cell("test", index=0, add=["important"])
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert "important" in nb.cells[0].metadata.get("tags", [])


def test_tag_cell_remove(nb_file):
    notebook.tag_cell("test", index=0, add=["important"])
    notebook.tag_cell("test", index=0, remove=["important"])
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert "important" not in nb.cells[0].metadata.get("tags", [])


def test_tag_cell_read_only_returns_list(nb_file):
    result = notebook.tag_cell("test", index=0)
    assert isinstance(result, list)


def test_tag_cell_read_only_does_not_write(nb_file):
    import os
    mtime_before = os.path.getmtime(nb_file)
    notebook.tag_cell("test", index=0)
    assert os.path.getmtime(nb_file) == mtime_before
