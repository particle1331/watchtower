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
# wt kernels
# ---------------------------------------------------------------------------

def test_cli_kernels_lists_kernel_names(monkeypatch):
    from watchtower import kernels

    monkeypatch.setattr(
        kernels,
        "available_kernel_rows",
        lambda: [("python3", "python", "Python 3")],
    )
    result = runner.invoke(cli.app, ["kernels"])
    assert result.exit_code == 0
    assert "python3" in result.output


def test_cli_run_kernel_error_lists_available_names(tmp_path, monkeypatch, cli_console, invoke):
    monkeypatch.chdir(tmp_path)
    _write_code_notebook(tmp_path / "notes" / "test.ipynb", ["print('hello')"])

    from watchtower import execute, kernels

    def fail(*args, **kwargs):
        raise ValueError("kernel 'missing' failed to run: No such kernel named missing")

    monkeypatch.setattr(execute, "run_notebook", fail)
    monkeypatch.setattr(kernels, "available_kernel_names", lambda: ["python3", "xcpp14"])

    assert invoke("run", "test", "--kernel", "missing") == 1
    output = cli_console.getvalue()
    assert "Available kernels:" in output
    assert "python3, xcpp14" in output
    assert "wt kernels" in output


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


def test_cli_docs_passes_port_and_prints_preview_url(monkeypatch, cli_console):
    from watchtower import render

    seen = []
    monkeypatch.setattr(render, "preview_site", lambda port: seen.append(port))

    result = runner.invoke(cli.app, ["docs", "--port", "4300"])

    assert result.exit_code == 0
    assert seen == [4300]
    assert "http://localhost:4300/" in cli_console.getvalue()


# ---------------------------------------------------------------------------
# wt diff
# ---------------------------------------------------------------------------

def test_print_diff_highlights_interactive_terminal(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(
        cli,
        "console",
        Console(file=buf, force_terminal=True, color_system="standard", no_color=False),
    )

    cli._print_diff("@@ -1 +1 @@\n-old\n+new")

    output = buf.getvalue()
    assert "\x1b[" in output
    assert "-old" in output
    assert "+new" in output


def test_print_diff_stays_plain_when_not_terminal(monkeypatch, capsys):
    monkeypatch.setattr(cli, "console", Console(force_terminal=False))

    cli._print_diff("@@ -1 +1 @@\n-old\n+new")

    assert capsys.readouterr().out == "@@ -1 +1 @@\n-old\n+new\n"


def test_print_diff_respects_no_color(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "console",
        Console(force_terminal=True, color_system="standard", no_color=True),
    )

    cli._print_diff("@@ -1 +1 @@\n-old\n+new")

    assert "\x1b[" not in capsys.readouterr().out
