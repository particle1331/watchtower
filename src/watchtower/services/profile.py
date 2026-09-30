"""Profile presentation helpers and reproducible PDF builds in a generated stage."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from watchtower.models import Profile

_URL_OR_LINK_RE = re.compile(
    r"\[(?P<md_text>[^\]]*)\]\((?P<md_url>https?://[^\s)]+)\)"
    r"|(?P<bare>https?://[^\s)]+)"
)

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
    if isinstance(out.get("homepage_intro"), list):
        out["homepage_intro"] = [esc(value) for value in out["homepage_intro"]]
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

def latex_profile(profile: Profile) -> dict[str, Any]:
    """Escape display fields without changing structured contact conventions."""
    return _escape_for_target(profile.model_dump(mode="json", exclude_none=True), _latex_text)


def build_resume_pdf(stage: Path, source_epoch: int = 1767225600) -> Path:
    """Compile the snapshot-derived TeX and fonts, never workspace content."""
    if shutil.which("xelatex") is None:
        raise RuntimeError("Résumé PDF build requires xelatex on PATH")
    destination = stage / "assets/resume.pdf"
    output = stage / ".resume-build"
    output.mkdir(exist_ok=True)
    tex = stage / "assets/resume.tex"
    for _ in range(2):
        process = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
             f"-output-directory={output}", str(tex)],
            cwd=stage, capture_output=True, env={**os.environ, "SOURCE_DATE_EPOCH": str(source_epoch)},
        )
        if process.returncode:
            detail = (process.stdout + process.stderr).decode("utf-8", errors="replace")[-4000:]
            raise RuntimeError(f"Résumé PDF compilation failed: {detail}")
    built = output / "resume.pdf"
    if not built.is_file():
        raise RuntimeError("xelatex produced no résumé PDF")
    shutil.copyfile(built, destination)
    return destination
