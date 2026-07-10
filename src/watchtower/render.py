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


def _find_output_pdf(nb: Path) -> Path | None:
    """Locate the PDF Quarto produced — next to the notebook or in _site/."""
    local = nb.with_suffix(".pdf")
    if local.exists():
        return local
    # Project renders go to _site/<relative-path>.pdf
    site = Path("_site") / nb.relative_to(Path(".").resolve()).with_suffix(".pdf")
    if site.exists():
        return site
    return None


def render_pdf(notebook: str) -> Path:
    """Render a notebook to PDF under notes/pdf/."""
    nb = Path(notebook).resolve()
    if not nb.exists():
        raise FileNotFoundError(nb)
    NOTES_PDF_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["quarto", "render", str(nb), "--to", "pdf"],
        check=True,
        env=_quarto_env(),
    )
    out_pdf = _find_output_pdf(nb)
    if out_pdf is None:
        raise FileNotFoundError(
            f"quarto rendered but no PDF found (searched: {nb.with_suffix('.pdf')}, "
            f"_site/{nb.relative_to(Path('.').resolve()).with_suffix('.pdf')})"
        )
    dest_pdf = NOTES_PDF_DIR / nb.name.replace(".ipynb", ".pdf")
    out_pdf.rename(dest_pdf)
    return dest_pdf


def preview_site() -> None:
    """Serve the writings+portfolio site (blocking — previews in browser)."""
    subprocess.run(["quarto", "preview"], check=True, env=_quarto_env())


def publish_site() -> None:
    """Render the site to _site/."""
    subprocess.run(["quarto", "render"], check=True, env=_quarto_env())