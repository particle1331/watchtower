"""Render one repository notebook to PDF with make render NOTEBOOK=<path>."""

import os
import subprocess
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT_PATH / "nb"


def quarto_env() -> dict[str, str]:
    """Keep Jupyter and LuaLaTeX caches in the repository environment."""
    tex_cache = ROOT_PATH / ".tmp" / "texmf-var"
    tex_cache.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "QUARTO_PYTHON": sys.executable}
    env.setdefault("TEXMFVAR", str(tex_cache))
    env.setdefault("TEXMFCACHE", str(tex_cache))
    return env


def render_pdf() -> Path:
    name = os.environ.get("NOTEBOOK", "").strip()
    if not name:
        raise ValueError("pass NOTEBOOK=nb/posts/<name>.ipynb to make render")

    source = Path(name)
    if source.suffix == "":
        source = source.with_suffix(".ipynb")
    if source.suffix != ".ipynb":
        raise ValueError("NOTEBOOK must be a .ipynb file")
    if not source.is_absolute():
        source = ROOT_PATH / source
    source = source.resolve()
    if NOTEBOOKS_DIR not in source.parents or not source.is_file():
        raise FileNotFoundError(f"notebook not found under nb/: {source}")

    subprocess.run(
        ["quarto", "render", str(source), "--to", "pdf"],
        cwd=ROOT_PATH,
        check=True,
        env=quarto_env(),
    )

    relative_pdf = source.relative_to(ROOT_PATH).with_suffix(".pdf")
    candidates = [source.with_suffix(".pdf"), ROOT_PATH / "_site" / relative_pdf]
    generated = next((path for path in candidates if path.is_file()), None)
    if generated is None:
        raise FileNotFoundError(f"Quarto finished without a PDF at {candidates}")

    destination = source.parent / "pdf" / f"{source.stem}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    generated.replace(destination)
    return destination


if __name__ == "__main__":
    try:
        print(f"rendered {render_pdf()}")
    except (OSError, ValueError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
