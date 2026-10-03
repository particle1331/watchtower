"""JSON CLI adapters for the file-backed publishing system."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import typer
from markdown_it import MarkdownIt

from .services.content import ContentService
from .services.workspace import ServiceError, load_yaml


def active() -> bool:
    return Path("content/data/catalog.yaml").exists()


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def slug(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ServiceError("name must be a single safe filename stem")
    return value


def split_plan(body: str, headings: list[str], required: list[str]) -> dict[str, str]:
    """Extract prescribed H2 bodies, ignoring heading examples in code fences."""
    tokens = MarkdownIt().parse(body)
    sections: list[tuple[str, int, int]] = []
    lines = body.splitlines()
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2" and token.map:
            heading = tokens[i + 1].content
            if heading in headings:
                sections.append((heading, token.map[0], token.map[1]))
    result: dict[str, str] = {}
    for i, (heading, _start, end) in enumerate(sections):
        if heading in result:
            raise ServiceError(f"duplicate plan section: {heading}")
        result[heading] = "\n".join(lines[end:sections[i + 1][1] if i + 1 < len(sections) else len(lines)]).strip()
    if any(not result.get(name) for name in required):
        raise ServiceError("plan file requires nonempty sections: " + ", ".join(required))
    result["introduction"] = "\n".join(lines[:sections[0][1] if sections else len(lines)]).strip()
    return result


def create_post(name: str, title: str | None, content: str | None, plan_file: str | None, tags: list[str] | None, description: str | None = None, visibility: str = "public", expected_revision: str | None = None) -> None:
    service = ContentService()
    slug(name)
    if plan_file and content is not None:
        raise ServiceError("choose --plan-file or --planned-content")
    body = service.plan_file(plan_file) if plan_file else content or ""
    emit(service.create({"id": f"post/{name}", "kind": "post", "title": title or name.replace("-", " ").title(), "path": f"content/notebooks/posts/{name}.ipynb", "visibility": visibility, "description": description, "tags": tags or [], "planned": {"content": body}}, expected_revision))


def create_chapter(course: str, name: str, title: str | None, toc_title: str | None, section: str | None, content: str | None, lab: str | None, plan_file: str | None, expected_revision: str | None = None) -> None:
    service = ContentService()
    slug(name)
    course_slug = slug(course.removeprefix("course/"))
    contract = service.read_data(f"course/{course_slug}")
    section = section or contract["data"]["toc"][-1]["id"]
    if plan_file:
        if content is not None or lab is not None:
            raise ServiceError("choose --plan-file or inline plan sections")
        sections = split_plan(service.plan_file(plan_file), ["Planned content", "Planned lab and evidence"], ["Planned content", "Planned lab and evidence"])
        content, lab = sections["Planned content"], sections["Planned lab and evidence"]
    emit(service.create({"id": f"course/{course_slug}/{name}", "kind": "chapter", "parent": f"course/{course_slug}", "section": section, "title": title or name.replace("-", " ").title(), "toc_title": toc_title or title or name, "path": f"content/notebooks/courses/{course_slug}/{name}.ipynb", "planned_content": content, "planned_lab_and_evidence": lab}, expected_revision or contract["revision"]))


def install(app: typer.Typer, new_app: typer.Typer) -> None:
    from .kanban_cli import install as install_kanban
    install_kanban(app)

    @app.command("delete")
    def delete(name: str, dry_run: bool = typer.Option(False, "--dry-run"), cascade: bool = typer.Option(False, "--cascade"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Remove an entry, retaining files; use --cascade to include course chapters."""
        service = ContentService()
        emit(service.deletion_plan(name) if dry_run else service.delete(name, expected_revision, cascade=cascade))

    @app.command("start")
    def start(name: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Materialize a planned notebook as a draft without executing cells."""
        emit(ContentService().start(name, expected_revision))

    @app.command("draft")
    def draft(name: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Return published content to draft, preserving its body and visibility."""
        emit(ContentService().draft(name, expected_revision))

    @app.command("update")
    def update(name: str, title: str | None = None, description: str | None = None, visibility: str | None = None, lifecycle: str | None = None, toc_title: str | None = typer.Option(None, "--toc-title"), section: str | None = None, tag: list[str] | None = typer.Option(None, "--tag"), add_tag: list[str] | None = typer.Option(None, "--add-tag"), remove_tag: list[str] | None = typer.Option(None, "--remove-tag"), planned_content: str | None = typer.Option(None, "--planned-content"), plan_file: str | None = typer.Option(None, "--plan-file"), patch_file: str | None = typer.Option(None, "--patch-file"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Update metadata through validated services; never edit source headers."""
        service = ContentService()
        inspected = service.inspect(name)
        patch = json.loads(Path(patch_file).read_text()) if patch_file else {}
        for key, value in {"title": title, "description": description, "visibility": visibility, "lifecycle": lifecycle, "toc_title": toc_title, "section": section}.items():
            if value is not None:
                patch[key] = value
        if tag is not None or add_tag or remove_tag:
            tags = list(tag if tag is not None else inspected["artifact"].get("tags", []))
            tags.extend(add_tag or [])
            removed = {t.strip().casefold() for t in remove_tag or []}
            patch["tags"] = [t for t in tags if t.strip().casefold() not in removed]
        if plan_file and planned_content is not None:
            raise ServiceError("choose --plan-file or --planned-content")
        if plan_file or planned_content is not None:
            body = service.plan_file(plan_file) if plan_file else planned_content
            patch["planned"] = {"content": body}
        emit(service.update(name, patch, expected_revision or inspected["revision"]))

    @app.command("data")
    def data(name: str, file: str | None = None, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Read or replace profile, portfolio, photos, settings, or course/<slug>."""
        service = ContentService()
        if file:
            payload = load_yaml(Path(file).read_bytes(), file)
            emit(service.update_data(name, payload, expected_revision))
        else:
            emit(service.read_data(name))

    @app.command("batch")
    def batch(file: str, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Apply related metadata/data repairs as one validated transaction."""
        payload = json.loads(Path(file).read_text())
        emit(ContentService().batch(payload.get("updates", []), payload.get("data", {}), expected_revision))

    @app.command("gallery")
    def gallery(file: str | None = None, expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Read or save ordered photos with individual headings and lifecycles."""
        service = ContentService()
        if file:
            emit(service.update_gallery(load_yaml(Path(file).read_bytes(), file), expected_revision))
        else:
            emit(service.read_data("photos"))

    @new_app.command("portfolio")
    def portfolio(name: str, title: str | None = None, abstract: str | None = None, figure_path: str | None = typer.Option(None, "--figure-path"), figure_caption: str | None = typer.Option(None, "--figure-caption"), project_name: str | None = typer.Option(None, "--project-name"), project_source: str = typer.Option("active", "--project-source"), archive_date: str | None = typer.Option(None, "--archive-date"), introduction: str | None = None, what_it_contains: str | None = typer.Option(None, "--what-it-contains"), scope_notes: str | None = typer.Option(None, "--scope-notes"), plan_file: str | None = typer.Option(None, "--plan-file"), expected_revision: str | None = typer.Option(None, "--expected-revision")) -> None:
        """Register a portfolio plan without creating its source notebook."""
        service = ContentService()
        slug(name)
        if plan_file:
            if any(v is not None for v in (introduction, what_it_contains, scope_notes)):
                raise ServiceError("choose a plan file or inline portfolio plan")
            parts = split_plan(service.plan_file(plan_file), ["What it contains", "Explore the project"], ["What it contains"])
            introduction, what_it_contains, scope_notes = parts["introduction"], parts["What it contains"], parts.get("Explore the project", "")
        detail = {"abstract": abstract, "figure_path": figure_path, "figure_caption": figure_caption, "project_name": project_name, "project_source": project_source, "archive_date": archive_date, "notebook_path": f"content/notebooks/portfolio/{name}.ipynb", "planned": {"introduction": introduction or "", "what_it_contains": what_it_contains or "", "scope_notes": scope_notes or ""}}
        emit(service.create({"id": f"portfolio/{name}", "kind": "portfolio", "title": title or name.replace("-", " ").title(), "detail": detail}, expected_revision))

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
    def migrate(apply: bool = False, reviewed_figures: bool = typer.Option(False, "--reviewed-figures"), preserve_gallery_prose: bool = typer.Option(False, "--preserve-gallery-prose"), title_choice: list[str] | None = typer.Option(None, "--title-choice")) -> None:
        """Inventory legacy inputs; apply only a candidate without review blockers."""
        from .services.migration import Migration
        if (Path.cwd() / "content/data/catalog.yaml").exists():
            raise ServiceError("This workspace is already migrated. Original inputs are retained under archive/2026-10-01/content-system-inputs; do not reapply migration over active content.", status=409, code="already_migrated")
        choices = dict(item.split("=", 1) for item in title_choice or [])
        candidate = Migration(Path.cwd(), reviewed_portfolio_figures=reviewed_figures, preserve_gallery_as_personal=preserve_gallery_prose, title_choices=choices).prepare()
        if apply:
            if not candidate["report"]["ready"]:
                emit(candidate["report"])
                raise typer.Exit(1)
            emit(ContentService().install_migration(candidate["files"]))
        else:
            emit(candidate["report"])
