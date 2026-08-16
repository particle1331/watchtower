"""Shared pytest fixtures for the watchtower test suite."""


import shutil
from pathlib import Path

import nbformat
import pytest

from watchtower import cli

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
def invoke(monkeypatch):
    """Run cli.main() with the given argv; return its exit code.

    User errors are caught in cli.main(), so error-path tests must go
    through it (invoking cli.app directly bypasses the handler).
    """
    def _invoke(*args: str) -> int:
        monkeypatch.setattr(cli.sys, "argv", ["wt", *args])
        try:
            cli.main()
        except SystemExit as e:
            return int(e.code or 0)
        return 0

    return _invoke


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
