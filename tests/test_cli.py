"""Tests for watchtower.cli — helpers and light CLI surface checks."""


import io

import nbformat
import pytest
from rich.console import Console
from typer.testing import CliRunner

from watchtower import cli

UNICODE_SAMPLE = "Box: ├── │ └──  Arrow: →  Dash: —  Bullet: •  Check: ✓  café"

runner = CliRunner()


class _FakeStdin:
    """Minimal stand-in exposing a binary ``buffer`` like ``sys.stdin``."""

    def __init__(self, raw: bytes) -> None:
        self.buffer = io.BytesIO(raw)


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


def test_read_stdin_decodes_utf8_regardless_of_locale(monkeypatch):
    # Bytes are UTF-8; decoding them as cp1252 (the old Windows default)
    # would mangle every non-ASCII glyph into mojibake. _read_stdin must
    # decode as UTF-8 from the raw buffer.
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(UNICODE_SAMPLE.encode("utf-8")))
    assert cli._read_stdin() == UNICODE_SAMPLE


def test_force_utf8_streams_is_idempotent_and_safe():
    # Should never raise, even when called repeatedly or when streams lack
    # a reconfigure method (guarded by getattr).
    cli._force_utf8_streams()
    cli._force_utf8_streams()


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
