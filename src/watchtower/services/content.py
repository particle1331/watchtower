"""Validated file-backed content management, independent of HTTP or CLI."""
from __future__ import annotations

import copy
import json
import posixpath
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import nbformat
import yaml
from markdown_it import MarkdownIt
from pydantic import ValidationError

from watchtower.models import (
    Artifact,
    Catalog,
    ChapterPlan,
    CourseContract,
    Kanban,
    Photos,
    Portfolio,
    Profile,
    SiteSettings,
    Workspace,
    course_rows,
    displayed_text,
    eligible,
    h1s,
    has_content,
    markdown_h1s,
    plan_body,
    route_for,
    source_path,
)
from watchtower.planning import extra_plan_body, missing_fields
from watchtower.starters import draft_sections, portfolio_abstract

from .images import portfolio_figure, uploaded_image
from .projects import project_name, scaffold_project
from .workspace import ServiceError, WorkspaceStore, digest, load_yaml, revision

CATALOG = "content/data/catalog.yaml"
PORTFOLIO = "content/data/portfolio.yaml"
PROFILE = "content/data/profile.yaml"
PHOTOS = "content/data/photos.yaml"
KANBAN = "content/data/kanban.yaml"
SETTINGS = "frontend/site.yaml"


def yaml_bytes(data: Any) -> bytes:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode()


@dataclass(frozen=True)
class WorkspaceSnapshot:
    state: Workspace
    files: dict[str, bytes]
    revision: str


def parse_state(files: dict[str, bytes | None]) -> Workspace:
    def record(name: str) -> dict[str, Any]:
        value = files.get(name)
        if value is None:
            raise ServiceError(f"required data missing: {name}; run wt migrate before using the new system", paths=[name])
        return load_yaml(value, name)
    try:
        catalog = Catalog.model_validate(record(CATALOG))
        portfolio = Portfolio.model_validate(record(PORTFOLIO))
        photos = Photos.model_validate(record(PHOTOS))
        for artifact in catalog.artifacts:
            if artifact.kind == "gallery":
                artifact.lifecycle = "published" if any(photo.lifecycle == "published" for photo in photos.photos) else "planned"
        profile = Profile.model_validate(record(PROFILE))
        settings = SiteSettings.model_validate(record(SETTINGS))
        kanban = Kanban.model_validate(record(KANBAN)) if files.get(KANBAN) is not None else Kanban()
        courses = {}
        for item in catalog.artifacts:
            if item.kind == "course":
                name = f"content/data/courses/{item.id.split('/')[-1]}.yaml"
                courses[item.id] = CourseContract.model_validate(record(name))
        return Workspace(artifacts=catalog.artifacts, portfolio=portfolio.entries, courses=courses, photos=photos.photos, profile=profile, settings=settings, kanban=kanban.cards)
    except (ValidationError, ValueError) as error:
        if isinstance(error, ServiceError):
            raise
        raise ServiceError(str(error)) from error


def validate_state(state: Workspace, files: dict[str, bytes | None], root: Path) -> None:
    errors: list[str] = []
    paths: list[str] = []
    def fail(message: str, path: str = CATALOG) -> None:
        errors.append(message)
        paths.append(path)
    def exists(path: str | None, description: str) -> bool:
        if not path or files.get(path) is None:
            fail(f"{description}: missing {path}", path or CATALOG)
            return False
        return True
    def check_assets(notebook: nbformat.NotebookNode, source: str) -> None:
        def reference(value: str, attachments: dict[str, Any]) -> None:
            parsed = urlsplit(value)
            if parsed.scheme in {"https", "http", "data"} or value.startswith("//"):
                return
            if parsed.scheme == "attachment":
                if parsed.path not in attachments:
                    fail(f"{source}: missing attachment {parsed.path}", source)
                return
            if parsed.scheme:
                fail(f"{source}: unsupported image scheme {parsed.scheme}", source)
                return
            path = unquote(parsed.path)
            target = posixpath.normpath(path.lstrip("/") if path.startswith("/") else posixpath.join(posixpath.dirname(source), path))
            if path and files.get(target) is None:
                fail(f"{source}: missing image or media {value}", source)
        def body(text: str, attachments: dict[str, Any]) -> None:
            for token in MarkdownIt("commonmark", {"html": True}).parse(text):
                for child in token.children or []:
                    if child.type == "image":
                        reference(str(child.attrGet("src") or ""), attachments)
                    elif child.type == "html_inline":
                        for match in re.finditer(r"\bsrc=[\"']([^\"']+)[\"']", child.content):
                            reference(match[1], attachments)
                if token.type == "html_block":
                    for match in re.finditer(r"\bsrc=[\"']([^\"']+)[\"']", token.content):
                        reference(match[1], attachments)
        for cell in notebook.cells:
            attachments = cell.get("attachments", {})
            if cell.cell_type == "markdown":
                body(cell.source, attachments)
            for output in cell.get("outputs", []):
                for mime in ("text/html", "text/markdown"):
                    data = output.get("data", {}).get(mime)
                    if isinstance(data, str):
                        body(data, attachments)
    artifacts = {a.id: a for a in state.artifacts}
    if len(artifacts) != len(state.artifacts):
        fail("duplicate artifact IDs")
    details = {p.id: p for p in state.portfolio}
    if len(details) != len(state.portfolio):
        fail("duplicate portfolio IDs", PORTFOLIO)
    portfolio_ids = {a.id for a in state.artifacts if a.kind == "portfolio"}
    if portfolio_ids != set(details):
        fail("portfolio detail IDs must exactly match catalog portfolio IDs", PORTFOLIO)
    routes: set[str] = set()
    sources: set[str] = set()
    for artifact in state.artifacts:
        for related in artifact.relations:
            if related not in artifacts:
                fail(f"{artifact.id}: unknown relation {related}")
        if artifact.kind != "project":
            route = route_for(artifact)
            if route in routes:
                fail(f"duplicate route {route}")
            routes.add(route)
        if artifact.cover:
            exists(artifact.cover, f"{artifact.id} cover image")
        if artifact.kind == "project":
            key = f"@dir/{artifact.path}"
            if key not in files:
                fail(f"{artifact.id}: project directory missing", str(artifact.path))
            continue
        if artifact.kind == "gallery":
            expected = "published" if any(photo.lifecycle == "published" for photo in state.photos) else "planned"
            if artifact.lifecycle != expected:
                fail(f"{artifact.id}: gallery lifecycle is derived from photo states; expected {expected}", PHOTOS)
            continue
        source = source_path(artifact, state)
        if source:
            if source in sources:
                fail(f"duplicate authored source {source}", source)
            sources.add(source)
        value = files.get(source or "")
        if value is None:
            if artifact.lifecycle != "planned":
                fail(f"{artifact.id}: {artifact.lifecycle} requires authored notebook", source or CATALOG)
        else:
            try:
                notebook = nbformat.reads(value.decode(), as_version=4)
                nbformat.validate(notebook)
                check_assets(notebook, str(source))
                if artifact.kind == "chapter" and h1s(notebook) != [artifact.title]:
                    fail(f"{artifact.id}: expected exactly one H1 matching '{artifact.title}', found {h1s(notebook)}", str(source))
                content = has_content(notebook, artifact.title)
                if artifact.lifecycle == "planned" and content or artifact.lifecycle == "published" and not content:
                    fail(f"{artifact.id}: planned must have no authored content; published requires authored content; draft may be a scaffold", str(source))
                for cell in notebook.cells:
                    if cell.cell_type == "markdown":
                        header = re.match(r"\A\s*---\s*\n(.*?)\n---(?:\s*\n|$)", cell.source, re.S)
                        if header and isinstance(yaml.safe_load(header[1]), dict):
                            fail(f"{artifact.id}: document front matter belongs in generated copies", str(source))
            except (ValueError, nbformat.ValidationError, yaml.YAMLError) as error:
                fail(f"{artifact.id}: invalid notebook: {error}", str(source))
        if artifact.kind == "portfolio" and artifact.id in details:
            detail = details[artifact.id]
            if artifact.lifecycle != "planned":
                required = ("abstract", "figure_path", "figure_caption", "notebook_path", "project_name") if artifact.lifecycle == "published" else ("notebook_path", "project_name")
                for field in required:
                    if not getattr(detail, field):
                        fail(f"{artifact.id}: {field} required for {artifact.lifecycle}", PORTFOLIO)
            if detail.figure_path:
                exists(detail.figure_path, f"{artifact.id} figure")
            if detail.project_path:
                prefix = f"archive/{detail.archive_date}/projects" if detail.project_source == "archived" else "projects"
                key = f"@dir/{detail.project_path}"
                resolved = files.get(key)
                if resolved is None:
                    if artifact.lifecycle != "planned" or detail.project_source != "active":
                        fail(f"{artifact.id}: missing project directory {detail.project_path}", PORTFOLIO)
                elif not Path(resolved.decode()).is_relative_to(root / prefix):
                    fail(f"{artifact.id}: project symlink escapes selected project root", PORTFOLIO)
                for related in artifact.relations:
                    target = artifacts.get(related)
                    if target and target.kind == "project" and target.path != detail.project_path:
                        fail(f"{artifact.id}: project relation points to different code directory", PORTFOLIO)
        if artifact.kind == "chapter":
            parent = artifacts.get(str(artifact.parent))
            if parent is None or parent.kind != "course":
                fail(f"{artifact.id}: parent must reference a course")
    for course_id, course in state.courses.items():
        name = f"content/data/courses/{course_id.split('/')[-1]}.yaml"
        if course.id != course_id:
            fail(f"{course_id}: contract ID mismatch", name)
        section_ids = [section.id for section in course.toc]
        if len(section_ids) != len(set(section_ids)):
            fail(f"{course_id}: duplicate section IDs", name)
        seen: list[str] = []
        for section in course.toc:
            for chapter_id in section.chapters:
                seen.append(chapter_id)
                chapter = artifacts.get(chapter_id)
                if chapter is None or chapter.kind != "chapter" or chapter.parent != course_id or chapter.section != section.id:
                    fail(f"{course_id}: invalid chapter membership {chapter_id} in {section.id}", name)
        expected = {a.id for a in state.artifacts if a.kind == "chapter" and a.parent == course_id}
        if len(seen) != len(set(seen)) or set(seen) != expected:
            fail(f"{course_id}: every chapter must occur exactly once in TOC", name)
        plans = course.planned.get("chapters", [])
        planned_ids: set[str] = set()
        if not isinstance(plans, list):
            fail(f"{course_id}: planned.chapters must be a list", name)
            plans = []
        for raw in plans:
            try:
                plan = ChapterPlan.model_validate(raw)
            except ValidationError as error:
                fail(f"{course_id}: invalid chapter plan: {error}", name)
                continue
            chapter = artifacts.get(plan.chapter_id)
            if plan.chapter_id in planned_ids or chapter is None or chapter.parent != course_id or chapter.section != plan.section:
                fail(f"{course_id}: duplicate, foreign, or mismatched plan {plan.chapter_id}", name)
            planned_ids.add(plan.chapter_id)
            if markdown_h1s(plan.content) or markdown_h1s(plan.lab_and_evidence):
                fail(f"{plan.chapter_id}: plan bodies must not contain H1 headings", name)
        for chapter_id in expected:
            if artifacts[chapter_id].lifecycle == "planned" and chapter_id not in planned_ids:
                fail(f"{chapter_id}: missing chapter plan", name)
        if course.overview and course.overview not in expected:
            fail(f"{course_id}: overview must reference own chapter", name)
    for photo in state.photos:
        if photo.path:
            exists(photo.path, "gallery image")
    for card in state.kanban:
        for artifact_id in card.artifact_ids:
            if artifact_id not in artifacts:
                fail(f"Kanban card {card.id}: unknown stable ID {artifact_id}", KANBAN)
    for project in state.profile.projects:
        if project.artifact_id and project.artifact_id not in artifacts:
            fail(f"profile project: unknown artifact {project.artifact_id}", PROFILE)
    for name, value in files.items():
        if value is not None and name.startswith("content/notebooks/") and name.endswith(".ipynb") and name not in sources:
            fail(f"unregistered active notebook: {name}", name)
    if errors:
        raise ServiceError("\n".join(errors), paths=sorted(set(paths)))


class ContentService:
    def __init__(self, root: Path | None = None):
        self.root = (root or Path.cwd()).resolve()
        self.store = WorkspaceStore(self.root)

    def _snapshot(self) -> WorkspaceSnapshot:
        files = self.store.inputs()
        state = parse_state(files)
        validate_state(state, files, self.root)
        after = self.store.inputs()
        if revision(files) != revision(after):
            raise ServiceError("inputs changed while capturing snapshot", code="conflict", status=412)
        return WorkspaceSnapshot(state, {p: b for p, b in files.items() if b is not None and not p.startswith("@dir/")}, revision(files))

    def snapshot(self) -> WorkspaceSnapshot:
        with self.store.locked():
            return self._snapshot()

    def validate(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {"valid": True, "revision": snapshot.revision, "artifacts": len(snapshot.state.artifacts)}

    def list(self, kind: str | None = None) -> dict[str, Any]:
        with self.store.locked():
            files = self.store.inputs()
            catalog = self._catalog(files)
            return {"artifacts": [a for a in catalog["artifacts"] if kind is None or a.get("kind") == kind], "revision": revision(files)}

    @staticmethod
    def _planning(artifact: Artifact, state: Workspace) -> dict[str, Any]:
        if artifact.kind == "course":
            contract = state.courses[artifact.id]
            return {**contract.planned, "purpose": contract.purpose, "audience": contract.audience,
                    "summary": contract.planned.get("summary") or artifact.planned.get("content", "")}
        if artifact.kind == "chapter":
            return next((p for p in state.courses[str(artifact.parent)].planned.get("chapters", []) if p.get("chapter_id") == artifact.id), {})
        if artifact.kind == "portfolio":
            return next(p.planned for p in state.portfolio if p.id == artifact.id)
        return artifact.planned

    @classmethod
    def _build_brief(cls, artifact: Artifact, state: Workspace) -> str:
        plan = cls._planning(artifact, state)
        lines = [f"# {artifact.title}", "", f"Stable ID: {artifact.id}", f"Kind: {artifact.kind}",
                 f"State: {artifact.lifecycle} / {artifact.visibility}"]
        path = source_path(artifact, state)
        if path:
            lines.append(f"Notebook: {path}")
        if artifact.kind == "portfolio":
            detail = next(p for p in state.portfolio if p.id == artifact.id)
            lines.append(f"Project: {detail.project_path or 'projects/' + artifact.id.split('/')[-1]}")
        if artifact.kind == "portfolio":
            detail = next(entry for entry in state.portfolio if entry.id == artifact.id)
            if abstract := detail.abstract or artifact.description:
                lines.extend(["", "Abstract: " + abstract])
        elif artifact.description:
            lines.extend(["", "Description: " + artifact.description])
        if artifact.internal_notes:
            lines.extend(["", "## Internal notes", "", artifact.internal_notes])
        if artifact.tags:
            lines.append("Tags: " + ", ".join(artifact.tags))
        if artifact.relations:
            lines.append("Related stable IDs: " + ", ".join(artifact.relations))
        lines.extend(["", extra_plan_body(artifact.kind, plan, {"chapters", "chapter_id", "section"})])
        if artifact.planned and artifact.kind in {"course", "portfolio", "chapter"}:
            lines.extend(["", "## Legacy catalog plan", "", extra_plan_body(artifact.kind, artifact.planned, set())])
        missing = missing_fields(artifact.kind, plan)
        lines.extend(["", "Suggested planning fields missing (optional): " + (", ".join(missing) if missing else "None")])
        if artifact.kind == "course":
            for row in course_rows(state.courses[artifact.id], state.artifacts):
                child = next(a for a in state.artifacts if a.id == row["chapter"]["id"])
                lines.extend(["", f"## {row['section']} / {child.title}", "", cls._build_brief(child, state)])
        elif artifact.kind == "chapter":
            parent = next(a for a in state.artifacts if a.id == artifact.parent)
            context = cls._planning(parent, state)
            lines.extend(["", f"## Course context: {parent.title}", "", f"Course ID: {parent.id}",
                          f"Section: {artifact.section}", "", extra_plan_body("course", context, {"chapters"})])
            if parent.internal_notes:
                lines.extend(["", "### Course internal notes", "", parent.internal_notes])
        return "\n".join(lines)

    def organize_course(self, artifact_id: str, action: str, values: dict[str, str], expected_revision: str) -> dict[str, Any]:
        """Apply one scoped outline action while validating all linked records."""
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            catalog = self._catalog(files)
            record = self._find(catalog, artifact_id)
            if record["kind"] != "course":
                raise ServiceError("Choose a course.")
            name = f"content/data/courses/{artifact_id.split('/')[-1]}.yaml"
            contract = load_yaml(files[name] or b"", name)
            sections = contract["toc"]
            selected = next((s for s in sections if s["id"] == values.get("section")), None)
            if action == "add-section":
                title = values.get("title", "").strip()
                section_id = re.sub(r"[^a-z0-9_-]+", "-", title.casefold()).strip("-_")
                if not section_id:
                    raise ServiceError("Enter a section title containing letters or numbers.")
                if any(s["id"].casefold() == section_id for s in sections):
                    raise ServiceError("A section with this name already exists.")
                sections.append({"id": section_id, "title": title, "chapters": []})
            elif action in {"rename-section", "remove-section", "section-up", "section-down"}:
                if selected is None:
                    raise ServiceError("Choose an existing section.")
                if action == "rename-section":
                    title = values.get("title", "").strip()
                    if not title:
                        raise ServiceError("Enter a section title.")
                    selected["title"] = title
                elif action == "remove-section":
                    if selected["chapters"]:
                        raise ServiceError("Move or delete the chapters before removing this section.")
                    if len(sections) == 1:
                        raise ServiceError("Keep at least one section for new chapters.")
                    sections.remove(selected)
                else:
                    index = sections.index(selected)
                    target = index + (-1 if action == "section-up" else 1)
                    if not 0 <= target < len(sections):
                        raise ServiceError("Section is already at the edge of the outline.")
                    sections[index], sections[target] = sections[target], sections[index]
            elif action in {"chapter-up", "chapter-down", "move-chapter"}:
                chapter = self._find(catalog, values.get("chapter", ""))
                if chapter.get("parent") != artifact_id or chapter["kind"] != "chapter":
                    raise ServiceError("Choose a chapter belonging to this course.")
                origin = next(s for s in sections if chapter["id"] in s["chapters"])
                if action == "move-chapter":
                    if selected is None:
                        raise ServiceError("Choose a destination section.")
                    if selected != origin:
                        origin["chapters"].remove(chapter["id"])
                        selected["chapters"].append(chapter["id"])
                        chapter["section"] = selected["id"]
                        for plan in contract["planned"].get("chapters", []):
                            if plan["chapter_id"] == chapter["id"]:
                                plan["section"] = selected["id"]
                else:
                    chapters = origin["chapters"]
                    index = chapters.index(chapter["id"])
                    target = index + (-1 if action == "chapter-up" else 1)
                    if not 0 <= target < len(chapters):
                        raise ServiceError("Chapter is already at the edge of this section.")
                    chapters[index], chapters[target] = chapters[target], chapters[index]
            else:
                raise ServiceError("Unknown course outline action.")
            return {"course_id": artifact_id}, {CATALOG: yaml_bytes(catalog), name: yaml_bytes(contract)}
        return self._mutate("organize course", apply, expected_revision)

    def read_plan(self, stable_id: str) -> dict[str, Any]:
        """Read internal authoring context independently of notebook content or lifecycle."""
        with self.store.locked():
            files = self.store.inputs()
            state = parse_state(files)
            artifact = next((a for a in state.artifacts if a.id == stable_id), None)
            if artifact is None:
                raise ServiceError(f"unknown artifact stable ID: {stable_id}", code="not_found", status=404)
            return {
                "id": artifact.id,
                "kind": artifact.kind,
                "title": artifact.title,
                "lifecycle": artifact.lifecycle,
                "source_path": source_path(artifact, state),
                "plan": self._planning(artifact, state),
                "internal_notes": artifact.internal_notes,
                "build_brief": self._build_brief(artifact, state),
                "revision": revision(files),
            }

    def inspect(self, artifact_id: str) -> dict[str, Any]:
        with self.store.locked():
            files = self.store.inputs()
            state = parse_state(files)
            artifact = next((a for a in state.artifacts if artifact_id in {a.id, a.path}), None)
            if artifact is None:
                raise ServiceError(f"unknown artifact: {artifact_id}", code="not_found", status=404)
            path = source_path(artifact, state)
            existing = bool(path and files.get(path) is not None)
            result = {"artifact": artifact.model_dump(mode="json"), "revision": revision(files), "source_path": path, "has_source": existing, "editor_url": "vscode://file/" + quote(str(self.root / str(path)), safe="/") if existing else None, "eligible": eligible(artifact, state.artifacts), "plan": plan_body(artifact, state), "route": route_for(artifact)}
            if path:
                try:
                    result["has_authored_content"] = existing and has_content(nbformat.reads((files[path] or b"").decode(), as_version=4), artifact.title)
                except (ValueError, nbformat.ValidationError):
                    # Inspection must still expose malformed sources for repair.
                    result["has_authored_content"] = None
            if artifact.kind == "portfolio":
                result["detail"] = next(p.model_dump(mode="json") for p in state.portfolio if p.id == artifact.id)
            if artifact.kind == "course":
                result["contract"] = state.courses[artifact.id].model_dump(mode="json")
            if artifact.kind == "chapter":
                result["chapter_plan"] = next((p for p in state.courses[str(artifact.parent)].planned.get("chapters", []) if p.get("chapter_id") == artifact.id), None)
            planning = self._planning(artifact, state)
            result["missing_plan_fields"] = missing_fields(artifact.kind, planning)
            result["build_brief"] = self._build_brief(artifact, state)
            if artifact.kind == "course":
                result["chapter_rows"] = course_rows(state.courses[artifact.id], state.artifacts)
            try:
                validate_state(state, files, self.root)
                result["errors"] = []
            except ServiceError as error:
                result["errors"] = [error.as_dict()]
            return result

    def _mutate(self, operation: str, callback: Any, expected_revision: str | None) -> dict[str, Any]:
        with self.store.locked():
            original = self.store.inputs()
            token = revision(original)
            if expected_revision is not None and expected_revision.strip('"') != token:
                raise ServiceError(f"stale workspace revision; current revision {token}", code="conflict", status=412, paths=[CATALOG])
            # Loading deliberately does not validate the old semantic state.
            candidate = copy.deepcopy(original)
            try:
                result, writes = callback(candidate)
                if KANBAN in writes and writes[KANBAN] is not None:
                    incoming = Kanban.model_validate(load_yaml(writes[KANBAN], KANBAN))
                    try:
                        previous = Kanban.model_validate(load_yaml(original[KANBAN] or b"", KANBAN)) if original.get(KANBAN) is not None else Kanban()
                    except (ServiceError, ValidationError):
                        if operation not in {"update kanban", "batch"}:
                            raise
                        # Explicit whole-board repair remains available for malformed YAML.
                        previous = Kanban()
                    try:
                        incoming.preserve_identities(previous)
                    except ValueError as error:
                        raise ServiceError(str(error), paths=[KANBAN]) from error
                    saved_board = incoming.model_dump(mode="json")
                    writes[KANBAN] = yaml_bytes(saved_board)
                    if operation == "update kanban":
                        result["data"] = saved_board
                    elif operation == "batch" and "kanban" in result.get("data", {}):
                        result["data"]["kanban"] = saved_board
                candidate.update(writes)
                candidate.update(self.store.project_directories(writes))
                state = parse_state(candidate)
                validate_state(state, candidate, self.root)
            except (ValidationError, KeyError, TypeError) as error:
                raise ServiceError(f"invalid candidate: {error}") from error
            transaction = self.store.commit(writes, original, operation)
            result.update(revision=revision(self.store.inputs()), transaction=transaction)
            if KANBAN in writes:
                result["board_revision"] = "kanban:" + digest(writes[KANBAN])
            return result

    @staticmethod
    def _catalog(files: dict[str, bytes | None]) -> dict[str, Any]:
        catalog = load_yaml(files.get(CATALOG) or b"", CATALOG)
        if not isinstance(catalog.get("artifacts"), list):
            raise ServiceError("catalog artifacts must be a list", paths=[CATALOG])
        catalog["artifacts"] = [Artifact.normalize_labels(record) for record in catalog["artifacts"]]
        return catalog

    @staticmethod
    def _find(catalog: dict[str, Any], artifact_id: str) -> dict[str, Any]:
        record = next((a for a in catalog["artifacts"] if artifact_id in {a.get("id"), a.get("path")}), None)
        if record is None:
            raise ServiceError(f"unknown artifact {artifact_id}", code="not_found", status=404)
        return record

    def create_post(self, name: str, data: dict[str, Any], expected_revision: str | None = None) -> dict[str, Any]:
        """Create a post plan from a single extension-free name."""
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise ServiceError("Name must have no extension or folders; use letters, numbers, hyphens or underscores.")
        payload = {**data, "kind": "post", "id": f"post/{name}", "path": f"content/notebooks/posts/{name}.ipynb"}
        return self.create(payload, expected_revision)

    def create(self, data: dict[str, Any], expected_revision: str | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            payload = copy.deepcopy(data)
            detail, contract = payload.pop("detail", None), payload.pop("contract", None)
            chapter_plan = payload.pop("plan", None) or {}
            plan_content, plan_lab = payload.pop("planned_content", None), payload.pop("planned_lab_and_evidence", None)
            payload.setdefault("lifecycle", "planned")
            if payload.get("kind") == "chapter":
                payload["lifecycle"] = "planned"
            settings = SiteSettings.model_validate(load_yaml(files[SETTINGS] or b"", SETTINGS))
            if payload.get("kind") in {"post", "personal"}:
                payload.setdefault("date", datetime.now(ZoneInfo(settings.timezone)).date().isoformat())
            artifact = Artifact.model_validate(payload)
            if artifact.lifecycle == "planned" and artifact.kind not in {"gallery", "project"}:
                artifact.visibility = "private"
            catalog = self._catalog(files)
            if any(a.get("id", "").casefold() == artifact.id.casefold() for a in catalog["artifacts"]):
                raise ServiceError(f"Name is already used: {artifact.id.split('/')[-1]}" if artifact.kind == "post" else f"ID already registered: {artifact.id}")
            if artifact.id.casefold() in {value.casefold() for value in catalog.get("retired_ids", [])}:
                raise ServiceError(f"Name was previously used and remains reserved: {artifact.id.split('/')[-1]}" if artifact.kind == "post" else f"ID was previously deleted and remains reserved: {artifact.id}")
            reserved_sources = {value.casefold() for value in catalog.get("retired_sources", [])}
            source = (detail or {}).get("notebook_path") if artifact.kind == "portfolio" else artifact.path
            if source and source.casefold() in reserved_sources:
                raise ServiceError(f"Name / source was previously deleted and remains reserved: {source}")
            if artifact.kind == "post" and any(a.get("path", "").casefold() == (artifact.path or "").casefold() for a in catalog["artifacts"] if a.get("path")):
                raise ServiceError("Name is already used by another post.")
            catalog["artifacts"].append(artifact.model_dump(mode="json", exclude_none=True))
            writes = {CATALOG: yaml_bytes(catalog)}
            if artifact.kind == "portfolio":
                portfolio = load_yaml(files[PORTFOLIO] or b"", PORTFOLIO)
                portfolio["entries"].append({"id": artifact.id, **(detail or {})})
                writes[PORTFOLIO] = yaml_bytes(portfolio)
            if artifact.kind == "course":
                name = f"content/data/courses/{artifact.id.split('/')[-1]}.yaml"
                if files.get(name) is not None:
                    raise ServiceError("course contract already exists", paths=[name])
                writes[name] = yaml_bytes({"id": artifact.id, "purpose": "", "audience": "", "planned": {"summary": "", "chapters": []}, "actualized": {"summary": ""}, "toc": [{"id": "main", "title": "", "chapters": []}], **(contract or {})})
            if artifact.kind == "chapter":
                name = f"content/data/courses/{str(artifact.parent).split('/')[-1]}.yaml"
                course = load_yaml(files.get(name) or b"", name)
                section = next((s for s in course["toc"] if s["id"] == artifact.section), None)
                if section is None:
                    raise ServiceError("unknown course section", paths=[name])
                section["chapters"].append(artifact.id)
                course["planned"].setdefault("chapters", []).append({**chapter_plan, "chapter_id": artifact.id, "section": artifact.section, "content": plan_content if plan_content is not None else chapter_plan.get("content", ""), "lab_and_evidence": plan_lab if plan_lab is not None else chapter_plan.get("lab_and_evidence", "")})
                writes[name] = yaml_bytes(course)
            return {"artifact": artifact.model_dump(mode="json")}, writes
        return self._mutate("create", apply, expected_revision)

    def _deletion_plan(self, files: dict[str, bytes | None], artifact_id: str) -> dict[str, Any]:
        catalog = self._catalog(files)
        record = self._find(catalog, artifact_id)
        if record["kind"] == "gallery":
            raise ServiceError("Remove individual photos in Personal; the gallery is a built-in surface.")
        state = parse_state(files)
        removed = [a for a in state.artifacts if a.id == record["id"] or (record["kind"] == "course" and a.parent == record["id"])]
        ids = {a.id for a in removed}
        sources = [path for a in removed if (path := source_path(a, state)) and files.get(path) is not None and a.kind != "project"]
        if record["kind"] == "course":
            sources.append(f"content/data/courses/{record['id'].split('/')[-1]}.yaml")
        links = [{"kind": "relation", "id": a.id, "title": a.title, "artifact_ids": [link for link in a.relations if link in ids]} for a in state.artifacts if a.id not in ids and any(link in ids for link in a.relations)]
        links.extend({"kind": "kanban", "id": card.id, "title": card.title, "artifact_ids": [link for link in card.artifact_ids if link in ids]} for card in state.kanban if any(link in ids for link in card.artifact_ids))
        links.extend({"kind": "profile", "id": project.title, "artifact_ids": [project.artifact_id]} for project in state.profile.projects if project.artifact_id in ids)
        return {"artifact": record, "removed": [a.model_dump(mode="json") for a in removed], "archive_files": sorted(set(sources)), "detached_links": links}

    def deletion_plan(self, artifact_id: str) -> dict[str, Any]:
        """Review removal, including course children and incoming managed links."""
        with self.store.locked():
            files = self.store.inputs()
            return {**self._deletion_plan(files, artifact_id), "revision": revision(files)}

    def delete(self, artifact_id: str, expected_revision: str | None = None, *, cascade: bool = False) -> dict[str, Any]:
        """Remove registrations, archive authored files, and detach managed links."""
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes | None]]:
            plan = self._deletion_plan(files, artifact_id)
            if len(plan["removed"]) > 1 and not cascade:
                raise ServiceError("Course has chapters; review deletion and explicitly include them with cascade.", code="has_children", status=409)
            ids = {record["id"] for record in plan["removed"]}
            catalog = self._catalog(files)
            catalog["artifacts"] = [a for a in catalog["artifacts"] if a["id"] not in ids]
            for record in catalog["artifacts"]:
                record["relations"] = [link for link in record.get("relations", []) if link not in ids]
            catalog["retired_ids"] = sorted(set(catalog.get("retired_ids", [])) | ids)
            state = parse_state(files)
            reserved_sources = {source_path(a, state) for a in state.artifacts if a.id in ids}
            catalog["retired_sources"] = sorted(set(catalog.get("retired_sources", [])) | {name for name in reserved_sources if name})
            writes: dict[str, bytes | None] = {CATALOG: yaml_bytes(catalog)}
            portfolio = load_yaml(files[PORTFOLIO] or b"", PORTFOLIO)
            entries = [entry for entry in portfolio["entries"] if entry["id"] not in ids]
            if entries != portfolio["entries"]:
                portfolio["entries"] = entries
                writes[PORTFOLIO] = yaml_bytes(portfolio)
            state = parse_state(files)
            for course_id in state.courses:
                if course_id in ids:
                    continue
                name = f"content/data/courses/{course_id.split('/')[-1]}.yaml"
                contract = load_yaml(files[name] or b"", name)
                before = copy.deepcopy(contract)
                for section in contract["toc"]:
                    section["chapters"] = [chapter for chapter in section["chapters"] if chapter not in ids]
                contract["planned"]["chapters"] = [p for p in contract["planned"].get("chapters", []) if p["chapter_id"] not in ids]
                if contract.get("overview") in ids:
                    contract["overview"] = None
                if contract != before:
                    writes[name] = yaml_bytes(contract)
            if any(link["kind"] == "kanban" for link in plan["detached_links"]):
                board = load_yaml(files[KANBAN] or b"", KANBAN)
                for card in board["cards"]:
                    card["artifact_ids"] = [link for link in card.get("artifact_ids", []) if link not in ids]
                writes[KANBAN] = yaml_bytes(board)
            if any(link["kind"] == "profile" for link in plan["detached_links"]):
                profile = load_yaml(files[PROFILE] or b"", PROFILE)
                for project in profile.get("projects", []):
                    if project.get("artifact_id") in ids:
                        project["artifact_id"] = None
                writes[PROFILE] = yaml_bytes(profile)
            archive = f"archive/deleted/{uuid4().hex}"
            # Preserve exact authored bytes before removing their active locations.
            for source in plan["archive_files"]:
                writes[f"{archive}/{source}"] = files[source]
            writes[f"{archive}/record.json"] = json.dumps({**plan, "saved_data": {name: (files[name] or b"").decode() for name in writes if name.startswith("content/data/")}}, ensure_ascii=False, indent=2).encode()
            for source in plan["archive_files"]:
                writes[source] = None
            return {"deleted": sorted(ids), "archive_path": archive, "detached_links": plan["detached_links"]}, writes
        return self._mutate("delete artifact", apply, expected_revision)

    def update(self, artifact_id: str, patch: dict[str, Any], expected_revision: str | None = None, *, figure_image: bytes | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            catalog = self._catalog(files)
            record = self._find(catalog, artifact_id)
            before = copy.deepcopy(record)
            updates = copy.deepcopy(patch)
            if record["kind"] == "gallery" and "lifecycle" in updates:
                raise ServiceError("Change each photo's lifecycle in Personal; gallery lifecycle is derived automatically", paths=[PHOTOS])
            detail, plan = updates.pop("detail", None), updates.pop("plan", None)
            contract = updates.pop("contract", None)
            if "id" in updates or "kind" in updates:
                raise ServiceError("stable ID and artifact kind cannot be changed")
            if isinstance(updates.get("planned"), dict):
                updates["planned"] = {**record.get("planned", {}), **updates["planned"]}
            record.update(updates)
            normalized = Artifact.model_validate(record)
            if record["lifecycle"] == "planned" and record["kind"] not in {"gallery", "project"}:
                normalized.visibility = "private"
            elif updates.get("lifecycle") == "published" and before["lifecycle"] != "published":
                normalized.visibility = updates.get("visibility", "public")
            record.clear()
            record.update(normalized.model_dump(mode="json", exclude_none=True))
            writes: dict[str, bytes] = {}
            if contract is not None:
                if record["kind"] != "course":
                    raise ServiceError("Only courses have a course contract.")
                name = f"content/data/courses/{record['id'].split('/')[-1]}.yaml"
                current = load_yaml(files[name] or b"", name)
                if contract.get("id", record["id"]) != record["id"]:
                    raise ServiceError("Course contract ID cannot be changed.")
                for key in ("planned", "actualized"):
                    if isinstance(contract.get(key), dict):
                        contract[key] = {**current.get(key, {}), **contract[key]}
                current.update(contract)
                writes[name] = yaml_bytes(current)
            if figure_image is not None:
                if record["kind"] == "portfolio":
                    image_path = portfolio_figure(record["id"], figure_image)
                    detail = {**(detail or {}), "figure_path": image_path}
                elif record["kind"] == "course":
                    image_path = uploaded_image("courses", record["id"], figure_image)
                    record["cover"] = image_path
                else:
                    raise ServiceError("Featured images can only be uploaded for portfolio entries or courses.")
                writes[image_path] = figure_image
            if detail is not None:
                portfolio = load_yaml(files[PORTFOLIO] or b"", PORTFOLIO)
                target = next((p for p in portfolio["entries"] if p["id"] == record["id"]), None)
                if target is None:
                    raise ServiceError("no portfolio detail to update")
                if isinstance(detail.get("planned"), dict):
                    detail["planned"] = {**target.get("planned", {}), **detail["planned"]}
                target.update(detail)
                writes[PORTFOLIO] = yaml_bytes(portfolio)
            if record["kind"] == "chapter":
                if record.get("parent") != before.get("parent"):
                    raise ServiceError("moving chapters between courses requires an explicit import")
                name = f"content/data/courses/{record['parent'].split('/')[-1]}.yaml"
                course = load_yaml(files[name] or b"", name)
                section = next((s for s in course["toc"] if s["id"] == record["section"]), None)
                if section is None:
                    raise ServiceError("unknown course section", paths=[name])
                if record["section"] != before["section"]:
                    for item in course["toc"]:
                        item["chapters"] = [c for c in item["chapters"] if c != record["id"]]
                    section["chapters"].append(record["id"])
                existing = next((p for p in course["planned"].get("chapters", []) if p["chapter_id"] == record["id"]), None)
                if existing is not None:
                    existing.update(plan or {})
                    existing["section"] = record["section"]
                elif plan is not None:
                    course["planned"].setdefault("chapters", []).append({"chapter_id": record["id"], "section": record["section"], **plan})
                writes[name] = yaml_bytes(course)
                source = record["path"]
                if record["title"] != before["title"] and files.get(source) is not None:
                    notebook = nbformat.reads((files[source] or b"").decode(), as_version=4)
                    if h1s(notebook) != [before["title"]]:
                        raise ServiceError("existing H1 differs from old title; repair source first", paths=[source])
                    from markdown_it import MarkdownIt
                    for cell in notebook.cells:
                        if cell.cell_type != "markdown":
                            continue
                        tokens = MarkdownIt().parse(cell.source)
                        for index, token in enumerate(tokens):
                            if token.type == "heading_open" and token.tag == "h1" and displayed_text(tokens[index + 1]) == before["title"] and token.map:
                                lines = cell.source.splitlines()
                                lines[token.map[0]:token.map[1]] = [f"# {record['title']}"]
                                cell.source = "\n".join(lines)
                    writes[source] = nbformat.writes(notebook).encode()
            if record["kind"] != "chapter" and record["title"] != before["title"]:
                source = source_path(Artifact.model_validate(before), parse_state(files))
                if source and files.get(source) is not None:
                    notebook = nbformat.reads((files[source] or b"").decode(), as_version=4)
                    if not has_content(notebook, before["title"]):
                        for cell in notebook.cells:
                            if cell.cell_type == "markdown" and cell.source.strip():
                                cell.source = f"# {record['title']}\n"
                        writes[source] = nbformat.writes(notebook).encode()
            writes[CATALOG] = yaml_bytes(catalog)
            candidate = dict(files)
            candidate.update(writes)
            state = parse_state(candidate)
            affected = [{"id": a.id, "eligible": eligible(a, state.artifacts)} for a in state.artifacts if a.parent == record["id"]]
            return {"artifact": record, "affected_children": affected}, writes
        return self._mutate("update", apply, expected_revision)

    def start(self, artifact_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            catalog = self._catalog(files)
            record = self._find(catalog, artifact_id)
            if record["lifecycle"] != "planned" or record["kind"] not in {"post", "chapter", "portfolio", "personal", "course"}:
                raise ServiceError("start requires a planned notebook entry")
            state = parse_state(files)
            artifact = next(a for a in state.artifacts if a.id == record["id"])
            writes: dict[str, bytes] = {}
            project_path = None
            if artifact.kind == "portfolio":
                detail = next(p for p in state.portfolio if p.id == artifact.id)
                detail.notebook_path = detail.notebook_path or f"content/notebooks/portfolio/{artifact.id.split('/')[-1]}.ipynb"
                if detail.project_source == "active":
                    name = project_name(detail.project_name or artifact.id.split("/")[-1])
                    detail.project_name = name
                    project_path, project_writes = self._initialize_project(catalog, name, "private")
                    writes.update(project_writes)
                portfolio = load_yaml(files[PORTFOLIO] or b"", PORTFOLIO)
                target = next(p for p in portfolio["entries"] if p["id"] == artifact.id)
                target.update(notebook_path=detail.notebook_path, project_name=detail.project_name)
                if not (detail.abstract or "").strip():
                    target["abstract"] = (artifact.description or "").strip() or portfolio_abstract(detail.planned) or None
                writes[PORTFOLIO] = yaml_bytes(portfolio)
            path = source_path(artifact, state)
            if path is None:
                raise ServiceError("configure notebook_path before starting")
            if self.store.safe_path(path).exists() or files.get(path) is not None:
                raise ServiceError("start refuses an existing source notebook", code="conflict", status=412, paths=[path])
            sections = draft_sections(artifact.kind, self._planning(artifact, state))
            notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell(body) for body in [f"# {artifact.title}\n", *sections]], metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
            record["lifecycle"] = "draft"
            record["visibility"] = "private"
            writes.update({CATALOG: yaml_bytes(catalog), path: nbformat.writes(notebook).encode()})
            result = {"artifact": record, "source_path": path, "has_source": True, "editor_url": "vscode://file/" + quote(str(self.root / path), safe="/")}
            if project_path:
                result["project_path"] = project_path
            return result, writes
        return self._mutate("start", apply, expected_revision)

    def _initialize_project(self, catalog: dict[str, Any], name: str, visibility: Literal["public", "private"]) -> tuple[str, dict[str, bytes]]:
        name = project_name(name)
        path = f"projects/{name}"
        destination = self.store.safe_path(path)
        if destination.is_symlink() and not destination.exists():
            raise ServiceError("Project destination is a broken symlink.", code="conflict", status=412, paths=[path])
        matching = next((item for item in catalog["artifacts"] if item["kind"] == "project" and item.get("path") == path), None)
        identifier = f"project/{name}"
        if matching is None:
            if any(item["id"] == identifier for item in catalog["artifacts"]):
                raise ServiceError(f"ID already registered: {identifier}")
            catalog["artifacts"].append(Artifact(id=identifier, kind="project", title=name.replace("-", " ").title(), path=path, lifecycle="draft", visibility=visibility).model_dump(mode="json", exclude_none=True))
        if destination.exists():
            if not destination.is_dir():
                raise ServiceError("Project destination must be a directory.", paths=[path])
            return path, {}
        return path, scaffold_project(self.root, name)

    def create_project(self, name: str, expected_revision: str | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            project_name(name)
            path = f"projects/{name}"
            if self.store.safe_path(path).exists() or self.store.safe_path(path).is_symlink():
                raise ServiceError("make project refuses an existing project directory.", code="conflict", status=412, paths=[path])
            catalog = self._catalog(files)
            path, writes = self._initialize_project(catalog, name, "public")
            writes[CATALOG] = yaml_bytes(catalog)
            return {"project_path": path}, writes
        return self._mutate("create_project", apply, expected_revision)

    def publish(self, artifact_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        with self.store.locked():
            files = self.store.inputs()
            if expected_revision is not None and expected_revision.strip('"') != revision(files):
                raise ServiceError("stale workspace revision", code="conflict", status=412, paths=[CATALOG])
            catalog = self._catalog(files)
            record = self._find(catalog, artifact_id)
            if record["kind"] == "chapter":
                parent = self._find(catalog, record["parent"])
                if parent["visibility"] != "public" or parent["lifecycle"] != "published":
                    raise ServiceError("publish the public parent course first")
            captured = revision(files)
        return self.update(artifact_id, {"lifecycle": "published", "visibility": "public"}, expected_revision or captured)

    def draft(self, artifact_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        with self.store.locked():
            files = self.store.inputs()
            if expected_revision is not None and expected_revision.strip('"') != revision(files):
                raise ServiceError("stale workspace revision", code="conflict", status=412, paths=[CATALOG])
            record = self._find(self._catalog(files), artifact_id)
            if record["lifecycle"] != "published":
                raise ServiceError("draft returns published entries to draft; use start for planned content")
            captured = revision(files)
        return self.update(artifact_id, {"lifecycle": "draft"}, expected_revision or captured)

    def _data_path(self, name: str) -> str:
        names = {"profile": PROFILE, "portfolio": PORTFOLIO, "photos": PHOTOS, "settings": SETTINGS, "kanban": KANBAN}
        if name.startswith("course/") and re.fullmatch(r"[\w-]+", name[7:]):
            return f"content/data/courses/{name[7:]}.yaml"
        if name not in names:
            raise ServiceError("unknown structured record", code="not_found", status=404)
        return names[name]

    def read_data(self, name: str) -> dict[str, Any]:
        with self.store.locked():
            files = self.store.inputs()
            path = self._data_path(name)
            if name == "kanban" and files.get(path) is None:
                return {"data": Kanban().model_dump(mode="json"), "revision": revision(files)}
            return {"data": load_yaml(files.get(path) or b"", path), "revision": revision(files)}

    def update_data(self, name: str, payload: dict[str, Any], expected_revision: str | None = None) -> dict[str, Any]:
        if name == "photos":
            return self.update_gallery(payload, expected_revision)
        path = self._data_path(name)
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            return {"data": payload}, {path: yaml_bytes(payload)}
        return self._mutate(f"update {name}", apply, expected_revision)

    def plan_file(self, name: str) -> str:
        path = self.store.safe_path(name)
        if not path.resolve().is_relative_to(self.root / ".tmp") or not path.is_file():
            raise ServiceError("plan files must be existing files under <repo>/.tmp/", paths=[name])
        return path.read_text(encoding="utf-8")

    def install_migration(self, writes: dict[str, bytes], expected_revision: str | None = None) -> dict[str, Any]:
        return self._mutate("migrate", lambda files: ({"migrated": True}, writes), expected_revision)

    def batch(self, updates: list[dict[str, Any]], data: dict[str, dict[str, Any]], expected_revision: str | None = None) -> dict[str, Any]:
        """Repair several related records, validating the combined final state."""
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            catalog = self._catalog(files)
            changed = []
            for update in updates:
                record = self._find(catalog, update["id"])
                patch = update["patch"]
                if "id" in patch or "kind" in patch:
                    raise ServiceError("batch cannot change stable IDs or kinds")
                record.update(patch)
                normalized = Artifact.model_validate(record).model_dump(mode="json", exclude_none=True)
                record.clear()
                record.update(normalized)
                changed.append(normalized)
            writes = {self._data_path(name): yaml_bytes(payload) for name, payload in data.items()}
            if "photos" in data:
                photos = Photos.model_validate(data["photos"])
                lifecycle = "published" if any(photo.lifecycle == "published" for photo in photos.photos) else "planned"
                for record in catalog["artifacts"]:
                    if record["kind"] == "gallery":
                        record["lifecycle"] = lifecycle
            writes[CATALOG] = yaml_bytes(catalog)
            return {"artifacts": changed, "data": data}, writes
        return self._mutate("batch", apply, expected_revision)

    def update_gallery(self, payload: dict[str, Any], expected_revision: str | None = None, *, photo_images: dict[int, bytes] | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            catalog = self._catalog(files)
            galleries = [a for a in catalog["artifacts"] if a["kind"] == "gallery"]
            if len(galleries) != 1:
                raise ServiceError("gallery save requires exactly one registered gallery")
            data = copy.deepcopy(payload)
            rows = data.get("photos", [])
            writes: dict[str, bytes] = {}
            for index, image in (photo_images or {}).items():
                if not 0 <= index < len(rows):
                    raise ServiceError("Unknown photo for image upload.")
                path = uploaded_image("photos", str(rows[index].get("heading", "photo")), image)
                rows[index]["path"] = path
                writes[path] = image
            photos = Photos.model_validate(data)
            for row, photo in zip(rows, photos.photos, strict=True):
                row["path"] = photo.path
            galleries[0]["lifecycle"] = "published" if any(photo.lifecycle == "published" for photo in photos.photos) else "planned"
            writes.update({CATALOG: yaml_bytes(catalog), PHOTOS: yaml_bytes(data)})
            return {"artifacts": [], "data": {"photos": data}}, writes
        return self._mutate("update gallery", apply, expected_revision)

    def import_notebook(self, source: Path, kind: str, name: str, *, course: str | None = None, section: str | None = None, title: str | None = None, expected_revision: str | None = None) -> dict[str, Any]:
        """Import through the supported normalizer, preserving cells and outputs."""
        from .migration import normalize_notebook, read_source_notebook
        if kind not in {"post", "personal", "chapter"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ServiceError("import requires a safe notebook name and post/personal/chapter kind")
        notebook, header = normalize_notebook(read_source_notebook(source))
        title = title or header.get("title") or name.replace("-", " ").title()
        if kind == "chapter":
            if not course or not re.fullmatch(r"[\w-]+", course.removeprefix("course/")):
                raise ServiceError("chapter import requires a course slug")
            course = course.removeprefix("course/")
            notebook, _ = normalize_notebook(notebook, chapter_title=title)
        lifecycle = "draft" if has_content(notebook, title) else "planned"
        tier = f"courses/{course}" if kind == "chapter" else "posts" if kind == "post" else "personal"
        path = f"content/notebooks/{tier}/{name}.ipynb"
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            if files.get(path) is not None or self.store.safe_path(path).exists():
                raise ServiceError("import refuses existing destination", code="conflict", status=412, paths=[path])
            catalog = self._catalog(files)
            artifact_id = f"course/{course}/{name}" if kind == "chapter" else f"{kind}/{name}"
            record: dict[str, Any] = {"id": artifact_id, "kind": kind, "title": title, "path": path, "lifecycle": lifecycle, "categories": header.get("categories", []), "tags": header.get("tags", []), "description": header.get("description"), "date": str(header["date"]) if header.get("date") else None}
            writes: dict[str, bytes] = {}
            if kind == "chapter":
                contract_path = f"content/data/courses/{course}.yaml"
                contract = load_yaml(files.get(contract_path) or b"", contract_path)
                selected = next((s for s in contract["toc"] if section is None or s["id"] == section), None)
                if selected is None:
                    raise ServiceError("unknown course section")
                record.update(parent=f"course/{course}", section=selected["id"], toc_title=title)
                selected["chapters"].append(artifact_id)
                if lifecycle == "planned":
                    raise ServiceError("empty chapter imports require a plan; use new chapter instead")
                writes[contract_path] = yaml_bytes(contract)
            artifact = Artifact.model_validate(record)
            catalog["artifacts"].append(artifact.model_dump(mode="json", exclude_none=True))
            writes.update({CATALOG: yaml_bytes(catalog), path: nbformat.writes(notebook).encode()})
            return {"artifact": artifact.model_dump(mode="json")}, writes
        return self._mutate("import", apply, expected_revision)
