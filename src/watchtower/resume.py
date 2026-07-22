"""Resume builder — YAML is the single source for both outputs.

`wt resume` renders assets/resume.yaml -> assets/resume.tex (moderncv PDF)
and index.ipynb (site home page) via a Jinja2 template, then runs pdflatex
to produce assets/resume.pdf. Edit the YAML; never hand-edit the generated
.tex / .ipynb.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import nbformat
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .paths import repo_root

RESUME_YAML = Path("assets/resume.yaml")
RESUME_TEX_J2 = Path("assets/resume.tex.j2")
RESUME_TEX = Path("assets/resume.tex")
RESUME_PDF = Path("assets/resume.pdf")
INDEX_IPYNB_J2 = Path("assets/index.ipynb.j2")
INDEX_IPYNB = Path("index.ipynb")
LATEX_ENGINE = "pdflatex"

_URL_RE = re.compile(r"https?://[^\s)]+")
_MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\((?P<url>https?://[^\s)]+)\)")
_URL_OR_LINK_RE = re.compile(
    r"\[(?P<md_text>[^\]]*)\]\((?P<md_url>https?://[^\s)]+)\)"
    r"|(?P<bare>https?://[^\s)]+)"
)

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

    Markdown links [text](url) become \\href{url}{escaped text}.
    Bare URLs are kept raw inside \\url{...} (which is robust to #, _, ~, etc.).
    The surrounding text gets standard escaping.
    """
    out: list[str] = []
    pos = 0
    for m in _URL_OR_LINK_RE.finditer(text):
        if m.start() > pos:
            out.append(text[pos:m.start()].translate(_LATEX_SPECIAL))
        if m.group("md_url"):
            url = m.group("md_url").split("#", 1)[0]
            link_text = m.group("md_text").translate(_LATEX_SPECIAL)
            out.append(r"\href{" + url + "}{" + link_text + "}")
        else:
            url = m.group("bare").split("#", 1)[0]
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


def _run_pdflatex(tex: Path, out_dir: Path, source_epoch: int) -> None:
    # SOURCE_DATE_EPOCH makes pdfTeX stamp /CreationDate, /ModDate, and /ID
    # from this epoch instead of the current wall-clock, so reruns produce
    # byte-identical PDFs when the sources are unchanged (reproducible build).
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(source_epoch)}
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
        env=env,
    )


def build_resume() -> tuple[Path, Path]:
    """Render YAML -> assets/resume.pdf and index.ipynb. Returns (pdf, ipynb)."""
    root = repo_root()
    tex_src = root / RESUME_TEX_J2
    ipynb_src = root / INDEX_IPYNB_J2
    yaml_path = root / RESUME_YAML
    for p in (tex_src, ipynb_src, yaml_path):
        if not p.exists():
            raise FileNotFoundError(f"resume source missing: {p}")
    if not shutil.which(LATEX_ENGINE):
        raise FileNotFoundError(
            f"{LATEX_ENGINE} not found on PATH — install TeX Live or MiKTeX."
        )

    data = _load_yaml(yaml_path)
    env = _make_env(root)

    # Pin PDF timestamps to the newest source mtime so reruns are reproducible.
    source_epoch = int(max(p.stat().st_mtime for p in (tex_src, ipynb_src, yaml_path)))

    # Render index.ipynb (web version with markdown escaping) as a single
    # markdown cell containing Quarto frontmatter + body.
    ipynb_template = env.get_template(INDEX_IPYNB_J2.name)
    ipynb_rendered = ipynb_template.render(**_escape_for_target(data, _md_escape))
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb.cells = [nbformat.v4.new_markdown_cell(ipynb_rendered)]
    index_path = root / INDEX_IPYNB
    nbformat.write(nb, index_path)

    # Render resume.tex (PDF version with LaTeX escaping).
    tex_template = env.get_template(RESUME_TEX_J2.name)
    tex_rendered = tex_template.render(**_escape_for_target(data, _latex_text))
    (root / RESUME_TEX).write_text(tex_rendered, encoding="utf-8")
    # Use a STABLE scratch dir basename: pdfTeX hashes the absolute build path
    # into the PDF /ID, so a random tmp suffix would make every run's bytes
    # differ. Combined with SOURCE_DATE_EPOCH (set in _run_pdflatex) this
    # makes reruns byte-identical when sources are unchanged.
    tmp_dir = Path(tempfile.gettempdir()) / "watchtower-resume-build"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        tex_copy = tmp_dir / "resume.tex"
        tex_copy.write_text(tex_rendered, encoding="utf-8")
        _run_pdflatex(tex_copy, tmp_dir, source_epoch)
        _run_pdflatex(tex_copy, tmp_dir, source_epoch)  # 2nd pass for cross-refs / page count.
        built = tmp_dir / "resume.pdf"
        if not built.exists():
            raise FileNotFoundError(
                f"{LATEX_ENGINE} ran but produced no PDF in {tmp_dir}"
            )
        dest_pdf = root / RESUME_PDF
        dest_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(built, dest_pdf)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
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
    for key in ("employment", "early_employment", "skills", "projects", "education"):
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