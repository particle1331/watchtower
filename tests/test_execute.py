"""Tests for watchtower.execute — in-place notebook execution via nbclient.

These launch a real kernel (python3) where noted; keep them small and few.
"""

import nbformat
import pytest

from watchtower import execute


def _write_code_notebook(path, sources):
    """Write a minimal notebook with one code cell per source string."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell(s) for s in sources]
    nbformat.write(nb, path)
    return path


def _output_text(cell) -> str:
    return "".join(cell.outputs[0].text) if isinstance(cell.outputs[0].text, list) else cell.outputs[0].text


def test_run_uses_notebook_kernelspec_unless_overridden(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "notes" / "kernel.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "watchtower"}
    nb.cells = [nbformat.v4.new_code_cell("print('hello')")]
    nbformat.write(nb, path)

    selected = []

    def fake_execute(notebook, *, kernel, timeout):
        selected.append(kernel)

    monkeypatch.setattr(execute, "_execute", fake_execute)

    execute.run_notebook("kernel")
    execute.run_notebook("kernel", kernel="python3")

    assert selected == ["watchtower", "python3"]


# ---------------------------------------------------------------------------
# whole-notebook runs
# ---------------------------------------------------------------------------

def test_run_writes_stdout_output(nb_file):
    result = execute.run_notebook("test")
    assert result["ran"] == 1
    assert result["errors"] == []
    assert result["path"].resolve() == nb_file.resolve()
    nb = nbformat.read(nb_file, as_version=nbformat.NO_CONVERT)
    assert nb.cells[1].execution_count == 1
    assert len(nb.cells[1].outputs) == 1
    assert nb.cells[1].outputs[0].output_type == "stream"
    assert "hello" in _output_text(nb.cells[1])


def test_run_captures_error_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write_code_notebook(tmp_path / "notes" / "err.ipynb", ["1/0", "print('after')"])
    result = execute.run_notebook("err")
    assert result["ran"] == 2
    assert result["errors"] == [
        {"index": 0, "ename": "ZeroDivisionError", "evalue": "division by zero"}
    ]
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    # error stored inline, execution continued to the next cell
    assert nb.cells[0].outputs[0].output_type == "error"
    assert nb.cells[0].outputs[0].ename == "ZeroDivisionError"
    assert nb.cells[1].execution_count == 2
    assert "after" in _output_text(nb.cells[1])


def test_run_single_cell_writes_only_requested_cell(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write_code_notebook(
        tmp_path / "notes" / "single.ipynb", ["print('first')", "print('second')"]
    )
    result = execute.run_notebook("single", index=0)
    assert result["ran"] == 1
    assert result["errors"] == []
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert nb.cells[0].execution_count == 1
    assert "first" in _output_text(nb.cells[0])
    assert nb.cells[1].outputs == []


def test_run_single_cell_has_state_from_earlier_cells(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write_code_notebook(
        tmp_path / "notes" / "context.ipynb", ["value = 41", "print(value + 1)"]
    )

    result = execute.run_notebook("context", index=1)

    assert result["ran"] == 2
    assert result["errors"] == []
    nb = nbformat.read(path, as_version=nbformat.NO_CONVERT)
    assert nb.cells[0].outputs == []
    assert "42" in _output_text(nb.cells[1])
    assert nb.cells[1].execution_count == 2


def test_run_single_cell_out_of_bounds(nb_file):
    with pytest.raises(ValueError, match="out of bounds"):
        execute.run_notebook("test", index=99)


def test_run_zero_code_cells_skips_kernel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "notes" / "mdonly.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("# only markdown")]
    nbformat.write(nb, path)

    class _MustNotLaunch:
        def __init__(self, *args, **kwargs):
            raise AssertionError("kernel must not be launched for zero code cells")

        def execute(self):
            raise AssertionError("kernel must not be launched for zero code cells")

    monkeypatch.setattr(execute, "NotebookClient", _MustNotLaunch)
    result = execute.run_notebook("mdonly")
    assert result["ran"] == 0
    assert result["errors"] == []
    assert result["path"].resolve() == path.resolve()
