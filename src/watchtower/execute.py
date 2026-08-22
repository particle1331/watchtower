"""Execute notebook code cells in-place via nbclient, writing outputs back.

Quarto renders notebooks with inline outputs and never re-runs code, so
`wt run` is the sanctioned way to refresh or verify outputs: it launches a
kernel, executes the code cells, and writes the resulting outputs (and
execution counts) back into the `.ipynb`.

Execution is JupyterLab-like: a cell that raises stores its error as an
inline output and execution continues with the next cell. Indexed runs
execute the notebook prefix through the selected cell in a *fresh* kernel,
so imports and variables from earlier cells are available. Only the selected
cell's outputs and execution count are copied back to the notebook.
"""

import copy
from pathlib import Path

import nbformat
from nbclient import NotebookClient

from .inspect import resolve_ipynb
from .notebook import read_notebook


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
        raise ValueError(f"kernel '{kernel}' failed to run: {e}") from e


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

    If *kernel* is omitted, use the notebook's ``kernelspec.name`` and fall
    back to ``python3`` when no kernelspec is stored. With *index*: execute all
    cells through that one in a fresh kernel, so the selected cell has the
    state established by earlier cells. Copy only its
    outputs (and execution count) back onto the original cell. Without:
    execute all code cells; if there are none, no kernel is launched.
    """
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    if kernel is None:
        kernelspec = nb.metadata.get("kernelspec") or {}
        kernel = kernelspec.get("name") or "python3"
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
    # Execute the prefix so the target sees imports and variables defined by
    # earlier cells. Deep-copy it so context-cell outputs are not written back.
    temp["cells"] = copy.deepcopy(nb["cells"][: index + 1])
    _execute(temp, kernel=kernel, timeout=timeout)
    executed = temp["cells"][index]
    cell["outputs"] = executed.get("outputs", [])
    cell["execution_count"] = executed.get("execution_count")
    nbformat.write(nb, path)
    return {
        "ran": sum(1 for c in temp["cells"] if c.get("cell_type") == "code"),
        "errors": _collect_errors(temp),
        "path": path,
    }
