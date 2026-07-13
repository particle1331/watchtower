"""Resume builder — YAML is the single source for both outputs.

`wt resume` renders assets/resume.yaml -> assets/resume.tex (moderncv PDF)
and index.qmd (site home page) via Jinja2 templates, then runs pdflatex
to produce assets/resume.pdf. Edit the YAML; never hand-edit the generated
.tex / .qmd.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .paths import repo_root

RESUME_YAML = Path("assets/resume.yaml")
RESUME_TEX_J2 = Path("assets/resume.tex.j2")
RESUME_PDF = Path("assets/resume.pdf")
INDEX_QMD_J2 = Path("assets/index.qmd.j2")
INDEX_QMD = Path("index.qmd")
LATEX_ENGINE = "pdflatex"

_URL_RE = re.compile(r"https?://[^\s)]+")

# Order matters: backslash first so we don't double-escape the ones we add.
_LATEX_SPECIAL = str.maketrans({
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
})


def _latex_text(text: str) -> str:
    """Escape LaTeX special chars in prose, wrap bare URLs in robust \\url{}.

    URLs are kept raw inside \\url{...} (which is robust to #, _, ~, etc.).
    The surrounding text gets standard escaping.
    """
    out: list[str] = []
    pos = 0
    for m in _URL_RE.finditer(text):
        if m.start() > pos:
            out.append(text[pos:m.start()].translate(_LATEX_SPECIAL))
        url = m.group(0)
        # Strip #fragment — the bare # is a parameter token inside \cventry's
        # argument capture and breaks pdflatex even inside \url{...}. The page
        # resolves fine without the anchor; the web version keeps the full URL.
        url = url.split("#", 1)[0]
        out.append(r"\url{" + url + "}")
        pos = m.end()
    if pos < len(text):
        out.append(text[pos:].translate(_LATEX_SPECIAL))
    return "".join(out)


def _html_entities(text: str) -> str:
    """Encode every char as numeric HTML entities — obfuscates email from
    naive regex scrapers while displaying normally in browsers.
    """
    return "".join(f"&#{ord(c)};" for c in text)


def _md_escape(text: str) -> str:
    r"""Escape characters that pandoc/markdown would otherwise interpret:
    `$` (math), `*`/`_` (emphasis), backticks (code), `<`/`>` (HTML), `\`.
    URLs are kept raw so they still linkify inside <...>.
    """
    out: list[str] = []
    pos = 0
    for m in _URL_RE.finditer(text):
        if m.start() > pos:
            out.append(_md_escape_text(text[pos:m.start()]))
        out.append(m.group(0))  # keep URLs raw so pandoc autolinks them
        pos = m.end()
    if pos < len(text):
        out.append(_md_escape_text(text[pos:]))
    return "".join(out)


def _md_escape_text(text: str) -> str:
    for ch, rep in (("\\", "\\\\"), ("$", "\\$"), ("*", "\\*"),
                    ("_", "\\_"), ("`", "\\`"), ("<", "&lt;"), (">", "&gt;")):
        text = text.replace(ch, rep)
    return text


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def _make_env(root: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader([str(root / "assets"), str(root)]),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["latex_text"] = _latex_text
    env.filters["html_entities"] = _html_entities
    env.filters["md_escape"] = _md_escape
    return env


def _run_pdflatex(tex: Path, out_dir: Path) -> None:
    subprocess.run(
        [
            LATEX_ENGINE,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={out_dir}",
            str(tex),
        ],
        check=True,
        capture_output=True,
    )


def build_resume() -> tuple[Path, Path]:
    """Render YAML -> assets/resume.pdf and index.qmd. Returns (pdf, qmd)."""
    root = repo_root()
    tex_src = root / RESUME_TEX_J2
    qmd_src = root / INDEX_QMD_J2
    yaml_path = root / RESUME_YAML
    for p in (tex_src, qmd_src, yaml_path):
        if not p.exists():
            raise FileNotFoundError(f"resume source missing: {p}")
    if not shutil.which(LATEX_ENGINE):
        raise FileNotFoundError(
            f"{LATEX_ENGINE} not found on PATH — install TeX Live or MiKTeX."
        )

    data = _load_yaml(yaml_path)
    env = _make_env(root)

    # Render index.qmd (web version with markdown escaping).
    qmd_template = env.get_template(INDEX_QMD_J2.name)
    qmd_rendered = qmd_template.render(**_escape_for_target(data, _md_escape))
    index_path = root / INDEX_QMD
    index_path.write_text(qmd_rendered, encoding="utf-8")

    # Render resume.tex (PDF version with LaTeX escaping).
    tex_template = env.get_template(RESUME_TEX_J2.name)
    tex_rendered = tex_template.render(**_escape_for_target(data, _latex_text))
    with tempfile.TemporaryDirectory(prefix="watchtower-resume-") as tmp:
        tmp_dir = Path(tmp)
        tex_copy = tmp_dir / "resume.tex"
        tex_copy.write_text(tex_rendered, encoding="utf-8")
        _run_pdflatex(tex_copy, tmp_dir)
        _run_pdflatex(tex_copy, tmp_dir)  # 2nd pass for cross-refs / page count.
        built = tmp_dir / "resume.pdf"
        if not built.exists():
            raise FileNotFoundError(
                f"{LATEX_ENGINE} ran but produced no PDF in {tmp_dir}"
            )
        dest_pdf = root / RESUME_PDF
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(built, dest_pdf)
    return dest_pdf, index_path


def _escape_for_target(data: dict, esc) -> dict:
    """Return a deep copy of data with all free-text fields escaped through
    `esc` (either _latex_text for the .tex template or _md_escape for the
    .qmd template). Contact fields (email, phone, github, linkedin) are left
    raw — the LaTeX template gets them verbatim for moderncv macros, and the
    web template applies its own filters (html_entities) at render time.
    """
    import copy
    out = copy.deepcopy(data)
    if "summary" in out:
        out["summary"] = esc(out["summary"])
    for key in ("employment", "skills", "projects", "education"):
        items = out.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                _escape_dict_fields(item, esc)
    return out


def _escape_dict_fields(d: dict, esc) -> None:
    for field in ("bullets", "entries", "courses"):
        if isinstance(d.get(field), list):
            d[field] = [esc(x) for x in d[field]]
    for field in ("title", "company", "dates", "name", "institution",
                  "degree", "major", "awards", "thesis", "description"):
        if field in d:
            d[field] = esc(d[field])


if __name__ == "__main__":  # pragma: no cover
    pdf, _ = build_resume()
    print(f"resume PDF: {pdf}", file=sys.stderr)