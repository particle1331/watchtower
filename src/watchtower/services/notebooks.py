"""Recovery-gated notebook operations, retaining the existing cell API."""
from __future__ import annotations

import threading
from functools import wraps
from pathlib import Path
from typing import Any

import nbformat

from .workspace import WorkspaceStore

_LOCAL = threading.local()


def managed(function: Any) -> Any:
    @wraps(function)
    def operation(*args: Any, **kwargs: Any) -> Any:
        root = Path.cwd().resolve()
        if not (root / "content/data/catalog.yaml").exists():
            return function(*args, **kwargs)
        store = WorkspaceStore(root)
        with store.locked():
            outer = getattr(_LOCAL, "inputs", None)
            if outer is None:
                _LOCAL.inputs = store.inputs()
            try:
                return function(*args, **kwargs)
            finally:
                if outer is None:
                    del _LOCAL.inputs
    return operation


def write_notebook(notebook: nbformat.NotebookNode, path: Path) -> None:
    root = Path.cwd().resolve()
    if not (root / "content/data/catalog.yaml").exists():
        nbformat.write(notebook, path)
        return
    store = WorkspaceStore(root)
    with store.locked():
        name = path.resolve().relative_to(root).as_posix()
        expected = getattr(_LOCAL, "inputs", None) or store.inputs()
        store.commit({name: nbformat.writes(notebook).encode()}, expected, "notebook operation")
