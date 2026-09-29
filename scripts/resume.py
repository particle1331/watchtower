"""Resume builder — YAML is the single source for résumé content.

`make resume` renders assets/resume.yaml into the site home, résumé page,
contact script, and moderncv LaTeX, then runs xelatex for the PDF.
The home and posts pages also select published posts. Edit the YAML
for résumé content; never hand-edit generated files.
"""


import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import nbformat
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT_PATH = Path(__file__).resolve().parents[1]

RESUME_YAML     = Path("assets/resume.yaml")
RESUME_TEX_J2   = Path("assets/resume.tex.j2")
RESUME_TEX      = Path("assets/resume.tex")
RESUME_PDF      = Path("assets/resume.pdf")
INDEX_QMD_J2    = Path("assets/index.qmd.j2")
INDEX_QMD       = Path("index.qmd")
RESUME_QMD_J2   = Path("assets/resume.qmd.j2")
RESUME_QMD      = Path("resume.qmd")
CONTACT_JS_J2   = Path("assets/contact.js.j2")
CONTACT_JS      = Path("assets/contact.js")
POSTS_QMD_J2    = Path("assets/posts.qmd.j2")
POSTS_QMD       = Path("posts.qmd")

LATEX_ENGINE = "xelatex"

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


def _published_posts(root: Path) -> list[dict[str, str]]:
    """Select only catalog-published public posts for the site listing."""
    posts: list[tuple[date, str, str]] = []
    catalog = yaml.safe_load((root / "knowledge/catalog.yaml").read_text(encoding="utf-8"))
    for item in catalog["artifacts"]:
        if item.get("kind") != "post" or item.get("visibility") != "public" or item.get("lifecycle") != "published":
            continue
        path = root / item["path"]
        notebook = nbformat.read(path, as_version=nbformat.NO_CONVERT)
        if not notebook.cells or notebook.cells[0].cell_type != "markdown":
            continue
        source = notebook.cells[0].source
        if not source.startswith("---\n"):
            continue
        frontmatter = source.split("---", 2)
        if len(frontmatter) < 3:
            continue
        metadata = yaml.safe_load(frontmatter[1])
        if not isinstance(metadata, dict) or metadata.get("draft"):
            continue
        if not metadata.get("title") or not metadata.get("date"):
            continue
        published = date.fromisoformat(str(metadata["date"]))
        posts.append((published, str(metadata["title"]), path.relative_to(root).as_posix()))
    posts.sort(reverse=True)
    return [
        {"title": title, "date": f"{published:%b} {published.day}, {published.year}", "url": url}
        for published, title, url in posts
    ]


def _make_env(root: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader([str(root / "assets"), str(root)]),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    env.filters["md_escape"]     = _md_escape
    env.filters["latex_text"]    = _latex_text
    env.filters["html_entities"] = _html_entities
    env.filters["char_codes"] = lambda value: ", ".join(str(ord(char)) for char in value)
    return env


def _run_xelatex(tex: Path, out_dir: Path, source_epoch: int) -> None:
    # SOURCE_DATE_EPOCH makes XeTeX stamp /CreationDate, /ModDate, and /ID
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
        cwd=ROOT_PATH,
    )


def build_resume() -> tuple[Path, Path]:
    """Render YAML into the site pages, contact script, and PDF."""
    root = ROOT_PATH
    tex_src = root / RESUME_TEX_J2
    qmd_src = root / INDEX_QMD_J2
    yaml_path = root / RESUME_YAML
    resume_qmd_src = root / RESUME_QMD_J2
    contact_js_src = root / CONTACT_JS_J2
    posts_qmd_src = root / POSTS_QMD_J2
    for p in (tex_src, qmd_src, resume_qmd_src, contact_js_src, posts_qmd_src, yaml_path):
        if not p.exists():
            raise FileNotFoundError(f"resume source missing: {p}")
    if not shutil.which(LATEX_ENGINE):
        raise FileNotFoundError(
            f"{LATEX_ENGINE} not found on PATH — install TeX Live or MiKTeX."
        )

    data = _load_yaml(yaml_path)
    env = _make_env(root)

    # Pin PDF timestamps to the newest source mtime so reruns are reproducible.
    source_epoch = int(max(p.stat().st_mtime for p in (tex_src, qmd_src, resume_qmd_src, contact_js_src, yaml_path, root / "assets/fonts/Ubuntu-Bold.ttf")))

    # Render index.qmd (web version with markdown escaping).
    web_data = _escape_for_target(data, _md_escape)
    web_data["posts"] = _published_posts(root)
    web_data["latest_posts"] = web_data["posts"][:3]
    qmd_template = env.get_template(INDEX_QMD_J2.name)
    qmd_rendered = qmd_template.render(**web_data)
    index_path = root / INDEX_QMD
    index_path.write_text(qmd_rendered, encoding="utf-8")
    resume_template = env.get_template(RESUME_QMD_J2.name)
    (root / RESUME_QMD).write_text(resume_template.render(**web_data), encoding="utf-8")
    posts_template = env.get_template(POSTS_QMD_J2.name)
    (root / POSTS_QMD).write_text(posts_template.render(**web_data), encoding="utf-8")
    contact_template = env.get_template(CONTACT_JS_J2.name)
    (root / CONTACT_JS).write_text(contact_template.render(**data), encoding="utf-8")

    # Render resume.tex (PDF version with LaTeX escaping).
    tex_template = env.get_template(RESUME_TEX_J2.name)
    tex_rendered = tex_template.render(**_escape_for_target(data, _latex_text))
    (root / RESUME_TEX).write_text(tex_rendered, encoding="utf-8")
    # Keep the build path stable for reproducible PDF output.
    tmp_dir = root / ".tmp" / "resume-build"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        tex_copy = tmp_dir / "resume.tex"
        tex_copy.write_text(tex_rendered, encoding="utf-8")
        _run_xelatex(tex_copy, tmp_dir, source_epoch)
        _run_xelatex(tex_copy, tmp_dir, source_epoch)  # 2nd pass for cross-refs / page count.
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


def main() -> None:
    try:
        pdf, index = build_resume()
    except (OSError, ValueError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        print(f"command failed: {error.cmd[0]}", file=sys.stderr)
        output = "\n".join(
            stream.decode(errors="replace") if isinstance(stream, bytes) else stream
            for stream in (error.stdout, error.stderr)
            if stream
        )
        if output:
            print("xelatex output (last 50 lines):", file=sys.stderr)
            print("\n".join(output.splitlines()[-50:]), file=sys.stderr)
        raise SystemExit(error.returncode) from error
    print(f"resume PDF: {pdf}")
    print(f"home page: {index}")
    print(f"résumé page: {index.parent / RESUME_QMD}")
    print(f"posts page: {index.parent / POSTS_QMD}")


if __name__ == "__main__":
    main()
