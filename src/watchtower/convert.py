"""Import an external Jupyter notebook into a content tier.

`wt import <src.ipynb> notes|articles|courses [<name>]` copies a notebook
(usually one you ran elsewhere — Colab, Kaggle, a teammate's machine) into
the chosen tier dir. Outputs are preserved as-is; Quarto renders them
without re-execution.
"""

from __future__ import annotations

from pathlib import Path

import nbformat

TIERS = ("notes", "articles", "courses")


def import_notebook(src: str, tier: str, name: str | None = None) -> Path:
    """Copy <src.ipynb> into <tier>/<name>.ipynb (default: same stem as src)."""
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got: {tier}")
    source = Path(src).resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix != ".ipynb":
        raise ValueError(f"expected an .ipynb file, got: {source}")

    stem = name if name is not None else source.stem
    dest_dir = Path(tier)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stem}.ipynb"

    # Re-write via nbformat for a clean, normalized JSON (drops Colab metadata
    # noise, etc.). Outputs are preserved.
    nb = nbformat.read(source, as_version=nbformat.NO_CONVERT)
    if "kernelspec" not in nb.metadata:
        nb.metadata["kernelspec"] = {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        }
    nbformat.write(nb, dest)
    return dest