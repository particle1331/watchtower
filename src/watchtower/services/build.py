"""Generate immutable Quarto projects and promote only successful serialized builds.

Quarto sees stored notebook outputs and is always invoked with execution disabled.
Authored files are read exclusively through ContentService's validated snapshot.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import nbformat
import yaml
from jinja2 import DictLoader, Environment
from markdown_it import MarkdownIt

from watchtower.models import (
    course_rows,
    displayed_text,
    eligible,
    route_for,
    source_path,
)
from watchtower.services.content import KANBAN, ContentService
from watchtower.services.profile import build_resume_pdf, latex_profile
from watchtower.services.workspace import ServiceError

_MODES = {"preview", "production"}
_LINK = re.compile(r"(!?\[[^\]]*\])\(([^\s)]+)([^)]*)\)")
_HTML_REF = re.compile(r"((?:src|href)=[\"'])([^\"']+)([\"'])")
_INCLUDE = re.compile(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    _write(temp, json.dumps(value, indent=2, sort_keys=True))
    os.replace(temp, path)


def _frontmatter(value: dict[str, Any]) -> str:
    return "---\n" + yaml.safe_dump(value, sort_keys=False, allow_unicode=True) + "---\n"


def _href(route: str) -> str:
    return str(PurePosixPath(route).with_suffix(".html"))


def _asset_path(source: str) -> str:
    return source.replace("content/notebooks/", "nb/", 1).removeprefix("content/")


def _generated_cell(artifact_id: str, role: str, source: str) -> nbformat.NotebookNode:
    identifier = hashlib.sha256(f"{artifact_id}:{role}".encode()).hexdigest()[:16]
    return nbformat.v4.new_markdown_cell(source, id=identifier)


def _relative(target: str, route: str) -> str:
    return quote(posixpath.relpath(target, posixpath.dirname(route) or "."), safe="/._-~")


def _source_url(entry: Any, settings: Any) -> str | None:
    if not entry.project_path:
        return None
    encoded = "/".join(quote(part, safe="") for part in entry.project_path.split("/"))
    return f"{settings.repository_url.rstrip('/')}/tree/{quote(settings.source_ref, safe='')}/{encoded}"


def _remove_title_h1s(source: str, title: str) -> tuple[str, bool]:
    tokens = MarkdownIt().parse(source)
    ignored: set[int] = set()
    for index, token in enumerate(tokens):
        if (
            token.type == "heading_open"
            and token.tag == "h1"
            and index + 1 < len(tokens)
            and displayed_text(tokens[index + 1]) == title
            and token.map
        ):
            ignored.update(range(*token.map))
    if not ignored:
        return source, False
    return "\n".join(line for index, line in enumerate(source.splitlines()) if index not in ignored), True


class _Generator:
    """A renderer over one immutable snapshot; no workspace reads occur here."""

    def __init__(self, snapshot: Any, stage: Path, mode: str) -> None:
        self.snapshot = snapshot
        self.state = snapshot.state
        self.files: dict[str, bytes] = snapshot.files
        self.stage = stage
        self.mode = mode
        self.entries = [a for a in self.state.artifacts if eligible(a, self.state.artifacts, mode)]
        self.by_id = {a.id: a for a in self.entries}
        self.details = {e.id: e for e in self.state.portfolio}
        self.routes = {a.id: route_for(a) for a in self.entries if a.kind != "project"}
        self.all_sources = {
            source: artifact
            for artifact in self.state.artifacts
            if (source := source_path(artifact, self.state))
        }
        self.all_targets = dict(self.all_sources)
        for artifact in self.state.artifacts:
            if artifact.kind == "project":
                continue
            target = route_for(artifact)
            self.all_targets[target] = artifact
            self.all_targets[_href(target)] = artifact
        templates = {
            key.removeprefix("frontend/templates/"): value.decode("utf-8")
            for key, value in self.files.items()
            if key.startswith(("frontend/templates/site/", "frontend/templates/shared/"))
        }
        self.env = Environment(loader=DictLoader(templates), autoescape=False)
        self.env.filters["char_codes"] = lambda text: ",".join(str(ord(c)) for c in text)
        self.env.filters["html_entities"] = lambda text: "".join(f"&#{ord(c)};" for c in text)
        self.render_paths: list[str] = []
        self.asset_paths: set[str] = set()

    def template(self, template_name: str, **context: Any) -> str:
        env = self.env
        if template_name.endswith(".tex.j2") or template_name in {"site/index.qmd.j2", "site/resume.qmd.j2"}:
            # Preserve the original profile renderer's compact Markdown lists.
            env = env.overlay(trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
        return env.get_template(template_name).render(**context)

    def write(self, path: str, value: str | bytes, *, render: bool = False) -> None:
        if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise ValueError(f"Unsafe generated route: {path}")
        _write(self.stage / path, value)
        if isinstance(value, bytes) and not path.startswith("templates/"):
            self.asset_paths.add(path)
        if render:
            self.render_paths.append(path)

    def copy_reference(self, reference: str, source: str, route: str, *, required: bool = False) -> None:
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("#"):
            return
        raw = unquote(parsed.path)
        if raw.startswith("/"):
            resolved = raw.lstrip("/")
            destination = resolved
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), raw))
            destination = posixpath.normpath(posixpath.join(posixpath.dirname(route), raw))
        if destination.startswith("../") or destination == "..":
            raise ServiceError(f"Asset reference escapes generated project: {reference}", paths=[source])
        if resolved not in self.files:
            # Absolute/shared site assets are generated from the same snapshot
            # before notebooks; they need not also live under content/.
            if required and (self.stage / destination).is_file():
                return
            if required:
                raise ServiceError(f"{source}: referenced asset does not exist: {reference}", paths=[resolved])
            return
        if resolved in self.all_sources:
            return
        if resolved.startswith(("archive/", "projects/", "content/data/", "frontend/templates/cms/")):
            return
        self.write(destination, self.files[resolved])

    def rewrite_body(self, body: str, source: str, route: str) -> str:
        def link(match: re.Match[str]) -> str:
            label, target, suffix = match.groups()
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                return match.group(0)
            resolved = (
                parsed.path.lstrip("/")
                if parsed.path.startswith("/")
                else posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path)))
            )
            render_resolved = posixpath.normpath(posixpath.join(posixpath.dirname(route), unquote(parsed.path)))
            artifact = self.all_targets.get(resolved) or self.all_targets.get(render_resolved)
            if artifact:
                if artifact.id not in self.routes:
                    return label.removeprefix("!").removeprefix("[").removesuffix("]")
                target = _relative(self.routes[artifact.id], route)
                if parsed.fragment:
                    target += "#" + parsed.fragment
                return f"{label}({target}{suffix})"
            self.copy_reference(target, source, route, required=label.startswith("!"))
            return match.group(0)

        body = _LINK.sub(link, body)
        def html_reference(match: re.Match[str]) -> str:
            prefix, reference, suffix = match.groups()
            parsed = urlsplit(reference)
            if not parsed.scheme and not parsed.netloc and parsed.path:
                resolved = parsed.path.lstrip("/") if parsed.path.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path)))
                render_resolved = posixpath.normpath(posixpath.join(posixpath.dirname(route), unquote(parsed.path)))
                artifact = self.all_targets.get(resolved) or self.all_targets.get(render_resolved)
                if artifact:
                    target = _relative(_href(self.routes[artifact.id]), route) if artifact.id in self.routes else "#"
                    if artifact.id in self.routes and parsed.fragment:
                        target += "#" + parsed.fragment
                    return prefix + target + suffix
            self.copy_reference(reference, source, route, required=prefix.startswith("src="))
            return match.group(0)

        body = _HTML_REF.sub(html_reference, body)
        for reference in _INCLUDE.findall(body):
            self.copy_reference(reference, source, route)
        return body

    def context(self, artifact: Any) -> str:
        contract = self.state.courses[artifact.id]
        value = ["## Course context"]
        for label, record in (("Actualized", contract.actualized),):
            value.extend(["", f"### {label}"])
            for key, text in record.items():
                if key == "chapters" or not text:
                    continue
                if isinstance(text, str):
                    value.extend(["", f"**{key.replace('_', ' ').capitalize()}.** {text}"])
                elif isinstance(text, list):
                    value.extend(["", f"**{key.replace('_', ' ').capitalize()}**", ""])
                    value.extend(f"- {item}" for item in text)
        value.extend(["", "## Course path", ""])
        rows = course_rows(contract, self.entries)
        if rows:
            value.extend(["| Section | Chapter title | Summary |", "| --- | --- | --- |"])
            def cell(text: str) -> str:
                # Treat authored labels as text, not executable Markdown/HTML.
                return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", escape(text)).replace("\n", "<br>")
            for row in rows:
                child = row["chapter"]
                title = self.navigation_title(self.by_id[child["id"]], cell(child["title"]))
                link = _relative(self.routes[child["id"]], self.routes[artifact.id])
                summary = row["summary"] or ("Summary not added yet." if self.mode == "preview" else "")
                value.append(f"| {cell(row['section'])} | [{title}]({link}) | {cell(summary)} |")
        else:
            value.append("No chapters to display yet.")
        return "\n".join(value) + "\n"

    @staticmethod
    def navigation_title(artifact: Any, title: str) -> str:
        if artifact.lifecycle == "draft":
            return escape(title) + ' <span class="draft-badge">draft</span>'
        return title

    def metadata(self, artifact: Any, route: str) -> dict[str, Any]:
        value: dict[str, Any] = {"title": artifact.title, "toc": True, "lifecycle": artifact.lifecycle}
        # Portfolio entry pages show their abstract as body content from portfolio
        # YAML; a front-matter description would render it a second time.
        if artifact.description and artifact.kind != "portfolio":
            value["description"] = artifact.description
        if artifact.date:
            value["date"] = str(artifact.date)
        if artifact.tags:
            value["categories"] = artifact.tags
        if artifact.kind == "chapter":
            value["format"] = {"html": {"template-partials": ["/templates/title-block.html"]}}
        if artifact.kind in {"post", "personal"}:
            value["author"] = self.state.profile.name
        if artifact.kind == "course":
            value["sidebar"] = artifact.id.replace("/", "-")
            value["description"] = artifact.description or ""
        cover = getattr(artifact, "cover", None) or getattr(artifact, "image", None)
        if cover:
            value["image"] = "/" + _asset_path(cover)
            if cover in self.files:
                self.write(_asset_path(cover), self.files[cover])
        return value

    def gallery(self, artifact: Any) -> None:
        route = self.routes[artifact.id]
        photos: list[dict[str, Any]] = []
        for photo in self.state.photos:
            if photo.lifecycle == "draft" and self.mode == "production":
                continue
            src = ""
            if photo.path:
                destination = _asset_path(photo.path)
                self.write(destination, self.files[photo.path])
                src = _relative(destination, route)
            photos.append({
                "src": src,
                "caption": photo.caption,
                "heading": photo.heading,
                "lifecycle": photo.lifecycle,
                "width": getattr(photo, "width", None),
            })
        self.write(route, self.template("site/personal.qmd.j2", photos=photos, title=artifact.title), render=True)

    def notebook(self, artifact: Any) -> None:
        route = self.routes[artifact.id]
        source = source_path(artifact, self.state)
        if not source:
            raise ValueError(f"Missing notebook source for {artifact.id}")
        notebook = copy.deepcopy(nbformat.reads(self.files[source].decode("utf-8"), as_version=4))
        cells = []
        for cell in notebook.cells:
            if cell.cell_type == "markdown":
                if artifact.kind != "chapter":
                    cell.source, removed_title = _remove_title_h1s(cell.source, artifact.title)
                    if removed_title and not cell.source.strip():
                        continue
                cell.source = self.rewrite_body(cell.source, source, route)
            for output in cell.get("outputs", []):
                for mimetype in ("text/html", "text/markdown"):
                    body = output.get("data", {}).get(mimetype)
                    if isinstance(body, str):
                        self.rewrite_body(body, source, route)
            cells.append(cell)
        notebook.cells = cells
        header = _frontmatter(self.metadata(artifact, route))
        if artifact.lifecycle != "published" or artifact.visibility != "public":
            if artifact.kind == "portfolio" or artifact.lifecycle == "draft":
                header += "\n" + self.template("site/publication-meta.html.j2", entry=artifact) + "\n"
            else:
                header += f"\n::: {{.callout-note}}\n**{artifact.lifecycle.capitalize()}**"
                if artifact.visibility != "public":
                    header += " · Private working preview"
                header += "\n:::\n"
        if artifact.kind in {"post", "portfolio", "personal"}:
            gallery = next((entry for entry in self.entries if entry.kind == "gallery"), None)
            listing = {"post": "posts.qmd", "portfolio": "portfolio.qmd", "personal": self.routes[gallery.id] if gallery else None}[artifact.kind]
            back_url = (
                _relative(listing, route)
                if listing and not any(f"[← {artifact.kind.capitalize()}]" in cell.source for cell in notebook.cells)
                else None
            )
            if artifact.kind == "portfolio":
                detail = self.details.get(artifact.id)
                figure_url = None
                if detail and detail.figure_path:
                    destination = _asset_path(detail.figure_path)
                    self.write(destination, self.files[detail.figure_path])
                    figure_url = _relative(destination, route)
                header += "\n" + self.template(
                    "site/portfolio-page-header.md.j2", back_url=back_url, detail=detail,
                    source_url=_source_url(detail, self.state.settings) if detail else None,
                    figure_url=figure_url, description=artifact.description,
                ) + "\n"
            elif back_url:
                header += f"\n[← {artifact.kind.capitalize()}]({back_url})\n"
        notebook.cells.insert(0, _generated_cell(artifact.id, "header", header))
        if artifact.kind == "course":
            context = self.context(artifact)
            # Old generated include directives resolve to the new immutable context.
            include = posixpath.join(posixpath.dirname(route), "_course-context.md")
            self.write(include, context)
            has_include = any("_course-context.md" in c.source for c in notebook.cells)
            if not has_include:
                notebook.cells.insert(1, _generated_cell(artifact.id, "course-context", context))
        self.write(route, nbformat.writes(notebook), render=True)

    def portfolio(self) -> None:
        entries = []
        for detail in self.state.portfolio:
            artifact = self.by_id.get(detail.id)
            if not artifact:
                continue
            if self.mode == "production" and artifact.lifecycle != "published":
                continue
            data = artifact.model_dump(mode="json")
            data.update(detail.model_dump(mode="json"))
            data["anchor"] = artifact.id.replace("/", "-")
            data["route"] = self.routes[artifact.id]
            data["abstract"] = detail.abstract or artifact.description or "Project description not added yet."
            data["figure"] = None
            if detail.figure_path:
                destination = _asset_path(detail.figure_path)
                self.write(destination, self.files[detail.figure_path])
                data["figure"] = destination
            data["source_url"] = _source_url(detail, self.state.settings)
            data["project_name"] = detail.project_path.rsplit("/", 1)[-1] if detail.project_path else None
            entries.append(data)
        self.write("portfolio.qmd", self.template("site/portfolio.qmd.j2", entries=entries), render=True)

    def config(self) -> None:
        config = copy.deepcopy(self.state.settings.quarto)
        html = config.setdefault("format", {}).setdefault("html", {})
        css = html.get("css")
        styles = self.files.get("frontend/assets/styles.css")
        if styles is not None and (css == "assets/styles.css" or isinstance(css, list) and "assets/styles.css" in css):
            versioned = f"assets/styles-{hashlib.sha256(styles).hexdigest()[:16]}.css"
            self.write(versioned, styles)
            html["css"] = [versioned if item == "assets/styles.css" else item for item in css] if isinstance(css, list) else versioned
        config["execute"] = {"enabled": False}
        config["project"] = {
            "type": "website", "output-dir": "_site", "render": self.render_paths,
            "resources": ["assets/**", *sorted(p for p in self.asset_paths if not p.startswith("assets/")), "!assets/resume.tex", "!assets/preview-reload.html"],
        }
        website = config.setdefault("website", {})
        website["draft-mode"] = "visible" if self.mode == "preview" else "gone"
        gallery = next((entry for entry in self.entries if entry.kind == "gallery"), None)
        website["navbar"] = yaml.safe_load(self.template(
            "shared/navigation.yaml.j2", **self.state.settings.model_dump(mode="json"),
            personal_route=self.routes[gallery.id] if gallery else None,
        ))
        sidebars = []
        for artifact in self.entries:
            if artifact.kind != "course":
                continue
            contents: list[dict[str, Any]] = [{"href": self.routes[artifact.id], "text": self.navigation_title(artifact, artifact.title)}]
            for section in self.state.courses[artifact.id].toc:
                children = [
                    {"href": self.routes[c], "text": self.navigation_title(self.by_id[c], self.by_id[c].toc_title)}
                    for c in section.chapters if c in self.by_id
                ]
                if not children:
                    continue
                if section.title:
                    contents.append({"section": section.title, "contents": children})
                else:
                    contents.extend(children)
            sidebars.append({"id": artifact.id.replace("/", "-"), "style": "floating", "collapse-level": 2, "contents": contents})
        website["sidebar"] = sidebars
        if self.mode == "preview":
            config.setdefault("format", {}).setdefault("html", {})["include-after-body"] = "assets/preview-reload.html"
        self.write("_quarto.yml", yaml.safe_dump(config, sort_keys=False, allow_unicode=True))

    def generate(self) -> Path:
        for key, value in self.files.items():
            if key.startswith("frontend/assets/"):
                self.write("assets/" + key.removeprefix("frontend/assets/"), value)
        partial = self.files.get("frontend/templates/site/title-block.html", b"")
        self.write("templates/title-block.html", partial)
        profile = self.state.profile.model_dump(mode="json", exclude_none=True)
        # Free prose retains authored Markdown, while contact script values use codes.
        self.write("index.qmd", self.template("site/index.qmd.j2", **profile), render=True)
        self.write("resume.qmd", self.template("site/resume.qmd.j2", **profile), render=True)
        self.write("assets/contact.js", self.template("site/contact.js.j2", **profile))
        self.write("assets/resume.tex", self.template("site/resume.tex.j2", **latex_profile(self.state.profile)))
        for artifact in self.entries:
            if artifact.kind == "gallery":
                self.gallery(artifact)
            elif artifact.kind != "project":
                self.notebook(artifact)
        posts = []
        for artifact in self.entries:
            if artifact.kind == "post":
                data = {
                    "path": "/" + self.routes[artifact.id],
                    "outputHref": "/" + _href(self.routes[artifact.id]),
                    "title": self.navigation_title(artifact, artifact.title),
                    "description": artifact.description or "",
                    "categories": artifact.tags,
                }
                if artifact.date:
                    data["date"] = str(artifact.date)
                source = source_path(artifact, self.state)
                if source:
                    saved = nbformat.reads(self.files[source].decode("utf-8"), as_version=4)
                    prose = " ".join(cell.source for cell in saved.cells if cell.cell_type == "markdown")
                else:
                    prose = ""
                data["reading-time"] = max(1, (len(re.findall(r"\w+", prose)) + 199) // 200)
                posts.append(data)
        posts.sort(key=lambda p: (p.get("date") or "", p["title"]), reverse=True)
        self.write("posts.qmd", self.template("site/posts.qmd.j2", posts=posts), render=True)
        self.portfolio()
        courses = [
            {"path": _href(self.routes[a.id]), "outputHref": _href(self.routes[a.id]),
             "title": self.navigation_title(a, a.title),
             "description": a.description or "",
             **({"image": _asset_path(a.cover)} if getattr(a, "cover", None) else {})}
            for a in self.entries if a.kind == "course"
        ]
        self.write("courses.qmd", self.template("site/courses.qmd.j2", courses=courses), render=True)
        self.write("assets/preview-reload.html", '''<script>
(async function () {
  let revision;
  setInterval(async () => {
    try {
      const response = await fetch('/__watchtower_revision', {cache: 'no-store'});
      const current = await response.text();
      if (revision !== undefined && revision !== current) location.reload();
      revision = current;
    } catch (_) { /* Retain the last successful page while rendering. */ }
  }, 1000);
})();
</script>''')
        self.config()
        self.write(".watchtower-revision", self.snapshot.revision)
        return self.stage


class BuildService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.runtime = self.root / "backend/runtime/builds"
        self.generated = self.root / "frontend/generated"

    def _mode(self, mode: str) -> None:
        if mode not in _MODES:
            raise ServiceError("Build mode must be preview or production", code="invalid_build_mode")

    @contextmanager
    def _lock(self):
        self.runtime.mkdir(parents=True, exist_ok=True)
        with (self.runtime / "workspace.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def generate(self, mode: str = "preview") -> Path:
        self._mode(mode)
        snapshot = ContentService(self.root).snapshot()
        stage = self.generated / "jobs" / uuid.uuid4().hex
        stage.mkdir(parents=True)
        return _Generator(snapshot, stage, mode).generate()

    def _record(self, mode: str) -> dict[str, Any]:
        self._mode(mode)
        job_id = uuid.uuid4().hex
        record = {
            "id": job_id, "operation": "preview" if mode == "preview" else "build", "mode": mode,
            "status": "queued", "created_at": _now(), "started_at": None, "finished_at": None,
            "log_location": str(self.runtime / f"{job_id}.log"), "error": None,
            "output_location": None, "revision": None, "logs": "",
            "preview_url": "http://127.0.0.1:4300" if mode == "preview" else None,
        }
        _atomic_json(self.runtime / f"{job_id}.json", record)
        return record

    def get(self, job_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ServiceError("Invalid build ID", code="invalid_build_id", status=400)
        path = self.runtime / f"{job_id}.json"
        if not path.is_file():
            raise ServiceError(f"Unknown build: {job_id}", code="not_found", status=404)
        record = json.loads(path.read_text(encoding="utf-8"))
        log = Path(record["log_location"])
        if log.exists():
            record["logs"] = log.read_text(encoding="utf-8", errors="replace")[-16000:]
        preview = self.runtime.parent / "preview.json"
        if record["mode"] == "preview" and preview.exists():
            record["preview_url"] = json.loads(preview.read_text())["url"]
        return record

    def last_successful(self, mode: str = "preview") -> dict[str, Any] | None:
        self._mode(mode)
        records = []
        for path in self.runtime.glob("*.json"):
            record = json.loads(path.read_text())
            if record["mode"] == mode and record["status"] == "succeeded":
                records.append(record)
        if not records:
            return None
        latest = max(records, key=lambda record: record["finished_at"])
        return self.get(latest["id"])

    def _run(self, job_id: str) -> dict[str, Any]:
        record = self.get(job_id)
        with self._lock():
            record.update(status="running", started_at=_now())
            _atomic_json(self.runtime / f"{job_id}.json", record)
            try:
                stage = self.generate(record["mode"])
                record["revision"] = (stage / ".watchtower-revision").read_text()
                build_resume_pdf(stage)
                with Path(record["log_location"]).open("ab") as log:
                    process = subprocess.run(["quarto", "render", "--no-execute"], cwd=stage, stdout=log, stderr=subprocess.STDOUT, check=False)
                if process.returncode:
                    tail = Path(record["log_location"]).read_text(errors="replace")[-4000:]
                    raise RuntimeError(f"Quarto exited with status {process.returncode}. {tail}")
                if not (stage / "_site/index.html").is_file():
                    raise RuntimeError("Quarto did not produce the site home page")
                # Validate the current saved workspace before promotion; a conflicted
                # recovery journal must never replace the last successful preview.
                ContentService(self.root).snapshot()
                target = self.generated / record["mode"]
                temporary = self.generated / f".{record['mode']}.{job_id}"
                temporary.symlink_to(stage.relative_to(self.generated), target_is_directory=True)
                os.replace(temporary, target)
                record.update(status="succeeded", output_location=str(target / "_site"))
            except Exception as error:
                record.update(status="failed", error=str(error))
                with Path(record["log_location"]).open("a") as log:
                    log.write(f"\n{type(error).__name__}: {error}\n")
            record["finished_at"] = _now()
            _atomic_json(self.runtime / f"{job_id}.json", record)
        return self.get(job_id)

    def build(self, mode: str = "preview") -> dict[str, Any]:
        return self._run(self._record(mode)["id"])

    def submit(self, mode: str = "preview") -> dict[str, Any]:
        record = self._record(mode)
        # A separate worker survives the short-lived CLI and shares the same
        # filesystem lock with workers submitted by API/CMS clients.
        with Path(record["log_location"]).open("ab") as log:
            try:
                subprocess.Popen(
                    [sys.executable, "-m", "watchtower.services.build", str(self.root), record["id"]],
                    cwd=self.root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                    env={**os.environ, "PYTHONPATH": str(self.root / "src")},
                )
            except OSError as error:
                record.update(status="failed", error=str(error), finished_at=_now())
                _atomic_json(self.runtime / f"{record['id']}.json", record)
        return record

    def _preview_signature(self) -> str:
        digest = hashlib.sha256()
        for folder in (
            self.root / "content", self.root / "frontend/templates", self.root / "frontend/assets",
            self.root / "src/watchtower",
        ):
            for path in sorted(folder.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts and path.relative_to(self.root).as_posix() != KANBAN:
                    stat = path.stat()
                    digest.update(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode())
        settings = self.root / "frontend/site.yaml"
        if settings.exists():
            digest.update(settings.read_bytes())
        return digest.hexdigest()

    def preview(self, port: int = 4300) -> None:
        _atomic_json(self.runtime.parent / "preview.json", {"url": f"http://127.0.0.1:{port}"})
        result = self.build("preview")
        if result["status"] != "succeeded":
            raise RuntimeError(result["error"])
        service = self
        stopped = threading.Event()


        def watch() -> None:
            previous = self._preview_signature()
            while not stopped.wait(0.5):
                current = self._preview_signature()
                if current != previous:
                    # Let IDE atomic saves settle before snapshotting the workspace.
                    if stopped.wait(0.25):
                        break
                    previous = self._preview_signature()
                    # Load current Python code, just like CMS-triggered builds.
                    service.submit("preview")

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(service.generated / "preview/_site"), **kwargs)

            def do_GET(self) -> None:
                if urlsplit(self.path).path == "/__watchtower_revision":
                    target = service.generated / "preview"
                    revision = target.resolve().name.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(revision)
                else:
                    super().do_GET()

        watcher = threading.Thread(target=watch, name="watchtower-preview-watch", daemon=True)
        watcher.start()
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        print(f"Watchtower preview: http://127.0.0.1:{port} (stored outputs; cells never execute)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stopped.set()
            server.server_close()


if __name__ == "__main__":
    BuildService(Path(sys.argv[1]))._run(sys.argv[2])
