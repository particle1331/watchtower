"""Quarto wrappers: render qmd->PDF for read-back, serve site."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NOTES_PDF_DIR = Path("notes/pdf")
ESSAYS_PDF_DIR = Path("essays/pdf")
ESSAYS_DIR = Path("essays").resolve()


def _pdf_dir_for(qmd: Path) -> Path:
    return ESSAYS_PDF_DIR if ESSAYS_DIR in qmd.parents else NOTES_PDF_DIR


def _quarto_env() -> dict[str, str]:
    """Point Quarto at the current Python (the uv venv, where jupyter lives)."""
    return {**os.environ, "QUARTO_PYTHON": sys.executable}


def _find_output_pdf(qmd: Path) -> Path | None:
    """Locate the PDF Quarto produced — next to the source or in _site/."""
    local = qmd.with_suffix(".pdf")
    if local.exists():
        return local
    # Project renders go to _site/<relative-path>.pdf
    site = Path("_site") / qmd.relative_to(Path(".").resolve()).with_suffix(".pdf")
    if site.exists():
        return site
    return None


def render_pdf(source: str) -> Path:
    """Render a .qmd file to PDF under notes/pdf/ or essays/pdf/."""
    src = Path(source).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    pdf_dir = _pdf_dir_for(src)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["quarto", "render", str(src), "--to", "pdf"],
        check=True,
        env=_quarto_env(),
    )
    out_pdf = _find_output_pdf(src)
    if out_pdf is None:
        raise FileNotFoundError(
            f"quarto rendered but no PDF found (searched: {src.with_suffix('.pdf')}, "
            f"_site/{src.relative_to(Path('.').resolve()).with_suffix('.pdf')})"
        )
    dest_pdf = pdf_dir / src.with_suffix(".pdf").name
    out_pdf.rename(dest_pdf)
    return dest_pdf


def preview_site() -> None:
    """Serve the essays+portfolio site (blocking — previews in browser)."""
    subprocess.run(["quarto", "preview"], check=True, env=_quarto_env())