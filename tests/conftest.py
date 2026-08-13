"""Shared pytest fixtures for the watchtower test suite."""


import shutil
from pathlib import Path

import nbformat
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Isolated repo root: cwd = tmp_path with a minimal _quarto.yml."""
    monkeypatch.chdir(tmp_path)
    shutil.copy(FIXTURES_DIR / "quarto.yml", tmp_path / "_quarto.yml")
    return tmp_path


def make_notebook(path: Path, cells: list[nbformat.NotebookNode]) -> Path:
    """Write a minimal notebook to *path* (creates parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = cells
    nbformat.write(nb, path)
    return path


@pytest.fixture
def nb_file(tmp_path, monkeypatch):
    """A 3-cell notebook at notes/test.ipynb with cwd = tmp_path."""
    monkeypatch.chdir(tmp_path)
    return make_notebook(
        tmp_path / "notes" / "test.ipynb",
        [
            nbformat.v4.new_markdown_cell("# Title"),
            nbformat.v4.new_code_cell("print('hello')"),
            nbformat.v4.new_markdown_cell("## Section"),
        ],
    )
