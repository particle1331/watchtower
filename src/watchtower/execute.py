"""Execute notebook code cells in-place via nbclient, writing outputs back.

Quarto renders notebooks with inline outputs and never re-runs code, so
`wt run` is the sanctioned way to refresh or verify outputs: it launches a
kernel, executes the code cells, and writes the resulting outputs (and
execution counts) back into the `.ipynb`.

Execution is JupyterLab-like: a cell that raises stores its error as an
inline output and execution continues with the next cell. Single-cell runs
execute in a *fresh* kernel, so no state carries over from other cells. A
cell that depends on earlier cells will fail, and that failure is the
useful signal.
"""

from pathlib import Path

import nbformat
from nbclient import NotebookClient

from .inspect import resolve_ipynb


def _read_notebook(path: Path) -> nbformat.NotebookNode:
    return nbformat.read(path, as_version=nbformat.NO_CONVERT)


def _cell_error_summary(
    cell: nbformat.NotebookNode, index: int
) -> list[dict]:
    """Error outputs of one cell as {"index", "ename", "evalue"} dicts."""
    out: list[dict] = []
    for output in cell.get("outputs", []) or []:
        if output.get("output_type") == "error":
            out.append(
                {
                    "index": index,
                    "ename": output.get("ename", "Error"),
                    "evalue": output.get("evalue", ""),
                }
            )
    return out


def _collect_errors(nb: nbformat.NotebookNode) -> list[dict]:
    """All error outputs across the notebook, as index-keyed summaries."""
    errors: list[dict] = []
    for i, cell in enumerate(nb["cells"]):
        errors.extend(_cell_error_summary(cell, i))
    return errors


def _execute(nb: nbformat.NotebookNode, *, kernel: str, timeout: int) -> None:
    """Run *nb*'s cells in a kernel, storing outputs back into *nb*.

    `allow_errors=True` is nbclient 0.11's flag for JupyterLab-like
    behavior (the pre-0.11 `error_on_cell_execution=False` no longer
    exists): execution continues past cell errors and error outputs are
    stored inline.
    """
    client = NotebookClient(
        nb,
        timeout=timeout,
        kernel_name=kernel,
        allow_errors=True,
    )
    try:
        client.execute()
    except Exception as e:
        raise ValueError(
            f"kernel '{kernel}' failed to run: {e}. "
            f"is ipykernel installed / kernel '{kernel}' available?"
        ) from e


def run_notebook(
    name: str,
    *,
    index: int | None = None,
    kernel: str | None = None,
    timeout: int = 300,
) -> dict:
    """Execute a notebook's code cells and write outputs back in-place.

    Returns {"ran": n, "errors": [...], "path": Path} where `ran` is the
    number of code cells executed and `errors` lists each inline error
    output as {"index", "ename", "evalue"}.

    With *index*: execute only that one cell in a fresh kernel and copy its
    outputs (and execution count) back onto the original cell. Without:
    execute all code cells; if there are none, no kernel is launched.
    """
    path = resolve_ipynb(name)
    nb = _read_notebook(path)
    kernel = kernel or "python3"
    if index is not None:
        return _run_single_cell(nb, path, index, kernel, timeout)
    code_count = sum(1 for c in nb["cells"] if c.get("cell_type") == "code")
    if code_count == 0:
        return {"ran": 0, "errors": [], "path": path}
    _execute(nb, kernel=kernel, timeout=timeout)
    nbformat.write(nb, path)
    return {"ran": code_count, "errors": _collect_errors(nb), "path": path}


def _run_single_cell(
    nb: nbformat.NotebookNode,
    path: Path,
    index: int,
    kernel: str,
    timeout: int,
) -> dict:
    total = len(nb["cells"])
    if not (0 <= index < total):
        raise ValueError(
            f"index {index} out of bounds (notebook has {total} cells)."
        )
    cell = nb["cells"][index]
    if cell.get("cell_type") != "code":
        return {"ran": 0, "errors": [], "path": path}
    temp = nbformat.v4.new_notebook()
    temp["cells"] = [nbformat.v4.new_code_cell(cell.get("source", ""))]
    # Keep the cell's metadata (tags etc.): Quarto honors it and nbclient
    # reads tags like `raises-exception`.
    temp["cells"][0]["metadata"] = cell.get("metadata", {})
    _execute(temp, kernel=kernel, timeout=timeout)
    executed = temp["cells"][0]
    cell["outputs"] = executed.get("outputs", [])
    cell["execution_count"] = executed.get("execution_count")
    nbformat.write(nb, path)
    return {
        "ran": 1,
        "errors": _cell_error_summary(executed, index),
        "path": path,
    }
