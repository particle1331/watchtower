"""Structured access to stored Jupyter cell outputs.

Notebook outputs are already persisted in the canonical ``.ipynb`` file. This
module turns those JSON-shaped records into a small, typed interface that an
agent can use without knowing nbformat's output schema. Text stays in memory;
image payloads can be written to ``ROOT_PATH / ".tmp"`` for visual
inspection.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import nbformat

from .inspect import resolve_ipynb
from .notebook import read_notebook
from .paths import ROOT_PATH

_IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}


@dataclass(frozen=True)
class CellOutput:
    """One stored output from a notebook cell.

    ``data`` contains display payloads keyed by MIME type. Binary image
    values are decoded to ``bytes``; textual values remain ``str``. Stream and
    error outputs use ``text`` and have an empty ``data`` mapping.
    """

    cell_index: int
    output_index: int
    output_type: str
    text: str | None = None
    data: dict[str, str | bytes] = field(default_factory=dict)

    @property
    def image_data(self) -> dict[str, bytes]:
        """Return image MIME payloads from this output."""
        return {
            mime: value
            for mime, value in self.data.items()
            if mime.startswith("image/") and isinstance(value, bytes)
        }

    @property
    def is_image(self) -> bool:
        """Whether this output contains at least one decoded image."""
        return bool(self.image_data)


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    return str(value)


def _decode_image(mime: str, value: Any) -> bytes | None:
    """Decode an nbformat image value, tolerating raw SVG and byte values."""
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        return None
    if mime == "image/svg+xml" or value.lstrip().startswith("<svg"):
        return value.encode("utf-8")
    try:
        return base64.b64decode(value)
    except (ValueError, TypeError):
        return value.encode("utf-8")


def _normalize_output(
    output: nbformat.NotebookNode, cell_index: int, output_index: int
) -> CellOutput:
    output_type = output.get("output_type", "unknown")
    if output_type == "stream":
        return CellOutput(
            cell_index,
            output_index,
            output_type,
            text=_as_text(output.get("text", "")),
        )
    if output_type == "error":
        traceback = output.get("traceback", "")
        traceback_text = _as_text(traceback) if traceback else ""
        evalue = _as_text(output.get("evalue", ""))
        text = f"{evalue}\n{traceback_text}" if evalue and traceback_text else evalue or traceback_text
        return CellOutput(cell_index, output_index, output_type, text=text)

    raw_data = output.get("data", {}) or {}
    data: dict[str, str | bytes] = {}
    for mime, value in raw_data.items():
        if mime.startswith("image/"):
            decoded = _decode_image(mime, value)
            if decoded is not None:
                data[mime] = decoded
        elif isinstance(value, (str, bytes, list)):
            data[mime] = _as_text(value) if not isinstance(value, bytes) else value

    text_value = data.get("text/plain") or data.get("text/html")
    text = text_value.decode("utf-8", errors="replace") if isinstance(text_value, bytes) else text_value
    return CellOutput(cell_index, output_index, output_type, text=text, data=data)


def _resolve_path(notebook: str | Path) -> Path:
    path = Path(notebook)
    if path.exists() and path.suffix == ".ipynb":
        return path.resolve()
    return resolve_ipynb(str(notebook))


def get_cell_outputs(notebook: str | Path, cell_index: int) -> list[CellOutput]:
    """Return all stored outputs for ``cell_index`` in ``notebook``.

    ``notebook`` accepts the same bare stem, tier-prefixed stem, or full path
    forms as ``wt cat``. Markdown cells return an empty list; invalid indices
    raise ``ValueError``. No kernel is started and the notebook is unchanged.
    """
    path = _resolve_path(notebook)
    nb = read_notebook(path)
    if not (0 <= cell_index < len(nb["cells"])):
        raise ValueError(
            f"index {cell_index} out of bounds (notebook has {len(nb['cells'])} cells)."
        )
    cell = nb["cells"][cell_index]
    if cell.get("cell_type") != "code":
        return []
    return [
        _normalize_output(output, cell_index, output_index)
        for output_index, output in enumerate(cell.get("outputs", []) or [])
    ]


def get_cell_output(
    notebook: str | Path, cell_index: int, output_index: int = 0
) -> CellOutput:
    """Return one stored output, raising ``IndexError`` when absent."""
    if output_index < 0:
        raise IndexError(f"output index must be non-negative, got {output_index}")
    outputs = get_cell_outputs(notebook, cell_index)
    try:
        return outputs[output_index]
    except IndexError as exc:
        raise IndexError(
            f"cell {cell_index} has no output at index {output_index}"
        ) from exc


def save_cell_images(
    notebook: str | Path,
    cell_index: int,
    directory: str | Path | None = None,
) -> list[Path]:
    """Save all image payloads from a cell and return their paths.

    Filenames are deterministic: ``<notebook>-cell-<N>-output-<K>.<ext>``.
    Existing files are replaced, making repeated agent inspection idempotent.
    """
    path = _resolve_path(notebook)
    out_dir = _output_directory(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    saved: list[Path] = []
    for output in get_cell_outputs(path, cell_index):
        saved.extend(_save_output_images(output, stem, cell_index, out_dir))
    return saved


def _save_output_images(
    output: CellOutput, stem: str, cell_index: int, directory: Path
) -> list[Path]:
    saved: list[Path] = []
    for mime, payload in output.image_data.items():
        extension = _IMAGE_EXTENSIONS.get(mime, ".bin")
        image_path = directory / (
            f"{stem}-cell-{cell_index}-output-{output.output_index}{extension}"
        )
        image_path.write_bytes(payload)
        saved.append(image_path)
    return saved


def save_output_images(
    notebook: str | Path,
    output: CellOutput,
    directory: str | Path | None = None,
) -> list[Path]:
    """Save image payloads from one :class:`CellOutput` and return their paths."""
    path = _resolve_path(notebook)
    out_dir = _output_directory(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    return _save_output_images(output, path.stem, output.cell_index, out_dir)


def _output_directory(directory: str | Path | None) -> Path:
    """Resolve an optional destination, defaulting to ``ROOT_PATH / ".tmp"``."""
    return ROOT_PATH / ".tmp" if directory is None else Path(directory)
