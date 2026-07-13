"""One-time conversion of legacy Jupyter notebooks (`.ipynb`) to Quarto markdown.

Uses `jupytext` to write a `.qmd` file next to the source notebook (or at an
explicit destination), preserving prose + code. This is a migration helper —
the rest of the system is qmd-only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def convert_ipynb_to_qmd(ipynb: str, dest: str | None = None) -> Path:
    """Convert <path>.ipynb -> <path>.qmd (or an explicit dest .qmd).

    jupytext's `qmd` format is Quarto markdown with the right cell fencing
    (```{python} ... ```), so the output renders directly with `quarto render`.
    """
    src = Path(ipynb).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    if src.suffix != ".ipynb":
        raise ValueError(f"expected an .ipynb file, got: {src}")
    out = Path(dest).resolve() if dest else src.with_suffix(".qmd")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["jupytext", "--to", "qmd", "--output", str(out), str(src)],
        check=True,
    )
    return out