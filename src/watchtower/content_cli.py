"""JSON CLI adapters for the file-backed publishing system."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

import typer

from . import planning
from .services.content import ContentService
from .services.workspace import ServiceError, load_yaml

# Option declarations shared by the planning commands, so each spells and describes them alike.
SummaryFlag = Annotated[str | None, typer.Option("--summary", help="One public sentence: post or course listing, portfolio abstract, or chapter table row.")]
InternalNotesFlag = Annotated[str | None, typer.Option("--internal-notes", help="CMS-only Markdown, never shown on the site. Next steps belong in Kanban: wt kanban add --link ID.")]
PlanFileFlag = Annotated[str | None, typer.Option("--plan-file", help="Markdown under .tmp/ with ## sections named by label or key.")]
TagFlag = Annotated[list[str] | None, typer.Option("--tag", help="Tag; repeat for several.")]
StartFlag = Annotated[bool, typer.Option("--start", help="Also create the draft notebook; the output reports both results.")]
ExpectedRevisionFlag = Annotated[str | None, typer.Option("--expected-revision", help="Workspace revision to save against. A stale write fails and is never retried.")]
# Earlier spellings: still accepted, hidden from help.
DescriptionFlag = Annotated[str | None, typer.Option("--description", hidden=True)]
AbstractFlag = Annotated[str | None, typer.Option("--abstract", hidden=True)]
PlannedContentFlag = Annotated[str | None, typer.Option("--planned-content", hidden=True)]
PlannedLabFlag = Annotated[str | None, typer.Option("--planned-lab-and-evidence", hidden=True)]
IntroductionFlag = Annotated[str | None, typer.Option("--introduction", hidden=True)]
WhatItContainsFlag = Annotated[str | None, typer.Option("--what-it-contains", hidden=True)]
ScopeNotesFlag = Annotated[str | None, typer.Option("--scope-notes", hidden=True)]

# Flag -> (planning field, kinds it applies to; None means every kind with planning fields).
PLAN_FLAGS: dict[str, tuple[str, frozenset[str] | None]] = {
    "--summary": ("summary", None),
    "--description": ("summary", None),
    "--abstract": ("summary", frozenset({"portfolio"})),
    "--internal-notes": ("internal_notes", None),
    "--planned-content": ("content", frozenset({"post", "chapter"})),
    "--planned-lab-and-evidence": ("lab_and_evidence", frozenset({"chapter"})),
    "--introduction": ("introduction", frozenset({"portfolio"})),
    "--what-it-contains": ("what_it_contains", frozenset({"portfolio"})),
}
REMOVED_FLAGS = {
    "--scope-notes": "--scope-notes was removed: scope now belongs in --internal-notes (CMS-only) or in the ## What it contains section of the plan file.",
}


def active() -> bool:
    return Path("backend/data/catalog.yaml").exists()


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def slug(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ServiceError("name must be a single safe filename stem")
    return value


def merged(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    """Overlay a patch; nested objects merge so a partial plan keeps its sibling fields."""
    result = dict(base)
    for key, value in patch.items():
        current = result.get(key)
        result[key] = merged(current, value) if isinstance(current, dict) and isinstance(value, dict) else value
    return result


def section_labels(kind: str) -> str:
    return ", ".join(item["label"] for item in planning.plan_schema(kind))


def plan_sections(service: ContentService, kind: str, path: str) -> dict[str, str]:
    """Planning fields from the ## sections of a plan file under .tmp/."""
    text = service.plan_file(path)
    try:
        return planning.parse_plan_file(kind, text)
    except ValueError as error:
        raise ServiceError(f"{path}: {error}", paths=[path]) from error


def planning_patch(service: ContentService, kind: str, options: Mapping[str, str | None], plan_file: str | None) -> dict[str, Any]:
    """Service patch for planning flags and an optional plan file.

    A field comes from one source only: a flag and a plan-file section that both
    set it are an error, so neither value is dropped silently.
    """
    labels = planning.labels(kind)
    claimed: dict[str, tuple[str, str]] = {}

    def claim(key: str, origin: str, value: str) -> None:
        if key in claimed:
            raise ServiceError(f"{claimed[key][0]} and {origin} both set {labels.get(key, key)}; use one of them")
        claimed[key] = (origin, value)

    for option, value in options.items():
        if value is None:
            continue
        if option in REMOVED_FLAGS:
            raise ServiceError(REMOVED_FLAGS[option])
        field, kinds = PLAN_FLAGS[option]
        if kinds is not None and kind not in kinds:
            raise ServiceError(f"{option} does not apply to {kind} plans; use --plan-file with these ## sections: {section_labels(kind)}")
        claim(field, option, value)
    if plan_file is not None:
        for key, value in plan_sections(service, kind, plan_file).items():
            claim(key, f"{plan_file} ## {labels.get(key, key)}", value)
    notes = claimed.pop("internal_notes", None)
    values = {key: value for key, (_origin, value) in claimed.items()}
    try:
        patch = planning.plan_patch(kind, values) if values else {}
    except ValueError as error:
        raise ServiceError(str(error)) from error
    if notes is not None:
        patch["internal_notes"] = notes[1]
    return patch


def emit_created(service: ContentService, created: dict[str, Any], start: bool) -> None:
    """Print the new plan. With start, also create its draft; a failed start leaves the plan and says so."""
    if not start:
        emit(created)
        return
    identifier = created["artifact"]["id"]
    try:
        started = service.start(identifier, created["revision"])
    except ServiceError as error:
        raise ServiceError(f"plan created as {identifier}; start failed: {error}", code=error.code, status=error.status, paths=error.paths) from error
    emit({"created": created, "started": started})


def chapter_section(toc: list[dict[str, Any]], value: str | None) -> str:
    """Section ID for a chapter: the last section by default, otherwise a section ID or title."""
    if not toc:
        raise ServiceError("course has no sections; add one with wt new section")
    if value is None:
        return toc[-1]["id"]
    for section in toc:
        if value in {section["id"], section["title"]} or value.casefold() == section["title"].casefold():
            return section["id"]
    names = [section["title"] or section["id"] for section in toc]
    raise ServiceError(f"unknown course section {value}; sections: {', '.join(names)}")


def create_post(name: str, *, title: str | None, tags: list[str] | None, visibility: str, options: Mapping[str, str | None], plan_file: str | None, start: bool, expected_revision: str | None) -> None:
    service = ContentService()
    record = {"title": title or name.replace("-", " ").title(), "tags": tags or [], "visibility": visibility}
    created = service.create_post(name, merged(record, planning_patch(service, "post", options, plan_file)), expected_revision)
    emit_created(service, created, start)


def create_course(name: str, title: str, *, options: Mapping[str, str | None], plan_file: str | None, start: bool, expected_revision: str | None) -> None:
    service = ContentService()
    slug(name)
    record = {"id": f"course/{name}", "kind": "course", "title": title, "path": f"content/notebooks/courses/{name}"}
    created = service.create(merged(record, planning_patch(service, "course", options, plan_file)), expected_revision)
    emit_created(service, created, start)


def create_chapter(course: str, name: str, *, title: str | None, section: str | None, toc_title: str | None, options: Mapping[str, str | None], plan_file: str | None, start: bool, expected_revision: str | None) -> None:
    service = ContentService()
    slug(name)
    course_slug = slug(course.removeprefix("course/"))
    parent = service.inspect(f"course/{course_slug}")
    record = {
        "id": f"course/{course_slug}/{name}",
        "kind": "chapter",
        "parent": f"course/{course_slug}",
        "section": chapter_section(parent["contract"]["toc"], section),
        "title": title or name.replace("-", " ").title(),
        "toc_title": toc_title or title or name,
        "path": f"content/notebooks/courses/{course_slug}/{name}.ipynb",
    }
    created = service.create(merged(record, planning_patch(service, "chapter", options, plan_file)), expected_revision or parent["revision"])
    emit_created(service, created, start)


def create_portfolio(name: str, *, title: str | None, tags: list[str] | None, figure_path: str | None, figure_caption: str | None, project_path: str | None, options: Mapping[str, str | None], plan_file: str | None, start: bool, expected_revision: str | None) -> None:
    service = ContentService()
    slug(name)
    detail = {"notebook_path": f"content/notebooks/portfolio/{name}.ipynb", "project_path": project_path or f"projects/{name}", "figure_path": figure_path, "figure_caption": figure_caption}
    record = {"id": f"portfolio/{name}", "kind": "portfolio", "title": title or name.replace("-", " ").title(), "tags": tags or [], "detail": detail}
    created = service.create(merged(record, planning_patch(service, "portfolio", options, plan_file)), expected_revision)
    emit_created(service, created, start)


def install(app: typer.Typer) -> None:
    from .kanban_cli import install as install_kanban
    install_kanban(app)
    from .attachments_cli import install as install_attachments
    install_attachments(app)

    @app.command("plan")
    def plan(stable_id: str) -> None:
        """Read the plan for one exact stable ID; writes nothing.

        Output JSON: id, kind, title, lifecycle, source_path, summary (the public sentence), plan (saved planning fields by key), fields (per key: label, prompt, section, seed heading, core), internal_notes, build_brief, and revision.
        """
        emit(ContentService().read_plan(stable_id))

    @app.command("delete")
    def delete(name: str, dry_run: bool = typer.Option(False, "--dry-run"), cascade: bool = typer.Option(False, "--cascade"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Remove an entry, retaining files; use --cascade to include course chapters."""
        service = ContentService()
        emit(service.deletion_plan(name) if dry_run else service.delete(name, expected_revision, cascade=cascade))

    @app.command("start")
    def start(name: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Create a private draft seeded from the saved plan; retain internal notes separately."""
        emit(ContentService().start(name, expected_revision))

    @app.command("draft")
    def draft(name: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Return published content to draft, preserving its body and visibility."""
        emit(ContentService().draft(name, expected_revision))

    @app.command("update")
    def update(
        name: str,
        title: str | None = None,
        summary: SummaryFlag = None,
        description: DescriptionFlag = None,
        internal_notes: InternalNotesFlag = None,
        visibility: str | None = None,
        lifecycle: str | None = None,
        toc_title: str | None = typer.Option(None, "--toc-title"),
        section: str | None = None,
        tag: list[str] | None = typer.Option(None, "--tag"),
        add_tag: list[str] | None = typer.Option(None, "--add-tag"),
        remove_tag: list[str] | None = typer.Option(None, "--remove-tag"),
        planned_content: PlannedContentFlag = None,
        planned_lab_and_evidence: PlannedLabFlag = None,
        plan_file: PlanFileFlag = None,
        patch_file: str | None = typer.Option(None, "--patch-file"),
        expected_revision: ExpectedRevisionFlag = None,
    ) -> None:
        """Update metadata or planning fields through the validated service.

        Planning: --summary sets the one public sentence; --internal-notes is CMS-only. --plan-file changes only the ## sections it contains, and an empty section clears that field. Section names differ by kind: see the fields in wt plan ID. --patch-file takes a JSON patch that flags override. Tags (except courses and chapters): --tag replaces all tags; --add-tag and --remove-tag edit them.
        """
        service = ContentService()
        inspected = service.inspect(name)
        patch = json.loads(Path(patch_file).read_text()) if patch_file else {}
        for key, value in {"title": title, "visibility": visibility, "lifecycle": lifecycle, "toc_title": toc_title, "section": section}.items():
            if value is not None:
                patch[key] = value
        if tag is not None or add_tag or remove_tag:
            tags = list(tag if tag is not None else inspected["artifact"].get("tags", []))
            tags.extend(add_tag or [])
            removed = {t.strip().casefold() for t in remove_tag or []}
            patch["tags"] = [t for t in tags if t.strip().casefold() not in removed]
        options = {"--summary": summary, "--description": description, "--internal-notes": internal_notes, "--planned-content": planned_content, "--planned-lab-and-evidence": planned_lab_and_evidence}
        patch = merged(patch, planning_patch(service, inspected["artifact"]["kind"], options, plan_file))
        emit(service.update(name, patch, expected_revision or inspected["revision"]))

    @app.command("data")
    def data(name: str, file: str | None = None, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Read or replace profile, portfolio, photos, kanban, settings, or course/<slug>."""
        service = ContentService()
        if file:
            payload = load_yaml(Path(file).read_bytes(), file)
            emit(service.update_data(name, payload, expected_revision))
        else:
            emit(service.read_data(name))

    @app.command("batch")
    def batch(payload_file: str | None = typer.Argument(None, metavar="FILE"), file: str | None = typer.Option(None, "--file", help="JSON with updates [{id, patch}] and/or data {name: record}."), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Apply related metadata/data repairs as one validated transaction.

        Example payload: {"updates": [{"id": "post/example", "patch": {"description": "Revised"}}], "data": {}}
        """
        if (file is None) == (payload_file is None):
            raise typer.BadParameter("provide exactly one FILE or --file")
        payload = json.loads(Path(file or str(payload_file)).read_text())
        emit(ContentService().batch(payload.get("updates", []), payload.get("data", {}), expected_revision))

    @app.command("gallery")
    def gallery(file: str | None = None, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Read or save ordered photos with individual headings and lifecycles."""
        service = ContentService()
        if file:
            emit(service.update_gallery(load_yaml(Path(file).read_bytes(), file), expected_revision))
        else:
            emit(service.read_data("photos"))

    @app.command("build")
    def build(mode: str = "production") -> None:
        """Validate and render; promote only successful output."""
        from .services.build import BuildService
        result = BuildService(Path.cwd()).build(mode)
        emit(result)
        if result["status"] != "succeeded":
            raise typer.Exit(1)

    @app.command("preview")
    def preview(port: int = 4300) -> None:
        """Watch saved inputs and serve the working site, without execution."""
        from .services.build import BuildService
        BuildService(Path.cwd()).preview(port)

    @app.command("serve")
    def serve(port: int = 8000) -> None:
        """Serve the local CMS and typed JSON API on localhost."""
        import uvicorn

        from .api import create_app
        uvicorn.run(create_app(Path.cwd()), host="127.0.0.1", port=port)

    @app.command("migrate")
    def migrate(apply: bool = False, layout: bool = typer.Option(False, "--layout", help="Relocate content/data, content/assets and context files under backend; leave authored notebooks intact."), expected_revision: ExpectedRevisionFlag = None, reviewed_figures: bool = typer.Option(False, "--reviewed-figures"), preserve_gallery_prose: bool = typer.Option(False, "--preserve-gallery-prose"), title_choice: list[str] | None = typer.Option(None, "--title-choice")) -> None:
        """Review a legacy import or managed-storage move; --apply saves atomically."""
        if layout:
            from .services.layout import LayoutMigration
            if reviewed_figures or preserve_gallery_prose or title_choice:
                raise ServiceError("--layout cannot be combined with legacy import review options")
            emit(LayoutMigration(Path.cwd()).run(apply=apply, expected_revision=expected_revision))
            return
        from .services.migration import Migration
        if any((Path.cwd() / name).exists() for name in ("backend/data/catalog.yaml", "content/data/catalog.yaml")):
            raise ServiceError("This workspace is already migrated. Original inputs are retained under archive/2026-10-01/content-system-inputs; do not reapply migration over active content.", status=409, code="already_migrated")
        choices = dict(item.split("=", 1) for item in title_choice or [])
        candidate = Migration(Path.cwd(), reviewed_portfolio_figures=reviewed_figures, preserve_gallery_as_personal=preserve_gallery_prose, title_choices=choices).prepare()
        if apply:
            if not candidate["report"]["ready"]:
                emit(candidate["report"])
                raise typer.Exit(1)
            emit(ContentService().install_migration(candidate["files"], expected_revision))
        else:
            emit(candidate["report"])
