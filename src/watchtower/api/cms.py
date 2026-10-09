"""Jinja forms provide a native fallback as well as HTMX fragment responses."""

import copy
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from watchtower import planning
from watchtower.models import KANBAN_COLUMNS
from watchtower.services.images import MAX_FIGURE_BYTES
from watchtower.services.workspace import ServiceError

from . import authoring
from .attachments import read_uploads

NAVIGATION = [("home", "Home"), ("resume", "Résumé"), ("portfolio", "Portfolio"), ("posts", "Posts"), ("courses", "Courses"), ("personal", "Personal"), ("kanban", "Kanban")]
KINDS = {"posts": "post", "courses": "course", "portfolio": "portfolio", "personal": "personal"}
CREATE_SECTIONS = {"post": "posts", "course": "courses", "chapter": "courses", "portfolio": "portfolio", "project": "portfolio", "personal": "personal"}
DATA_NAMES = {"home": "profile", "resume": "profile", "portfolio": "portfolio", "personal": "photos"}
PROFILE_FIELD_ORDER = {"contact": ["phone", "email", "github", "linkedin"], "employment": ["title", "company", "dates", "bullets", "tech"], "early_employment": ["title", "company", "dates", "bullets", "tech"], "skills": ["name", "entries"], "education": ["degree", "institution", "dates", "major", "awards", "thesis", "courses", "description"], "projects": ["title", "bullets", "artifact_id"]}


def paginate(request: Request, items: list[Any], page: int, page_size: int) -> tuple[list[Any], dict[str, Any]]:
    page_size = page_size if page_size in {10, 25, 50} else 10
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, page), pages)
    start = (page - 1) * page_size
    return items[start:start + page_size], {
        "page": page, "pages": pages, "page_size": page_size, "total": total,
        "start": start + 1 if total else 0, "end": min(start + page_size, total),
        "previous": str(request.url.include_query_params(page=page - 1, page_size=page_size)) if page > 1 else None,
        "next": str(request.url.include_query_params(page=page + 1, page_size=page_size)) if page < pages else None,
    }


def contact_links(contact: dict[str, Any]) -> list[dict[str, str]]:
    links = []
    for key, label in [("github", "GitHub"), ("linkedin", "LinkedIn")]:
        value = str(contact.get(key) or "").strip()
        if not value:
            continue
        url = value if value.startswith(("https://", "http://")) else "https://" + ("github.com/" + value if key == "github" else value)
        links.append({"label": label, "url": url})
    return links


def creation_slug(name: str) -> str:
    """Turn a user-facing name into a safe, predictable source-name segment."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-_").lower()
    if not slug:
        raise ServiceError("Enter a name containing at least one letter or number.")
    return slug


def form_revision(value: Any) -> str:
    if not value:
        raise ServiceError("Reload this form to obtain a workspace revision before saving.", code="precondition_required", status=428)
    return str(value)


def form_baseline(value: Any) -> dict[str, Any]:
    try:
        baseline = json.loads(str(value))
    except (ValueError, TypeError) as error:
        raise ServiceError("Invalid form snapshot; reload the editor.") from error
    if not isinstance(baseline, dict):
        raise ServiceError("Invalid form snapshot; reload the editor.")
    return baseline


def photo_editor_data(data: dict[str, Any]) -> dict[str, Any]:
    """Expose optional default states and missing required fields for explicit repair."""
    data = copy.deepcopy(data)
    for photo in data.get("photos", []):
        if isinstance(photo, dict):
            for key, value in {"heading": "", "path": "", "caption": "", "lifecycle": "draft", "width": ""}.items():
                photo.setdefault(key, value)
    return data


def blank_record(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: blank_record(item) for key, item in value.items()}
    if isinstance(value, list):
        return []
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    return ""


def is_complex_collection(prefix: tuple[str, ...]) -> bool:
    if not prefix:
        return False
    return prefix[-1] in {"photos", "toc", "employment", "early_employment", "skills", "education", "projects"} or prefix == ("entries",) or prefix[-1] == "chapters" and "planned" in prefix


def collections(data: Any, prefix: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            result.extend(collections(value, (*prefix, key)))
    elif isinstance(data, list) and (bool(data) and isinstance(data[0], dict) or not data and is_complex_collection(prefix)):
        defaults = {"photos": {"heading": "", "path": "", "caption": "", "lifecycle": "draft"}, "toc": {"id": "", "title": "", "chapters": []}, "chapters": {"chapter_id": "", "section": "", "content": "", "lab_and_evidence": ""}, "entries": {"id": "", "notebook_path": "", "project_path": "", "abstract": None, "figure_path": None, "figure_caption": None, "planned": {}}, "projects": {"title": "", "bullets": [], "artifact_id": None}, "employment": {"title": "", "company": "", "dates": "", "bullets": []}, "early_employment": {"title": "", "company": "", "dates": "", "bullets": []}, "education": {"institution": "", "degree": "", "dates": ""}, "skills": {"name": "", "entries": []}}
        prototype = blank_record(data[0]) if data else defaults.get(prefix[-1] if prefix else "", {})
        if prefix[-1] == "photos":
            prototype = {**defaults["photos"], "width": "", **prototype, "lifecycle": "draft"}
        if prefix == ("entries",):
            prototype = {**prototype, **defaults["entries"]}
        result.append({"path": prefix, "label": " / ".join(prefix), "rows": list(enumerate(data)), "prototype": prototype, "fields": form_fields(prototype, prefix)})
        for index, value in enumerate(data):
            result.extend(collections(value, (*prefix, str(index))))
    return result


def form_fields(data: Any, prefix: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Render primitive values individually, preserving nested list order and types."""
    fields: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            fields.extend(form_fields(value, (*prefix, str(key))))
    elif isinstance(data, list):
        if not data and is_complex_collection(prefix):
            return fields
        if all(isinstance(value, str) for value in data):
            fields.append({"name": json.dumps(prefix), "label": " / ".join(prefix), "value": "\n".join(data), "type": "lines"})
        else:
            for index, value in enumerate(data):
                fields.extend(form_fields(value, (*prefix, str(index))))
    else:
        fields.append({"name": json.dumps(prefix), "label": " / ".join(prefix), "value": data if data is not None else "", "type": "photo_width" if prefix and prefix[-1] == "width" and "photos" in prefix else "photo_lifecycle" if prefix and prefix[-1] == "lifecycle" and "photos" in prefix else "bool" if isinstance(data, bool) else "int" if isinstance(data, int) else "float" if isinstance(data, float) else "text"})
        if prefix and prefix[0] == "photos" and prefix[-1] == "path":
            fields[-1].update(type="photo_image", photo_index=prefix[1] if len(prefix) == 3 else None)
    return fields


def field_groups(fields: list[dict[str, Any]], data: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep fields with their owning record and expose human-readable row names."""
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    collection_paths = {tuple(item["path"]) for item in collections(data)}
    for field in fields:
        path = tuple(json.loads(field["name"]))
        if field["label"] in {"id", "kind", "version", "route"} or field["label"] == "cover" and data.get("kind") != "course":
            continue
        parent = path[:-1]
        if parent not in groups:
            node: Any = data
            labels: list[str] = []
            row_action = None
            for key in parent:
                if isinstance(node, list):
                    index = int(key)
                    count = len(node)
                    node = node[index]
                    title = next((node.get(key) for key in ("heading", "title", "name", "company", "institution", "id", "chapter_id") if node.get(key)), "Untitled") if isinstance(node, dict) else str(node)
                    if isinstance(node, dict) and parent[0] in {"employment", "early_employment"} and node.get("title") and node.get("company"):
                        title = node["title"] + " · " + node["company"]
                    elif isinstance(node, dict) and parent[0] == "education" and node.get("degree") and node.get("institution"):
                        title = node["degree"] + " · " + node["institution"]
                    labels.append(f"{index + 1}. {title}")
                    if key == parent[-1] and parent[:-1] in collection_paths:
                        row_action = {"path": parent[:-1], "index": index, "count": count}
                else:
                    node = node[key]
                    labels.append(key.replace("_", " ").capitalize())
            groups[parent] = {"title": labels[-1] if labels else "General", "context": " / ".join(labels[:-1]), "fields": [], "row_action": row_action}
        groups[parent]["fields"].append({**field, "caption": path[-1].replace("_", " ").capitalize()})
    priority: list[tuple[str, ...]] = [(), ("contact",), ("employment",), ("early_employment",), ("skills",), ("education",), ("projects",)] if "contact" in data and "name" in data else [()]
    ordered = sorted(groups, key=lambda path: priority.index(path[:1]) if path[:1] in priority else len(priority))
    for path in ordered:
        field_order = ["name", "summary", "homepage_intro"] if not path else PROFILE_FIELD_ORDER.get(path[0], []) if "contact" in data and "name" in data else []
        if field_order:
            groups[path]["fields"].sort(key=lambda field: field_order.index(json.loads(field["name"])[-1]) if json.loads(field["name"])[-1] in field_order else len(field_order))
    for path in ordered:
        group = groups[path]
        if path and path[0] in {"employment", "early_employment", "skills", "education"}:
            group["fold"] = True
        else:
            group["fold"] = bool(path and path != ("contact",) and path[0] != "photos" and (sum(bool(field["value"]) for field in group["fields"]) > 5 or any(len(str(field["value"])) > 240 for field in group["fields"])))
    return [groups[path] for path in ordered]


def apply_fields(data: dict[str, Any], form: Any) -> dict[str, Any]:
    result = copy.deepcopy(data)
    for name, value in form.multi_items():
        if not name.startswith("field:"):
            continue
        try:
            path = json.loads(name[6:])
        except json.JSONDecodeError:
            # Multipart field names escape quotes in Content-Disposition.
            path = json.loads(name[6:].replace("%22", '"'))
        if not isinstance(path, list) or not path:
            raise ValueError("Invalid field path")
        node: Any = result
        for key in path[:-1]:
            node = node[int(key)] if isinstance(node, list) else node[key]
        key = int(path[-1]) if isinstance(node, list) else path[-1]
        previous = node[key]
        if previous is None and value == "":
            node[key] = None
        elif isinstance(previous, list):
            submitted = form.getlist(name) if form.get("relationship:" + name) else [value]
            lines = [line.strip() for item in submitted for line in str(item).splitlines() if line.strip()]
            node[key] = list(dict.fromkeys(lines)) if form.get("relationship:" + name) else lines
        elif isinstance(previous, bool):
            node[key] = value == "true"
        elif isinstance(previous, int):
            try:
                node[key] = int(value)
            except ValueError:
                node[key] = str(value)
        elif isinstance(previous, float):
            try:
                node[key] = float(value)
            except ValueError:
                node[key] = str(value)
        else:
            node[key] = str(value)
    operation = form.get("collection_action")
    if operation:
        operation = json.loads(str(operation))
        node: Any = result
        for key in operation["path"]:
            node = node[int(key)] if isinstance(node, list) else node[key]
        if not isinstance(node, list):
            raise ValueError("The selected collection is not a list")
        index = operation.get("index", 0)
        if operation["action"] == "remove":
            node.pop(index)
        elif operation["action"] in {"up", "down"}:
            destination = index + (-1 if operation["action"] == "up" else 1)
            if 0 <= destination < len(node):
                node[index], node[destination] = node[destination], node[index]
        elif operation["action"] == "add":
            prototype = operation["prototype"]
            wrapper = {"new": prototype}
            new_values = []
            for name, value in form.multi_items():
                if name.startswith("new:"):
                    path = json.loads(name[4:].replace("%22", '"'))
                    if path[:len(operation["path"])] == operation["path"]:
                        new_values.append(("field:" + json.dumps(["new", *path[len(operation["path"]):]]), value))
            from starlette.datastructures import FormData
            node.append(apply_fields(wrapper, FormData(new_values))["new"])
    return result


async def photo_uploads(form: Any, row_count: int) -> dict[int, bytes]:
    """Keep selected files with their rows when a submission reorders the list."""
    action = json.loads(str(form.get("collection_action", "{}")))
    images = {}
    for name, upload in form.multi_items():
        if not isinstance(upload, UploadFile) or not upload.filename:
            continue
        index = None
        if name.startswith("photo_image:"):
            index = int(name.split(":", 1)[1])
            if not 0 <= index < row_count:
                raise ServiceError("Unknown photo for image upload.")
            if action.get("path") == ["photos"]:
                selected = action.get("index", 0)
                operation = action.get("action")
                if operation == "remove":
                    if index == selected:
                        await upload.close()
                        continue
                    index -= int(index > selected)
                elif operation in {"up", "down"}:
                    destination = selected + (-1 if operation == "up" else 1)
                    if 0 <= destination < row_count:
                        if index == selected:
                            index = destination
                        elif index == destination:
                            index = selected
        elif name == "new_photo_image" and action.get("path") == ["photos"] and action.get("action") == "add":
            index = row_count
        try:
            if index is not None:
                images[index] = await upload.read(MAX_FIGURE_BYTES + 1)
        finally:
            await upload.close()
    return images


def cms_router(root: Path) -> APIRouter:
    router = APIRouter(prefix="/cms", include_in_schema=False)
    templates = Jinja2Templates(directory=str(root / "frontend/templates/cms"))
    templates.env.filters["urlpath"] = lambda value: quote(str(value), safe="/")

    def render(request: Request, template: str, context: dict[str, Any], status: int = 200) -> HTMLResponse:
        def visible_field(field: dict[str, Any]) -> bool:
            path = json.loads(field["name"])
            return not path or path[-1] not in {"project_name", "project_source", "archive_date"}

        if "fields" in context:
            context["fields"] = [field for field in context["fields"] if visible_field(field)]
        for collection in context.get("collections", []):
            collection["fields"] = [field for field in collection["fields"] if visible_field(field)]
        context.update({"navigation": NAVIGATION, "root": str(root)})
        try:
            context.setdefault("relationship_artifacts", request.app.state.content.list()["artifacts"])
        except ServiceError:
            context.setdefault("relationship_artifacts", [])
        if "fields" in context and context.get("sections") is None:
            data = context.get("artifact", context.get("data", {}))
            for field in context["fields"]:
                path = json.loads(field["name"])
                if path[-1] == "overview" or path[-1] == "chapter_id" or path[-1] == "chapters" and "toc" in path:
                    field.update(relationship_kind="chapter", relationship_parent=data.get("id", ""))
            context["groups"] = field_groups(context["fields"], data)
            if context.get("artifact"):
                notes = []
                for group in context["groups"]:
                    notes.extend(field for field in group["fields"] if field["label"] == "internal_notes")
                    group["fields"] = [field for field in group["fields"] if field["label"] != "internal_notes"]
                for field in notes:
                    field.update(prompt="Markdown notes for research, decisions, and future revisions. Excluded from site pages; included in the build brief.")
                context["groups"] = [group for group in context["groups"] if group["fields"]]
                if notes:
                    context["notes_section"] = {"title": "Internal notes", "fields": notes, "fold": False}
        if context.get("name") == "profile":
            sections = []
            for key, label in [(None, "General"), ("contact", "Contact"), ("employment", "Employment"), ("early_employment", "Early employment"), ("skills", "Skills"), ("education", "Education"), ("projects", "Projects")]:
                groups = [{**group, "context": ""} for group in context["groups"] if (json.loads(group["fields"][0]["name"])[:-1] or [None])[0] == key]
                section_collections = [collection for collection in context.get("collections", []) if collection["path"][0] == key]
                field_order = PROFILE_FIELD_ORDER.get(key or "", [])
                for collection in section_collections:
                    collection["fields"].sort(key=lambda field: field_order.index(json.loads(field["name"])[-1]) if json.loads(field["name"])[-1] in field_order else len(field_order))
                if groups or section_collections:
                    sections.append({"key": key, "title": label, "groups": groups, "collections": section_collections})
            context["profile_sections"] = sections
        context.setdefault("last_build", request.app.state.builds.last_successful(mode="preview"))
        context["preview_url"] = (context.get("last_build") or {}).get("preview_url") or "http://127.0.0.1:4300"
        return templates.TemplateResponse(request=request, name=template, context=context, status_code=status)

    def detail_context(request: Request, artifact_id: str, values: dict[str, Any] | None = None, revision: str | None = None, error: Any = None) -> dict[str, Any]:
        try:
            result = request.app.state.content.inspect(artifact_id)
        except ServiceError:
            if values is None:
                raise
            # A concurrently malformed saved file cannot erase the submitted form.
            result = {"artifact": values, "revision": revision, "eligible": False}
        artifact = copy.deepcopy(values if values is not None else result["artifact"])
        artifact.setdefault("internal_notes", "")
        kind = artifact.get("kind", "")
        if values is None:
            if kind == "chapter" and result.get("chapter_plan") is not None:
                artifact["plan"] = {key: value for key, value in result["chapter_plan"].items() if key not in {"chapter_id", "section"}}
            if kind == "portfolio":
                artifact["detail"] = {key: value for key, value in result["detail"].items() if key != "id"}
                if not artifact["detail"].get("abstract"):
                    artifact["detail"]["abstract"] = artifact.get("description") or ""
                if not artifact["detail"].get("project_path"):
                    # Show the effective default instead of an empty box.
                    artifact["detail"]["project_path"] = f"projects/{artifact['id'].split('/')[-1]}"
            if kind == "course":
                artifact["contract"] = copy.deepcopy(result["contract"])
        if kind in authoring.KINDS:
            artifact = authoring.ensure_shape(kind, artifact)
        source = result.get("source_path")
        # Canonical path comes only from shared inspection; never from form input.
        editor_url = result.get("editor_url")
        lifecycle_options = None
        if result.get("has_authored_content") is not None:
            lifecycle_options = ["draft", "published"] if result["has_authored_content"] else ["planned", "draft"] if result.get("has_source") else ["planned"]
        context: dict[str, Any] = {"artifact": artifact, "record": result, "revision": revision or result["revision"], "error": error, "source_path": str(root / source) if source else None, "editor_url": editor_url, "section": "courses" if kind in {"course", "chapter"} else "posts" if kind == "post" else "portfolio" if kind == "portfolio" else "personal"}
        if kind in authoring.KINDS:
            courses = None
            if kind == "chapter" and artifact.get("parent"):
                try:
                    parent = request.app.state.content.inspect(artifact["parent"])
                    courses = [{"id": parent["artifact"]["id"], "title": parent["artifact"]["title"], "sections": parent["contract"]["toc"]}]
                except ServiceError:
                    courses = []
            context["sections"] = authoring.sections(kind, artifact, courses=courses, lifecycle_options=lifecycle_options or [artifact.get("lifecycle", "planned")])
            context["fields"] = []
            if task_id := request.query_params.get("summary_task"):
                board = request.app.state.kanban.read()
                context["summary_task_result"] = next((card for card in board["cards"] if card["id"] == task_id and artifact["id"] in card["artifact_ids"]), None)
        else:
            fields = form_fields(artifact)
            if lifecycle_options is not None:
                for field in fields:
                    if field["label"] == "lifecycle":
                        field["options"] = lifecycle_options
            context["fields"] = fields
        return context

    @router.get("/lookup")
    def lookup(request: Request, q: str = "", kind: str = "", parent: str = "") -> JSONResponse:
        listing = request.app.state.content.list()
        query = q.strip().casefold()
        matches = [a for a in listing["artifacts"] if (not kind or a["kind"] == kind) and (not parent or a.get("parent") == parent) and (not query or query in a["id"].casefold() or query in a["title"].casefold())]
        def rank(artifact: dict[str, Any]) -> tuple[int, str, str]:
            identifier, title = artifact["id"].casefold(), artifact["title"].casefold()
            return (0 if identifier == query else 1 if identifier.startswith(query) or title.startswith(query) else 2, title, identifier)
        return JSONResponse({"artifacts": sorted(matches, key=rank)[:30], "revision": listing["revision"]})

    def course_context(request: Request, slug: str, error: Any = None, submitted: dict[str, str] | None = None) -> dict[str, Any]:
        context = detail_context(request, "course/" + slug)
        context.update(error=error, submitted=submitted or {}, slug=slug)
        if submitted:
            context["revision"] = submitted.get("revision", context["revision"])
        return context

    @router.get("/courses/{slug}")
    def course_workspace(request: Request, slug: str) -> HTMLResponse:
        return render(request, "course.html", course_context(request, slug))

    @router.post("/courses/{slug}/outline")
    async def organize_course(request: Request, slug: str) -> Response:
        form = await request.form()
        values = {key: str(value) for key, value in form.items()}
        try:
            request.app.state.content.organize_course("course/" + slug, values.get("action", ""), values, form_revision(values.get("revision")))
        except ServiceError as error:
            return render(request, "course.html", course_context(request, slug, error.as_dict(), values), error.status)
        return RedirectResponse("/cms/courses/" + quote(slug) + "#outline", status_code=303)

    @router.get("/")
    def home() -> RedirectResponse:
        return RedirectResponse("/cms/home")

    def creation_courses(request: Request) -> list[dict[str, Any]]:
        courses = []
        for course in request.app.state.content.list("course")["artifacts"]:
            record = request.app.state.content.inspect(course["id"])
            courses.append({"id": course["id"], "title": course["title"], "sections": record["contract"].get("toc", [])})
        # A chapter started from a course page can only be placed in that course.
        if request.query_params.get("parent"):
            courses = [course for course in courses if course["id"] == request.query_params["parent"]]
        return courses

    def creation_context(request: Request, kind: str, values: dict[str, Any], revision: str | None, error: Any = None) -> dict[str, Any]:
        listing = request.app.state.content.list()
        courses = creation_courses(request) if kind == "chapter" else []
        return {"section": CREATE_SECTIONS.get(kind, "posts"), "kind": kind, "values": values, "revision": revision or listing["revision"], "courses": courses, "error": error, "sections": authoring.sections(kind, values, creating=True, courses=courses), "contextual": bool(request.query_params.get("parent"))}

    @router.get("/new")
    def new(request: Request, kind: str = "post") -> HTMLResponse:
        if kind not in CREATE_SECTIONS:
            return HTMLResponse("Unknown entry kind", status_code=404)
        listing = request.app.state.content.list()
        values = authoring.ensure_shape(kind, {"kind": kind, "parent": request.query_params.get("parent", ""), "section": request.query_params.get("section", "")})
        return render(request, "new.html", creation_context(request, kind, values, listing["revision"]))

    @router.post("/new")
    async def create(request: Request, kind: str | None = None) -> Response:
        form = await request.form()
        selected_kind = kind or str(form.get("kind", "post"))
        if selected_kind not in CREATE_SECTIONS:
            return HTMLResponse("Unknown entry kind", status_code=404)
        values = authoring.ensure_shape(selected_kind, {"kind": selected_kind})
        slug = ""
        try:
            if form.get("route"):
                raise ServiceError("Route is managed by the site and cannot be set in the CMS.")
            values = apply_fields(values, form)
            slug = creation_slug(str(values.get("name") or "").strip() or str(values.get("title") or ""))
            token = form_revision(form.get("revision"))
            title = str(values.get("title", "")).strip()
            data: dict[str, Any] = {"kind": selected_kind, "title": title, "tags": authoring.tags_from(values.get("tags")), "relations": list(dict.fromkeys(str(item) for item in values.get("relations") or [] if str(item).strip())), "visibility": "private", "lifecycle": "planned"}
            if selected_kind in planning.PLAN:
                data.update(planning.plan_patch(selected_kind, authoring.creation_plan(selected_kind, values)))
            if selected_kind == "post":
                data["id"] = f"post/{slug}"
                data["path"] = f"content/notebooks/posts/{slug}.ipynb"
            elif selected_kind == "course":
                data["id"] = f"course/{slug}"
                data["path"] = f"content/notebooks/courses/{slug}"
            elif selected_kind == "chapter":
                parent = str(values.get("parent", ""))
                if not parent.startswith("course/") or len(parent.split("/")) != 2:
                    raise ServiceError("Choose the parent course.")
                if request.query_params.get("parent") and parent != request.query_params["parent"]:
                    raise ServiceError("The chapter must belong to the course where creation began.")
                course_slug = parent.split("/", 1)[1]
                data.update(id=f"{parent}/{slug}", path=f"content/notebooks/courses/{course_slug}/{slug}.ipynb", parent=parent, section=str(values.get("section", "")), toc_title=str(values.get("toc_title") or "").strip() or title or slug)
            elif selected_kind == "portfolio":
                data["id"] = f"portfolio/{slug}"
                data["detail"] = {"notebook_path": f"content/notebooks/portfolio/{slug}.ipynb", **data.get("detail", {}), "abstract": (data.get("detail", {}).get("abstract") or "").strip() or None, "project_path": str(values.get("detail", {}).get("project_path") or "") or None}
            elif selected_kind == "project":
                data["id"] = f"project/{slug}"
                data["path"] = f"projects/{slug}"
            elif selected_kind == "personal":
                data["id"] = f"personal/{slug}"
                data["path"] = f"content/notebooks/personal/{slug}.ipynb"
            if selected_kind == "post":
                result = request.app.state.content.create_post(slug, data, token, attachment_uploads=await read_uploads(form))
            else:
                result = request.app.state.content.create(data, expected_revision=token, attachment_uploads=await read_uploads(form))
        except ServiceError as error:
            return render(request, "new.html", creation_context(request, selected_kind, values, str(form.get("revision") or ""), error.as_dict()), error.status)
        except (ValueError, KeyError, TypeError) as error:
            return render(request, "new.html", creation_context(request, selected_kind, values, str(form.get("revision") or ""), str(error)), 422)
        artifact_id = result["artifact"]["id"]
        notice = ""
        if form.get("start_draft") and selected_kind in {"post", "portfolio", "course", "chapter"}:
            try:
                request.app.state.content.start(artifact_id, expected_revision=result["revision"])
            except ServiceError:
                # The plan is saved; the author retries Start draft from its page.
                notice = "?notice=start-failed"
        target = "/cms/artifact/" + quote(artifact_id, safe="/")
        if selected_kind == "course":
            target = "/cms/courses/" + slug
        elif selected_kind == "chapter":
            target = "/cms/courses/" + data["parent"].split("/")[-1] + "#outline"
        target += notice if selected_kind != "chapter" else ""
        if request.headers.get("HX-Request"):
            return HTMLResponse("", headers={"HX-Redirect": target})
        return RedirectResponse(target, status_code=303)

    @router.get("/artifact/{artifact_id:path}")
    def detail(request: Request, artifact_id: str) -> HTMLResponse:
        if artifact_id.startswith("course/") and len(artifact_id.split("/")) == 2:
            return render(request, "course.html", course_context(request, artifact_id.split("/")[-1]))
        return render(request, "artifact.html", detail_context(request, artifact_id))

    def deletion_context(request: Request, artifact_id: str, error: Any = None, submitted: dict[str, str] | None = None) -> dict[str, Any]:
        plan = request.app.state.content.deletion_plan(artifact_id)
        artifact = plan["artifact"]
        section = "courses" if artifact["kind"] in {"course", "chapter"} else "portfolio" if artifact["kind"] == "portfolio" else "posts" if artifact["kind"] == "post" else "personal"
        return {"title": "Delete " + artifact["title"], "section": section, "plan": plan, "error": error, "submitted": submitted, "return_url": "/cms/courses/" + artifact["parent"].split("/")[-1] + "#outline" if artifact["kind"] == "chapter" else "/cms/" + section}

    @router.get("/delete/{artifact_id:path}")
    def review_delete(request: Request, artifact_id: str) -> HTMLResponse:
        return render(request, "delete.html", deletion_context(request, artifact_id))

    @router.post("/delete/{artifact_id:path}")
    async def delete(request: Request, artifact_id: str) -> Response:
        form = await request.form()
        submitted = {key: str(form.get(key, "")) for key in ["revision", "confirm", "confirmation_id", "cascade"]}
        try:
            if submitted["confirm"] != artifact_id:
                raise ServiceError("Confirm the stable ID of the entry you want to delete.")
            context = deletion_context(request, artifact_id)
            if submitted["confirmation_id"] != artifact_id:
                raise ServiceError("Type the stable ID exactly as shown to confirm deletion.")
            request.app.state.content.delete(artifact_id, form_revision(submitted["revision"]), cascade=submitted["cascade"] == "yes")
        except ServiceError as error:
            # A stale review keeps its original revision and requires an explicit reload.
            try:
                context = deletion_context(request, artifact_id, error.as_dict(), submitted)
            except ServiceError:
                return HTMLResponse("This entry is no longer available. Reload its section.", status_code=error.status)
            return render(request, "delete.html", context, error.status)
        if context["plan"]["artifact"]["kind"] == "chapter":
            return RedirectResponse(context["return_url"], status_code=303)
        return RedirectResponse("/cms/" + context["section"] + "?deleted=1", status_code=303)

    @router.post("/save/{artifact_id:path}")
    async def save(request: Request, artifact_id: str) -> Response:
        form = await request.form()
        # The browser carries a read snapshot so conflicts preserve *all* submitted values.
        baseline = form_baseline(form.get("snapshot", "{}"))
        values = baseline
        revision = str(form.get("revision", ""))
        upload = form.get("featured_image")
        uploading = isinstance(upload, UploadFile) and bool(upload.filename)
        try:
            values = apply_fields(baseline, form)
            patch = {key: value for key, value in values.items() if baseline.get(key) != value}
            if values.get("kind") == "portfolio":
                saved_detail = request.app.state.content.inspect(artifact_id)["detail"]
                if not saved_detail.get("abstract") and values.get("detail", {}).get("abstract"):
                    patch["detail"] = {**patch.get("detail", {}), "abstract": values["detail"]["abstract"]}
            if "route" in patch:
                raise ServiceError("Route is managed by the site and cannot be edited in the CMS.")
            if "cover" in patch and request.app.state.content.inspect(artifact_id)["artifact"]["kind"] != "course":
                raise ServiceError("Only course card images can be changed here.")
            if form.get("save_action") == "publish":
                saved_artifact = request.app.state.content.inspect(artifact_id)["artifact"]
                if saved_artifact["kind"] not in {"post", "portfolio", "course", "chapter"} or saved_artifact["lifecycle"] != "draft":
                    raise ServiceError("Save and publish is available for draft posts, portfolio entries, courses and chapters only.")
            image = None
            if isinstance(upload, UploadFile) and uploading:
                try:
                    image = await upload.read(MAX_FIGURE_BYTES + 1)
                finally:
                    await upload.close()
            if form.get("save_action") == "publish":
                request.app.state.content.publish(artifact_id, expected_revision=form_revision(revision), patch=patch, figure_image=image, attachment_uploads=await read_uploads(form), remove_attachments=[str(item) for item in form.getlist("remove_attachments")])
            else:
                request.app.state.content.update(artifact_id, patch, expected_revision=form_revision(revision), figure_image=image, attachment_uploads=await read_uploads(form), remove_attachments=[str(item) for item in form.getlist("remove_attachments")])
        except ServiceError as error:
            context = detail_context(request, artifact_id, values, revision, error.as_dict())
            context["form_snapshot"] = baseline
            context["upload_retry"] = uploading
            context["remove_attachments"] = [str(item) for item in form.getlist("remove_attachments")]
            return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context, error.status)
        except (ValueError, KeyError, TypeError) as error:
            context = detail_context(request, artifact_id, values, revision, str(error))
            context["form_snapshot"] = baseline
            context["remove_attachments"] = [str(item) for item in form.getlist("remove_attachments")]
            return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context, 422)
        context = detail_context(request, artifact_id)
        if context["artifact"]["kind"] in {"course", "chapter"}:
            artifact = context["artifact"]
            slug = (artifact["id"] if artifact["kind"] == "course" else artifact["parent"]).split("/")[-1]
            target = "/cms/courses/" + slug + ("#outline" if artifact["kind"] == "chapter" else "#course-brief")
            if request.headers.get("HX-Request"):
                return HTMLResponse("", headers={"HX-Redirect": target})
            return RedirectResponse(target, status_code=303)
        if context["artifact"]["kind"] == "portfolio":
            target = "/cms/portfolio?saved=portfolio"
            if request.headers.get("HX-Request"):
                return HTMLResponse("", headers={"HX-Redirect": target})
            return RedirectResponse(target, status_code=303)
        context["saved"] = True
        return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context)

    @router.post("/action/{action}/{artifact_id:path}")
    async def action(request: Request, action: str, artifact_id: str) -> HTMLResponse:
        form = await request.form()
        revision = str(form.get("revision", ""))
        if action not in {"start", "publish", "draft"}:
            return HTMLResponse("Unknown action", status_code=404)
        try:
            result = getattr(request.app.state.content, action)(artifact_id, expected_revision=form_revision(revision))
        except ServiceError as error:
            return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", detail_context(request, artifact_id, revision=revision, error=error.as_dict()), error.status)
        context = detail_context(request, artifact_id)
        context["action_result"] = result
        if context["artifact"]["kind"] == "course" and not request.headers.get("HX-Request"):
            context.update(slug=artifact_id.split("/")[-1], submitted={})
            return render(request, "course.html", context)
        return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context)

    @router.post("/summary-task/{artifact_id:path}")
    async def create_summary_task(request: Request, artifact_id: str) -> Response:
        form = await request.form()
        revision = str(form.get("revision", ""))
        try:
            token = form_revision(revision).strip('"')
            plan = request.app.state.content.read_plan(artifact_id)
            if plan["kind"] not in authoring.KINDS:
                raise ServiceError("Summary tasks are available for posts, courses, chapters and portfolio entries.")
            board = request.app.state.kanban.read()
            if token != plan["revision"] or token != board["revision"]:
                raise ServiceError("The saved context changed. Reload the editor before adding a summary task.", code="conflict", status=412)
            payload = authoring.summary_task(plan)
            marker = payload["description"].splitlines()[0]
            card = next((card for card in board["cards"] if card["column"] != "done" and artifact_id in card["artifact_ids"] and card["description"].splitlines()[:1] == [marker]), None)
            if card is None:
                card = request.app.state.kanban.create(payload, token)["card"]
        except ServiceError as error:
            context = detail_context(request, artifact_id, revision=revision)
            context["summary_task_error"] = error.as_dict()
            if context["artifact"]["kind"] == "course" and not request.headers.get("HX-Request"):
                context.update(slug=artifact_id.split("/")[-1], submitted={})
                return render(request, "course.html", context, error.status)
            return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context, error.status)
        target = ("/cms/courses/" + quote(artifact_id.split("/")[-1]) if plan["kind"] == "course" else "/cms/artifact/" + quote(artifact_id, safe="/"))
        target += "?summary_task=" + quote(card["id"]) + ("#course-brief" if plan["kind"] == "course" else "#page")
        if request.headers.get("HX-Request"):
            return HTMLResponse("", headers={"HX-Redirect": target})
        return RedirectResponse(target, status_code=303)

    def profile_edit_context(values: dict[str, Any], revision: str, view: str = "resume", error: Any = None) -> dict[str, Any]:
        view = view if view in {"home", "resume"} else "resume"
        return {"title": dict(NAVIGATION)[view], "section": view, "name": "profile", "data": values, "revision": revision, "fields": form_fields(values), "collections": collections(values), "profile_view": view, "error": error}

    @router.get("/data/{name:path}")
    def data(request: Request, name: str) -> Response:
        if name == "photos" and request.query_params.get("add") == "photo":
            return RedirectResponse("/cms/photos/new", status_code=303)
        result = request.app.state.content.read_data(name)
        if name == "profile":
            return render(request, "profile.html", profile_edit_context(result["data"], result["revision"], request.query_params.get("view", "resume")))
        values = photo_editor_data(result["data"]) if name == "photos" else result["data"]
        return render(request, "data.html", {"section": "resume" if name == "profile" else "courses" if name.startswith("course/") else "personal" if name == "photos" else "portfolio", "name": name, "data": values, "revision": result["revision"], "fields": form_fields(values), "collections": collections(values)})

    @router.post("/data/{name:path}")
    async def save_data(request: Request, name: str) -> Response:
        form = await request.form()
        baseline = form_baseline(form.get("snapshot", "{}"))
        values = baseline
        revision = str(form.get("revision", ""))
        error: Any = None
        status = 200
        uploading = any(isinstance(value, UploadFile) and bool(value.filename) for value in form.values())
        try:
            values = apply_fields(baseline, form)
            if name == "photos":
                images = await photo_uploads(form, len(baseline.get("photos", [])))
                result = request.app.state.content.update_gallery(values, expected_revision=form_revision(revision), photo_images=images)
                values = photo_editor_data(result["data"]["photos"])
            else:
                result = request.app.state.content.update_data(name, values, expected_revision=form_revision(revision))
            revision = result["revision"]
        except ServiceError as exc:
            error, status = exc.as_dict(), exc.status
        except (ValueError, KeyError, TypeError) as exc:
            error, status = str(exc), 422
        if name == "profile":
            view = str(form.get("profile_view", "resume"))
            view = view if view in {"home", "resume"} else "resume"
            if not error:
                target = f"/cms/{view}?saved=profile"
                if request.headers.get("HX-Request"):
                    return HTMLResponse("", headers={"HX-Redirect": target})
                return RedirectResponse(target, status_code=303)
            return render(request, "profile_fragment.html" if request.headers.get("HX-Request") else "profile.html", profile_edit_context(values, revision, view, error), status)
        if name == "photos" and request.query_params.get("reorder") == "1":
            try:
                page = max(1, int(str(form.get("page", "1"))))
                page_size = int(str(form.get("page_size", "10")))
            except (TypeError, ValueError):
                page, page_size = 1, 10
            if page_size not in {10, 25, 50}:
                page_size = 10
            if not error:
                return RedirectResponse(f"/cms/personal?reorder=1&page={page}&page_size={page_size}&saved=order", status_code=303)
            result = "conflict" if status == 412 else "failed"
            return RedirectResponse(f"/cms/personal?reorder=1&page={page}&page_size={page_size}&save_error={result}", status_code=303)
        return render(request, "data_fragment.html" if request.headers.get("HX-Request") else "data.html", {"section": "resume" if name == "profile" else "courses" if name.startswith("course/") else "personal" if name == "photos" else "portfolio", "name": name, "data": values, "fields": form_fields(values), "collections": collections(values), "revision": revision, "error": error, "upload_retry": uploading, "saved": not error}, status)

    @router.post("/refresh")
    def refresh(request: Request) -> HTMLResponse:
        try:
            record = request.app.state.builds.submit(mode="preview")
            return render(request, "build.html" if request.headers.get("HX-Request") else "build_page.html", {"build": record})
        except ServiceError as error:
            return render(request, "build.html", {"error": error.as_dict()}, error.status)

    @router.get("/build/{build_id}")
    def build_status(request: Request, build_id: str) -> HTMLResponse:
        record = request.app.state.builds.get(build_id)
        return render(request, "build.html", {"build": record})

    @router.get("/home/atlas.png", include_in_schema=False)
    def home_illustration() -> Response:
        path = (root / "backend/assets/atlas.png").resolve()
        if not path.is_relative_to(root / "backend/assets") or not path.is_file():
            return HTMLResponse("Illustration not found", status_code=404)
        return FileResponse(path, media_type="image/png")

    @router.get("/figure/{artifact_id:path}")
    def portfolio_figure(request: Request, artifact_id: str) -> Response:
        record = request.app.state.content.inspect(artifact_id)
        figure = record.get("detail", {}).get("figure_path") if record["artifact"]["kind"] == "portfolio" else record["artifact"].get("cover")
        if not figure:
            return HTMLResponse("No figure configured", status_code=404)
        path = (root / figure).resolve()
        if not any(path.is_relative_to(root / folder) for folder in ("content", "backend/assets")) or not path.is_file():
            return HTMLResponse("Figure is outside supported assets or missing", status_code=404)
        return FileResponse(path)

    def photo_add_context(photo: dict[str, str], revision: str, error: Any = None, uploading: bool = False) -> dict[str, Any]:
        return {"title": "Add photo", "section": "personal", "photo": photo, "revision": revision, "error": error, "upload_retry": uploading}

    @router.get("/photos/new")
    def new_photo(request: Request) -> HTMLResponse:
        result = request.app.state.content.read_data("photos")
        photo = {"heading": "", "path": "", "caption": "", "lifecycle": "draft", "width": ""}
        return render(request, "photo_add.html", photo_add_context(photo, result["revision"]))

    @router.post("/photos/new")
    async def add_photo(request: Request) -> Response:
        form = await request.form()
        photo = {key: str(form.get(key, "draft" if key == "lifecycle" else "")) for key in ("heading", "caption", "lifecycle", "width")}
        photo["path"] = ""
        token = str(form.get("revision", ""))
        upload = form.get("new_photo_image")
        uploading = isinstance(upload, UploadFile) and bool(upload.filename)
        try:
            revision = form_revision(token)
            result = request.app.state.content.read_data("photos")
            values = copy.deepcopy(result["data"])
            rows = values.setdefault("photos", [])
            index = len(rows)
            rows.append(photo)
            images = {}
            if isinstance(upload, UploadFile) and upload.filename:
                images[index] = await upload.read(MAX_FIGURE_BYTES + 1)
            request.app.state.content.update_gallery(values, expected_revision=revision, photo_images=images)
        except ServiceError as error:
            return render(request, "photo_add_fragment.html" if request.headers.get("HX-Request") else "photo_add.html", photo_add_context(photo, token, error.as_dict(), uploading), error.status)
        finally:
            if isinstance(upload, UploadFile):
                await upload.close()
        if request.headers.get("HX-Request"):
            return HTMLResponse("", headers={"HX-Redirect": "/cms/personal?saved=photo"})
        return RedirectResponse("/cms/personal?saved=photo", status_code=303)

    def photo_context(index: int, data: dict[str, Any], revision: str, error: Any = None, uploading: bool = False) -> dict[str, Any]:
        values = photo_editor_data(data)
        if not 0 <= index < len(values.get("photos", [])):
            raise ServiceError("Unknown photo", code="not_found", status=404)
        fields = [field for field in form_fields(values) if tuple(json.loads(field["name"]))[:2] == ("photos", str(index))]
        return {"title": "Edit photo", "section": "personal", "index": index, "photo": values["photos"][index], "data": values, "fields": fields, "revision": revision, "error": error, "upload_retry": uploading}

    @router.get("/photos/{index}/edit")
    def edit_photo(request: Request, index: int) -> HTMLResponse:
        result = request.app.state.content.read_data("photos")
        return render(request, "photo.html", photo_context(index, result["data"], result["revision"]))

    @router.get("/photos/{index}/delete")
    def review_photo_delete(request: Request, index: int) -> HTMLResponse:
        result = request.app.state.content.read_data("photos")
        context = photo_context(index, result["data"], result["revision"])
        context["title"] = "Delete photo"
        return render(request, "photo_delete.html", context)

    @router.post("/photos/{index}/delete")
    async def delete_photo(request: Request, index: int) -> Response:
        form = await request.form()
        token = str(form.get("revision", ""))
        result = request.app.state.content.read_data("photos")
        rows = result["data"].get("photos", [])
        photo = rows[index] if 0 <= index < len(rows) else None
        try:
            revision = form_revision(token)
            if revision != result["revision"]:
                raise ServiceError("Photos changed since this deletion review. Reload before deleting.", code="conflict", status=412)
            if photo is None:
                raise ServiceError("Unknown photo", code="not_found", status=404)
            if form.get("confirm") != "yes":
                raise ServiceError("Confirm the photo you want to delete.")
            values = copy.deepcopy(result["data"])
            values["photos"].pop(index)
            request.app.state.content.update_gallery(values, expected_revision=revision)
        except ServiceError as error:
            return render(request, "photo_delete.html", {"title": "Delete photo", "section": "personal", "index": index, "photo": photo, "revision": token, "error": error.as_dict()}, error.status)
        return RedirectResponse("/cms/personal?deleted=1", status_code=303)

    @router.post("/photos/{index}/edit")
    async def save_photo(request: Request, index: int) -> Response:
        form = await request.form()
        baseline = form_baseline(form.get("snapshot", "{}"))
        values = copy.deepcopy(baseline)
        token = str(form.get("revision", ""))
        uploading = any(isinstance(value, UploadFile) and bool(value.filename) for value in form.values())
        try:
            if not 0 <= index < len(baseline.get("photos", [])):
                raise ServiceError("Unknown photo", code="not_found", status=404)
            if form.get("collection_action"):
                raise ServiceError("Use the gallery editor to reorder or remove photos.")
            candidate = apply_fields(baseline, form)
            values["photos"][index] = candidate["photos"][index]
            images = await photo_uploads(form, len(baseline["photos"]))
            selected_images = {index: images[index]} if index in images else {}
            request.app.state.content.update_gallery(values, expected_revision=form_revision(token), photo_images=selected_images)
        except ServiceError as error:
            return render(request, "photo_fragment.html" if request.headers.get("HX-Request") else "photo.html", photo_context(index, values, token, error.as_dict(), uploading), error.status)
        except (ValueError, KeyError, TypeError) as error:
            return render(request, "photo_fragment.html" if request.headers.get("HX-Request") else "photo.html", photo_context(index, values, token, str(error), uploading), 422)
        if request.headers.get("HX-Request"):
            return HTMLResponse("", headers={"HX-Redirect": "/cms/personal?saved=photo"})
        return RedirectResponse("/cms/personal?saved=photo", status_code=303)

    @router.get("/photo/{index}")
    def gallery_photo(request: Request, index: int) -> Response:
        photos = request.app.state.content.read_data("photos")["data"].get("photos", [])
        if not 0 <= index < len(photos):
            return HTMLResponse("Unknown photo", status_code=404)
        source = photos[index].get("path")
        if not source:
            return HTMLResponse("No Photo", status_code=404)
        path = (root / source).resolve()
        if not any(path.is_relative_to(root / folder) for folder in ("content", "backend/assets")) or not path.is_file():
            return HTMLResponse("Photo is outside supported assets or missing", status_code=404)
        return FileResponse(path)

    def kanban_context(request: Request, query: str = "", error: Any = None, submitted: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            board = request.app.state.kanban.read(query=query)
        except ServiceError as exc:
            board = {"cards": [], "columns": [{"id": key, "title": title} for key, title in KANBAN_COLUMNS], "revision": (submitted or {}).get("revision", "")}
            error = error or exc.as_dict()
        try:
            artifacts = request.app.state.content.list()["artifacts"]
        except ServiceError:
            artifacts = []
        return {"title": "Kanban", "section": "kanban", "board": board, "q": query, "error": error, "submitted": submitted, "all_artifacts": artifacts}

    @router.get("/kanban")
    def kanban_page(request: Request, q: str = "", edit: str | None = None, remove: str | None = None, add: bool = False, link: str = "") -> HTMLResponse:
        context = kanban_context(request, "" if edit or remove else q)
        # A next step started from an entry opens prefilled with its stable ID.
        context["prefill"] = {"artifact_ids": [link]} if link and add else None
        target = edit or remove
        if target and not any(card["id"] == target for card in context["board"]["cards"]):
            return HTMLResponse("Unknown card", status_code=404)
        context["active_dialog"] = "edit-" + edit if edit else "remove-" + remove if remove else "new-card" if add else None
        return render(request, "kanban.html", context)

    @router.post("/kanban/{action}")
    async def kanban_save(request: Request, action: str) -> Response:
        form = await request.form()
        values: dict[str, Any] = {key: str(form.get(key, "")) for key in ["revision", "card_id", "title", "description", "column", "artifact_ids"]}
        if form.get("relationship:artifact_ids"):
            values["artifact_ids"] = "\n".join(dict.fromkeys(str(value) for value in form.getlist("artifact_ids") if value))
        values["action"] = action
        values["remove_attachments"] = [str(item) for item in form.getlist("remove_attachments")]
        if action == "update":
            try:
                values["attachments"] = json.loads(str(form.get("attachment_snapshot") or "[]"))
                if not isinstance(values["attachments"], list):
                    raise ValueError("Expected attachment list")
            except ValueError:
                raise ServiceError("Invalid card attachment snapshot. Reload the card.") from None
        payload = {"title": values["title"], "description": values["description"], "column": values["column"], "artifact_ids": [line.strip() for line in values["artifact_ids"].splitlines() if line.strip()]}
        try:
            token = form_revision(values["revision"])
            if action == "create":
                request.app.state.kanban.create(payload, token, attachment_uploads=await read_uploads(form))
            elif action == "update":
                request.app.state.kanban.update(values["card_id"], payload, token, attachment_uploads=await read_uploads(form), remove_attachments=[str(item) for item in form.getlist("remove_attachments")])
            elif action == "move":
                request.app.state.kanban.update(values["card_id"], {"column": values["column"]}, token)
            elif action == "remove":
                request.app.state.kanban.remove(values["card_id"], token)
            else:
                return HTMLResponse("Unknown Kanban action", status_code=404)
        except ServiceError as exc:
            return render(request, "kanban.html", kanban_context(request, error=exc.as_dict(), submitted=values), exc.status)
        if request.headers.get("HX-Request"):
            return Response(status_code=200, headers={"HX-Redirect": "/cms/kanban"})
        return RedirectResponse("/cms/kanban", status_code=303)

    @router.get("/{section}")
    def section(request: Request, section: str, tag: str | None = None, lifecycle: str | None = None, visibility: str | None = None, q: str = "", page: int = 1, page_size: int = 10, edit: str | None = None, reorder: bool = False) -> HTMLResponse:
        if section not in dict(NAVIGATION):
            return HTMLResponse("Unknown author section", status_code=404)
        if section in {"home", "resume"} and edit == "profile":
            result = request.app.state.content.read_data("profile")
            return render(request, "profile.html", profile_edit_context(result["data"], result["revision"], section))
        listing = request.app.state.content.list()
        all_items = listing["artifacts"]
        items = [item for item in all_items if item["kind"] == KINDS.get(section) or section == "personal" and item["kind"] == "gallery"]
        tags = sorted({tag for item in items for tag in item.get("tags", [])}, key=str.casefold)
        items = [item for item in items if (not tag or tag in item.get("tags", [])) and (not lifecycle or item["lifecycle"] == lifecycle) and (not visibility or item["visibility"] == visibility)]
        if q:
            search = " ".join(q.split()).casefold()
            items = [item for item in items if search in " ".join(item["title"].split()).casefold()]
        items, pagination = paginate(request, items, page, page_size)
        records = {item["id"]: request.app.state.content.inspect(item["id"]) for item in items} if section in {"courses", "portfolio"} else {}
        profile = request.app.state.content.read_data("profile")["data"] if section in {"home", "resume"} else None
        photo_data = request.app.state.content.read_data("photos") if section == "personal" else None
        photos = photo_data["data"].get("photos", []) if photo_data else None
        photo_rows = None
        if photos is not None:
            photo_rows, pagination = paginate(request, list(enumerate(photos)), page, page_size)
        return render(request, "section.html", {"section": section, "title": dict(NAVIGATION)[section], "artifacts": items, "all_artifacts": all_items, "records": records, "profile": profile, "profile_links": contact_links(profile["contact"]) if profile else [], "photo_rows": photo_rows, "photo_revision": photo_data["revision"] if photo_data else None, "photo_snapshot": photo_data["data"] if photo_data else None, "reorder": section == "personal" and reorder, "pagination": pagination, "tags": tags, "q": q, "tag": tag, "lifecycle": lifecycle, "visibility": visibility, "data_name": DATA_NAMES.get(section), "kind": KINDS.get(section) if section != "personal" else None, "last_build": request.app.state.builds.last_successful(mode="preview")})

    return router
