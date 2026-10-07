"""Reviewable, read-only migration from the legacy content layout.

Preparing candidates does not adopt archived claims, infer publication state,
write source notebooks, or remove legacy inputs. The caller must resolve the
reported blockers before committing a candidate through the repository service.
"""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jupytext
import nbformat
from markdown_it import MarkdownIt
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from watchtower.notebook import read_notebook

DOCUMENT_FIELDS = {"title", "description", "date", "categories", "tags", "image", "image-alt", "image_alt", "author", "format", "toc", "page-layout", "execute", "jupyter"}
CATALOG_FIELDS = {"description", "date", "categories", "tags", "cover"}
HISTORICAL_PROJECTS = {"portfolio/autocode": "autocode", "portfolio/change-planner": "change-planner", "portfolio/ml-platform": "ml-platform"}
HEADER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def load_yaml(text: str) -> dict[str, Any]:
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    value = parser.load(text)
    if not isinstance(value, dict):
        raise ValueError("expected a YAML mapping")
    return value


def yaml_bytes(value: dict[str, Any]) -> bytes:
    import io

    stream = io.StringIO()
    parser = YAML()
    parser.default_flow_style = False
    parser.dump(value, stream)
    return stream.getvalue().encode("utf-8")


def document_header(source: str) -> tuple[dict[str, Any], str]:
    """Remove actual document YAML only, leaving horizontal rules untouched."""
    match = HEADER.match(source)
    if not match:
        return {}, source
    try:
        header = load_yaml(match.group(1))
    except ValueError:
        # A horizontal rule around ordinary prose is not document metadata.
        if not re.search(r"(?m)^(?:title|date|description|format|toc):", match.group(1)):
            return {}, source
        raise
    if not DOCUMENT_FIELDS.intersection(header):
        return {}, source
    return header, source[match.end():]


def read_source_notebook(path: Path) -> nbformat.NotebookNode:
    """Use supported notebook/Jupytext parsers, without changing the source."""
    if path.suffix == ".ipynb":
        return read_notebook(path)
    if path.suffix == ".qmd":
        notebook = jupytext.read(path, fmt="md")
        # Jupytext's Quarto reader may create v4 notebooks without cell IDs.
        for index, cell in enumerate(notebook.cells):
            cell.setdefault("id", hashlib.sha256(f"{path.name}:{index}:{cell.source}".encode()).hexdigest()[:12])
        notebook.nbformat_minor = max(notebook.nbformat_minor, 5)
        return notebook
    raise ValueError(f"unsupported migration source: {path}")


def displayed_text(inline: Any) -> str:
    if not inline.children:
        return inline.content
    return "".join(token.content for token in inline.children if token.type in {"text", "code_inline", "image"})


def h1_titles(notebook: nbformat.NotebookNode) -> list[str]:
    """Read real Markdown headings, including Setext, ignoring fenced code."""
    titles = []
    for cell in notebook.cells:
        if cell.cell_type != "markdown":
            continue
        tokens = MarkdownIt().parse(cell.source)
        for index, token in enumerate(tokens):
            if token.type == "heading_open" and token.tag == "h1":
                titles.append(displayed_text(tokens[index + 1]))
    return titles


def normalize_notebook(notebook: nbformat.NotebookNode, *, chapter_title: str | None = None) -> tuple[nbformat.NotebookNode, dict[str, Any]]:
    """Extract front matter and add an agreed missing chapter H1 in memory.

    Existing cells (including a now-empty header cell), IDs, options, metadata,
    execution counts, outputs, and attachments are retained. Conflicting titles
    fail before a candidate is returned.
    """
    candidate = copy.deepcopy(notebook)
    header: dict[str, Any] = {}
    if candidate.cells and candidate.cells[0].cell_type == "markdown":
        header, candidate.cells[0].source = document_header(candidate.cells[0].source)
    if chapter_title is not None:
        if header.get("title") is not None and header["title"] != chapter_title:
            raise ValueError(f"front matter title {header['title']!r} conflicts with catalog title {chapter_title!r}")
        titles = h1_titles(candidate)
        if titles and titles != [chapter_title]:
            raise ValueError(f"chapter H1 {titles!r} must equal [{chapter_title!r}]")
        if not titles:
            if candidate.cells and candidate.cells[0].cell_type == "markdown" and not candidate.cells[0].source.strip():
                candidate.cells[0].source = f"# {chapter_title}\n"
            else:
                cell = nbformat.v4.new_markdown_cell(f"# {chapter_title}\n")
                cell.id = "title-" + hashlib.sha256(chapter_title.encode()).hexdigest()[:12]
                candidate.cells.insert(0, cell)
    return candidate, header


def extract_photos(notebook: nbformat.NotebookNode) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Extract ordered Markdown/HTML images and retain prose for human review."""
    photos: list[dict[str, str]] = []
    prose: list[dict[str, Any]] = []
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "markdown":
            if cell.get("source", "").strip() or cell.get("outputs") or cell.get("attachments"):
                prose.append({"cell": index, "source": cell.get("source", ""), "reason": "non-Markdown gallery content"})
            continue
        source = document_header(cell.source)[1] if index == 0 else cell.source
        tokens = MarkdownIt("commonmark", {"html": True}).parse(source)
        image_lines = set()
        for token in tokens:
            for child in token.children or []:
                if child.type == "image":
                    photos.append({"path": str(child.attrGet("src") or ""), "caption": child.content})
                    if token.map:
                        image_lines.update(range(*token.map))
            if token.type in {"html_block", "inline"}:
                for match in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", token.content, re.I):
                    alt = re.search(r"\balt=[\"']([^\"']*)[\"']", match.group(), re.I)
                    photos.append({"path": match.group(1), "caption": alt.group(1) if alt else ""})
                    if token.map:
                        image_lines.update(range(*token.map))
        remainder = "\n".join(line for line_index, line in enumerate(source.splitlines()) if line_index not in image_lines).strip()
        if remainder:
            prose.append({"cell": index, "source": remainder, "reason": "gallery prose requires preservation decision"})
        if cell.get("attachments"):
            prose.append({"cell": index, "reason": "gallery attachments require extraction", "attachment_names": list(cell.attachments)})
    return photos, prose


class Migration:
    def __init__(self, root: Path, *, reviewed_portfolio_figures: bool = False, preserve_gallery_as_personal: bool = False, title_choices: dict[str, str] | None = None):
        self.root = Path(root).resolve()
        self.reviewed_portfolio_figures = reviewed_portfolio_figures
        self.preserve_gallery_as_personal = preserve_gallery_as_personal
        self.title_choices = title_choices or {}

    def _yaml(self, path: str) -> dict[str, Any]:
        return load_yaml((self.root / path).read_text(encoding="utf-8"))

    def inventory(self) -> dict[str, Any]:
        return self.prepare()["report"]

    def prepare(self) -> dict[str, Any]:
        """Return candidate bytes and review findings; never write any files."""
        artifacts = copy.deepcopy(self._yaml("knowledge/catalog.yaml")["artifacts"])
        report: dict[str, Any] = {"artifacts": [], "notebooks": [], "assets": [], "courses": [], "photos": [], "profile": {}, "presentation_exceptions": [], "blockers": [], "warnings": []}
        files: dict[str, bytes] = {}
        by_path = {item.get("path"): item for item in artifacts}
        portfolio: list[dict[str, Any]] = []
        historical_captions: dict[str, str] = {}
        if self.reviewed_portfolio_figures:
            reference = self.root / "archive/2026-09-30/nb/portfolio/portfolio.ipynb"
            if reference.exists():
                historical_photos, _ = extract_photos(read_source_notebook(reference))
                historical_captions = {Path(photo["path"]).name: photo["caption"] for photo in historical_photos}

        def block(path: str, field: str, message: str) -> None:
            report["blockers"].append({"path": path, "field": field, "message": message})

        def copy_asset(source: Path) -> str:
            resolved = source.resolve()
            if not resolved.is_relative_to(self.root):
                raise ValueError("asset path escapes repository root")
            relative = resolved.relative_to(self.root).as_posix()
            if relative.startswith("nb/"):
                target = "content/notebooks/" + relative.removeprefix("nb/")
            else:
                target = "content/assets/" + relative.removeprefix("assets/")
            files[target] = source.read_bytes()
            if not any(asset["source"] == relative for asset in report["assets"]):
                report["assets"].append({"source": relative, "target": target, "sha256": hashlib.sha256(files[target]).hexdigest(), "reason": "preserve sibling asset and relative source references"})
            return target

        # Keep authored sibling assets at their matching relative notebook path.
        # Context includes are generated anew and course contracts move to data.
        legacy_notebooks = self.root / "nb"
        for asset in legacy_notebooks.rglob("*"):
            relative = asset.relative_to(legacy_notebooks)
            if not asset.is_file() or any(part.startswith(".") for part in relative.parts):
                continue
            if asset.suffix in {".ipynb", ".qmd"} or asset.name in {"course.yaml", "_course-context.md"}:
                continue
            try:
                copy_asset(asset)
            except (ValueError, OSError) as exc:
                block(asset.relative_to(self.root).as_posix(), "asset", str(exc))

        def migrate_notebook(source: str, target: str, item: dict[str, Any]) -> None:
            try:
                if not (self.root / source).resolve().is_relative_to(self.root):
                    raise ValueError("source path escapes repository root")
                original = read_source_notebook(self.root / source)
                candidate, header = normalize_notebook(original, chapter_title=item["title"] if item["kind"] == "chapter" else None)
            except (ValueError, OSError, YAMLError) as exc:
                block(source, "notebook", str(exc))
                return
            report["notebooks"].append({"id": item["id"], "source": source, "target": target, "header": header, "h1s": h1_titles(candidate), "cells": len(original.cells), "source_sha256": hashlib.sha256((self.root / source).read_bytes()).hexdigest(), "candidate_sha256": hashlib.sha256(nbformat.writes(candidate).encode()).hexdigest()})
            for key, value in header.items():
                field = "cover" if key == "image" else key
                if field == "title":
                    if value != item["title"]:
                        choice = self.title_choices.get(item["id"])
                        if choice == item["title"] or choice == value:
                            report["warnings"].append({"path": source, "field": "title", "message": "explicit title choice resolves metadata conflict", "catalog_title": item["title"], "frontmatter_title": value, "chosen_title": choice})
                            item["title"] = choice
                        else:
                            block(source, "title", f"front matter {value!r} conflicts with catalog {item['title']!r}")
                elif field in CATALOG_FIELDS:
                    if field == "cover" and isinstance(value, str):
                        cover_source = self.root / Path(source).parent / value
                        if not cover_source.is_file():
                            cover_source = self.root / value.lstrip("/")
                        try:
                            value = copy_asset(cover_source)
                        except (ValueError, OSError) as exc:
                            block(source, field, str(exc))
                            continue
                    if field in item and item[field] != value:
                        block(source, field, f"front matter {value!r} conflicts with catalog {item[field]!r}")
                    else:
                        item[field] = value
                else:
                    report["presentation_exceptions"].append({"path": source, "field": key, "value": value, "action": "review frontend template/default ownership"})
            files[target] = nbformat.writes(candidate).encode("utf-8")

        sidebars = self._yaml("knowledge/sidebar.yaml").get("website", {}).get("sidebar", [])
        for course in [a for a in artifacts if a["kind"] == "course"]:
            source = course["path"]
            slug = Path(source).name
            contract = self._yaml(f"{source}/course.yaml")
            toc = []
            sidebar = next((value for value in sidebars if value.get("id") == slug), None)
            if sidebar is None:
                block("knowledge/sidebar.yaml", course["id"], "missing authored course sidebar")
            else:
                for number, group in enumerate(sidebar.get("contents", [])):
                    title = group.get("section", "")
                    section = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "orientation"
                    if any(existing["id"] == section for existing in toc):
                        section = f"{section}-{number + 1}"
                    chapter_ids = []
                    for link in group.get("contents", []):
                        chapter = by_path.get(link.get("href"))
                        if not chapter or chapter["kind"] != "chapter" or chapter.get("parent") != course["id"]:
                            block("knowledge/sidebar.yaml", course["id"], f"unknown or foreign chapter {link.get('href')}")
                            continue
                        chapter["section"] = section
                        chapter["toc_title"] = link.get("text") or chapter["title"]
                        chapter_ids.append(chapter["id"])
                    toc.append({"id": section, "title": title, "chapters": chapter_ids})
            contract["toc"] = toc
            planned = contract.get("planned", {}).get("chapters", [])
            normalized_plans = []
            for plan in planned:
                if "chapter_id" in plan:
                    normalized_plans.append(plan)
                    continue
                for stem, summary in plan.items():
                    chapter = by_path.get(f"{source}/{stem}.ipynb")
                    if chapter is None:
                        block(f"{source}/course.yaml", "planned.chapters", f"unknown chapter {stem}")
                    else:
                        normalized_plans.append({"chapter_id": chapter["id"], "section": chapter.get("section", ""), "summary": summary})
            if planned:
                contract["planned"]["chapters"] = normalized_plans
            overview = by_path.get(f"{source}/00-overview.ipynb")
            if overview:
                contract["overview"] = overview["id"]
            target = f"content/data/courses/{slug}.yaml"
            files[target] = yaml_bytes(contract)
            report["courses"].append({"id": course["id"], "source": f"{source}/course.yaml", "target": target, "toc": toc, "actualized": copy.deepcopy(contract.get("actualized"))})
            home = f"{source}/index.ipynb"
            course["route"] = home
            course["path"] = f"content/notebooks/courses/{slug}"
            migrate_notebook(home, f"{course['path']}/index.ipynb", course)

        for item in artifacts:
            kind = item["kind"]
            if kind == "course" or kind == "project":
                continue
            source = item["path"]
            target = f"content/notebooks/{source.removeprefix('nb/')}"
            if kind == "portfolio":
                target = str(Path(target).with_suffix(".ipynb"))
                detail: dict[str, Any] = {"id": item["id"], "abstract": item.pop("summary", ""), "notebook_path": target}
                name = HISTORICAL_PROJECTS.get(item["id"])
                if name:
                    detail["project_path"] = f"archive/2026-09-30/projects/{name}"
                    project = detail["project_path"]
                    if not (self.root / project).is_dir():
                        block(source, "project_path", f"archived project directory missing: {project}")
                    figure = f"archive/2026-09-30/nb/portfolio/img/{name}-flow.svg"
                    report["warnings"].append({"path": source, "message": "review historical figure and caption without adopting archived claims", "suggested_figure": figure if (self.root / figure).is_file() else None})
                    caption = historical_captions.get(f"{name}-flow.svg")
                    if self.reviewed_portfolio_figures and caption and (self.root / figure).is_file():
                        figure_target = f"content/assets/portfolio/{name}-flow.svg"
                        detail.update(figure_path=figure_target, figure_caption=caption)
                        files[figure_target] = (self.root / figure).read_bytes()
                else:
                    block(source, "project_path", "project reference requires review")
                if not detail.get("figure_path"):
                    block(source, "figure_path", "required figure and caption need author review")
                portfolio.append(detail)
                item.pop("path")
                item["route"] = str(Path(source).with_suffix(".ipynb"))
            else:
                item["path"] = target
                item["route"] = source
            migrate_notebook(source, target, item)
            if kind == "chapter" and not item.get("section"):
                block(source, "section", "chapter not present in authored sidebar")

        gallery_source = "nb/photos/photos.ipynb"
        if (self.root / gallery_source).exists():
            gallery = read_source_notebook(self.root / gallery_source)
            photos, prose = extract_photos(gallery)
            report["photos"] = photos
            report["gallery_prose"] = prose
            if prose and not self.preserve_gallery_as_personal:
                block(gallery_source, "prose", "preserve or relocate gallery prose before retiring the notebook")
            for index, photo in enumerate([] if self.preserve_gallery_as_personal else photos):
                if urlsplit(photo["path"]).scheme or photo["path"].startswith("attachment:"):
                    block(gallery_source, f"photos[{index}].path", "photo must be a reviewed repository image, not a remote placeholder or attachment")
                elif not (self.root / Path(gallery_source).parent / photo["path"]).is_file():
                    block(gallery_source, f"photos[{index}].path", "referenced image does not exist")
                if not photo["caption"].strip():
                    block(gallery_source, f"photos[{index}].caption", "caption requires review; no caption was invented")
                if not photo.get("heading"):
                    block(gallery_source, f"photos[{index}].heading", "each photo requires a reviewed section heading")
            header = document_header(gallery.cells[0].source)[0] if gallery.cells else {}
            if self.preserve_gallery_as_personal:
                personal = {"id": "personal/photos-notes", "kind": "personal", "title": header.get("title", "Personal"), "path": "content/notebooks/personal/photos-notes.ipynb", "visibility": "private", "lifecycle": "published", "relations": [], "route": "nb/personal/photos-notes.ipynb"}
                artifacts.append(personal)
                migrate_notebook(gallery_source, personal["path"], personal)
                artifacts.append({"id": "gallery/photos", "kind": "gallery", "title": "Personal", "path": "content/data/photos.yaml", "visibility": "public", "lifecycle": "planned", "relations": [], "route": gallery_source})
                files["content/data/photos.yaml"] = yaml_bytes({"version": 1, "photos": []})
                report["warnings"].append({"path": gallery_source, "message": "explicit preservation decision retains all gallery body/prose/placeholders in a personal notebook and reserves an empty planned gallery"})
            else:
                artifacts.append({"id": "gallery/photos", "kind": "gallery", "title": header.get("title", "Personal"), "path": "content/data/photos.yaml", "visibility": "public", "lifecycle": "published", "relations": [], "route": gallery_source})
                files["content/data/photos.yaml"] = yaml_bytes({"version": 1, "photos": photos})

        profile = self._yaml("assets/resume.yaml")
        report["profile"] = {"source": "assets/resume.yaml", "fields": list(profile), "preserved": True}
        files["content/data/profile.yaml"] = yaml_bytes({"version": 1, **profile})
        files["content/data/catalog.yaml"] = yaml_bytes({"version": 1, "artifacts": artifacts})
        files["content/data/portfolio.yaml"] = yaml_bytes({"version": 1, "entries": portfolio})
        report["artifacts"] = artifacts
        report["ready"] = not report["blockers"]
        report["candidate_paths"] = list(files)
        return {"files": files, "report": report}
