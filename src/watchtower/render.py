"""Quarto wrappers: render notebook->PDF for read-back, publish site."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NOTES_PDF_DIR = Path("notes/pdf")


def _quarto_env() -> dict[str, str]:
    """Point Quarto at the current Python (the uv venv, where jupyter lives)."""
    return {**os.environ, "QUARTO_PYTHON": sys.executable}


def render_pdf(notebook: str) -> Path:
    """Render a notebook to PDF under notes/pdf/.

    Quarto writes the PDF next to the input by default (single-file renders
    don't support --output-dir / --output with paths). We move it after.
    """
    nb = Path(notebook).resolve()
    if not nb.exists():
        raise FileNotFoundError(nb)
    NOTES_PDF_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["quarto", "render", str(nb), "--to", "pdf"],
        check=True,
        env=_quarto_env(),
    )
    out_pdf = nb.with_suffix(".pdf")
    dest_pdf = NOTES_PDF_DIR / nb.name.replace(".ipynb", ".pdf")
    out_pdf.rename(dest_pdf)
    return dest_pdf


def preview_site() -> None:
    """Serve the writings+portfolio site (blocking — previews in browser)."""
    subprocess.run(["quarto", "preview"], check=True, env=_quarto_env())


def publish_site() -> None:
    """Render the site to _site/."""
    subprocess.run(["quarto", "render"], check=True, env=_quarto_env())