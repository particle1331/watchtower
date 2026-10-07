"""Recovery-gated notebook operations, retaining the existing cell API."""
from __future__ import annotations

import threading
from functools import wraps
from pathlib import Path
from typing import Any

import nbformat

from .workspace import ServiceError, WorkspaceStore, digest

_LOCAL = threading.local()


def source_revision(value: bytes) -> str:
    return "notebook:" + digest(value)


def check_revision(path: Path, expected_revision: str | None) -> None:
    if expected_revision is None:
        return
    current = source_revision(path.read_bytes()) if path.is_file() else "notebook:absent"
    if expected_revision.strip('"') != current:
        raise ServiceError(f"stale notebook revision; current revision {current}", code="conflict", status=412, paths=[str(path)])


def read_source(path: Path) -> tuple[nbformat.NotebookNode, str]:
    value = path.read_bytes()
    return nbformat.reads(value.decode("utf-8"), as_version=nbformat.NO_CONVERT), source_revision(value)


def managed(function: Any) -> Any:
    @wraps(function)
    def operation(*args: Any, **kwargs: Any) -> Any:
        root = Path.cwd().resolve()
        expected_revision = kwargs.get("expected_revision")

        def check() -> None:
            if expected_revision is not None:
                from watchtower.inspect import resolve_ipynb
                check_revision(resolve_ipynb(args[0] if args else kwargs["name"]), expected_revision)

        if not (root / "content/data/catalog.yaml").exists():
            check()
            return function(*args, **kwargs)
        store = WorkspaceStore(root)
        with store.locked():
            outer = getattr(_LOCAL, "inputs", None)
            if outer is None:
                _LOCAL.inputs = store.inputs()
            try:
                check()
                return function(*args, **kwargs)
            finally:
                if outer is None:
                    del _LOCAL.inputs
    return operation


@managed
def execution_source(name: str, *, expected_revision: str | None = None) -> tuple[Path, nbformat.NotebookNode, str]:
    """Capture one notebook under the gate; execution happens after it is released."""
    from watchtower.inspect import resolve_ipynb
    path = resolve_ipynb(name)
    notebook, token = read_source(path)
    return path, notebook, token


def write_notebook(notebook: nbformat.NotebookNode, path: Path, *, expected_revision: str | None = None) -> None:
    root = Path.cwd().resolve()
    if not (root / "content/data/catalog.yaml").exists():
        check_revision(path, expected_revision)
        nbformat.write(notebook, path)
        return
    store = WorkspaceStore(root)
    with store.locked():
        check_revision(path, expected_revision)
        name = path.resolve().relative_to(root).as_posix()
        expected = getattr(_LOCAL, "inputs", None) or store.inputs()
        store.commit({name: nbformat.writes(notebook).encode()}, expected, "notebook operation")
