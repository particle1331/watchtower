"""Tests for watchtower.cli — helpers and light CLI surface checks."""


import io

import nbformat
import pytest
from rich.console import Console
from typer.testing import CliRunner

from watchtower import cli

runner = CliRunner()


@pytest.fixture
def cli_console(monkeypatch):
    """Redirect the module-level rich console into a buffer for assertions."""
    buf = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buf, force_terminal=False))
    return buf


def _write_code_notebook(path, sources):
    """Write a minimal notebook with one code cell per source string."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell(s) for s in sources]
    nbformat.write(nb, path)
    return path


# ---------------------------------------------------------------------------
# wt tag with --tag locator
# ---------------------------------------------------------------------------

def test_cli_tag_accepts_tag_locator(nb_file):
    r1 = runner.invoke(cli.app, ["tag", "test", "--index", "0", "--add", "focus"])
    assert r1.exit_code == 0
    r2 = runner.invoke(cli.app, ["tag", "test", "--tag", "focus"])
    assert r2.exit_code == 0
    assert "focus" in r2.output


def test_cli_tag_requires_locator(nb_file, cli_console, invoke):
    # Error handling lives in cli.main(), so go through it.
    assert invoke("tag", "test", "--add", "focus") == 1
    assert "exactly one" in cli_console.getvalue()


# ---------------------------------------------------------------------------
# wt run exit codes
# ---------------------------------------------------------------------------

def test_cli_run_success_exit_0(nb_file):
    result = runner.invoke(cli.app, ["run", "test"])
    assert result.exit_code == 0
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[1].outputs


def test_cli_run_errors_exit_1(tmp_path, monkeypatch, cli_console):
    monkeypatch.chdir(tmp_path)
    _write_code_notebook(tmp_path / "notes" / "err.ipynb", ["1/0"])
    result = runner.invoke(cli.app, ["run", "err"])
    assert result.exit_code == 1
    assert "ZeroDivisionError" in cli_console.getvalue()
