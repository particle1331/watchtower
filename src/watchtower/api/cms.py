"""Jinja forms provide a native fallback as well as HTMX fragment responses."""

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from watchtower.services.workspace import ServiceError

NAVIGATION = [("home", "Home"), ("resume", "Résumé"), ("portfolio", "Portfolio"), ("posts", "Posts"), ("courses", "Courses"), ("personal", "Personal")]
KINDS = {"posts": "post", "courses": "course", "portfolio": "portfolio", "personal": "personal"}
DATA_NAMES = {"home": "profile", "resume": "profile", "portfolio": "portfolio", "personal": "photos"}


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
            for key, value in {"heading": "", "path": "", "caption": "", "lifecycle": "draft"}.items():
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
        defaults = {"photos": {"heading": "", "path": "", "caption": "", "lifecycle": "draft"}, "toc": {"id": "", "title": "", "chapters": []}, "chapters": {"chapter_id": "", "section": "", "content": "", "lab_and_evidence": ""}, "entries": {"id": "", "project_source": "active", "planned": {}}, "projects": {"title": "", "bullets": []}, "employment": {"title": "", "company": "", "dates": "", "bullets": []}, "early_employment": {"title": "", "company": "", "dates": "", "bullets": []}, "education": {"institution": "", "degree": "", "dates": ""}, "skills": {"name": "", "entries": []}}
        prototype = blank_record(data[0]) if data else defaults.get(prefix[-1] if prefix else "", {})
        if prefix[-1] == "photos":
            prototype = {**defaults["photos"], **prototype, "lifecycle": "draft"}
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
        fields.append({"name": json.dumps(prefix), "label": " / ".join(prefix), "value": data if data is not None else "", "type": "photo_lifecycle" if prefix and prefix[-1] == "lifecycle" and "photos" in prefix else "bool" if isinstance(data, bool) else "int" if isinstance(data, int) else "float" if isinstance(data, float) else "text"})
    return fields


def apply_fields(data: dict[str, Any], form: Any) -> dict[str, Any]:
    result = copy.deepcopy(data)
    for name, value in form.multi_items():
        if not name.startswith("field:"):
            continue
        path = json.loads(name[6:])
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
            node[key] = [line.strip() for line in str(value).splitlines() if line.strip()]
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
                    path = json.loads(name[4:])
                    if path[:len(operation["path"])] == operation["path"]:
                        new_values.append(("field:" + json.dumps(["new", *path[len(operation["path"]):]]), value))
            from starlette.datastructures import FormData
            node.append(apply_fields(wrapper, FormData(new_values))["new"])
    return result


def cms_router(root: Path) -> APIRouter:
    router = APIRouter(prefix="/cms", include_in_schema=False)
    templates = Jinja2Templates(directory=str(root / "frontend/templates/cms"))
    templates.env.filters["urlpath"] = lambda value: quote(str(value), safe="/")

    def render(request: Request, template: str, context: dict[str, Any], status: int = 200) -> HTMLResponse:
        context.update({"navigation": NAVIGATION, "root": str(root)})
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
        if values is None:
            if artifact.get("kind") == "chapter" and result.get("chapter_plan") is not None:
                artifact["plan"] = {key: value for key, value in result["chapter_plan"].items() if key not in {"chapter_id", "section"}}
            if artifact.get("kind") == "portfolio":
                artifact["detail"] = {key: value for key, value in result["detail"].items() if key != "id"}
            if artifact.get("kind") in {"post", "personal"}:
                artifact.setdefault("planned", {}).setdefault("content", "")
        source = result.get("source_path")
        # Canonical path comes only from shared inspection; never from form input.
        editor_url = result.get("editor_url")
        return {"artifact": artifact, "record": result, "revision": revision or result["revision"], "error": error, "source_path": str(root / source) if source else None, "editor_url": editor_url, "fields": form_fields(artifact), "section": "courses" if artifact.get("kind") in {"course", "chapter"} else "posts" if artifact.get("kind") == "post" else "portfolio" if artifact.get("kind") == "portfolio" else "personal"}

    @router.get("/")
    def home() -> RedirectResponse:
        return RedirectResponse("/cms/home")

    @router.get("/new")
    def new(request: Request, kind: str = "post") -> HTMLResponse:
        listing = request.app.state.content.list()
        return render(request, "new.html", {"section": KINDS.get(kind, "posts"), "values": {"kind": kind, "visibility": "public"}, "revision": listing["revision"]})

    @router.post("/new")
    async def create(request: Request) -> Response:
        form = await request.form()
        values = dict(form)
        data: dict[str, Any] = {key: str(value) for key, value in form.items() if key not in {"revision", "tags", "relations"} and value != ""}
        data["tags"] = [tag.strip() for tag in str(form.get("tags", "")).split(",") if tag.strip()]
        data["relations"] = [item.strip() for item in str(form.get("relations", "")).split(",") if item.strip()]
        if data.get("kind") != "chapter":
            content = data.pop("planned_content", "")
            data.pop("planned_lab_and_evidence", None)
            data["planned"] = {"content": content}
        try:
            result = request.app.state.content.create(data, expected_revision=form_revision(form.get("revision")))
        except ServiceError as error:
            return render(request, "new.html", {"section": "posts", "values": values, "revision": form.get("revision"), "error": error.as_dict()}, error.status)
        target = "/cms/artifact/" + quote(result["artifact"]["id"], safe="/")
        if request.headers.get("HX-Request"):
            return HTMLResponse("", headers={"HX-Redirect": target})
        return RedirectResponse(target, status_code=303)

    @router.get("/artifact/{artifact_id:path}")
    def detail(request: Request, artifact_id: str) -> HTMLResponse:
        return render(request, "artifact.html", detail_context(request, artifact_id))

    @router.post("/save/{artifact_id:path}")
    async def save(request: Request, artifact_id: str) -> HTMLResponse:
        form = await request.form()
        # The browser carries a read snapshot so conflicts preserve *all* submitted values.
        baseline = form_baseline(form.get("snapshot", "{}"))
        values = baseline
        revision = str(form.get("revision", ""))
        try:
            values = apply_fields(baseline, form)
            patch = {key: value for key, value in values.items() if baseline.get(key) != value}
            request.app.state.content.update(artifact_id, patch, expected_revision=form_revision(revision))
        except ServiceError as error:
            context = detail_context(request, artifact_id, values, revision, error.as_dict())
            return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context, error.status)
        except (ValueError, KeyError, TypeError) as error:
            context = detail_context(request, artifact_id, values, revision, str(error))
            return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context, 422)
        context = detail_context(request, artifact_id)
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
        return render(request, "artifact_fragment.html" if request.headers.get("HX-Request") else "artifact.html", context)

    @router.get("/data/{name:path}")
    def data(request: Request, name: str) -> HTMLResponse:
        result = request.app.state.content.read_data(name)
        values = photo_editor_data(result["data"]) if name == "photos" else result["data"]
        return render(request, "data.html", {"section": "resume" if name == "profile" else "courses" if name.startswith("course/") else "personal" if name == "photos" else "portfolio", "name": name, "data": values, "revision": result["revision"], "fields": form_fields(values), "collections": collections(values)})

    @router.post("/data/{name:path}")
    async def save_data(request: Request, name: str) -> HTMLResponse:
        form = await request.form()
        baseline = form_baseline(form.get("snapshot", "{}"))
        values = baseline
        revision = str(form.get("revision", ""))
        error: Any = None
        status = 200
        try:
            values = apply_fields(baseline, form)
            if name == "photos":
                result = request.app.state.content.update_gallery(values, expected_revision=form_revision(revision))
            else:
                result = request.app.state.content.update_data(name, values, expected_revision=form_revision(revision))
            revision = result["revision"]
        except ServiceError as exc:
            error, status = exc.as_dict(), exc.status
        except (ValueError, KeyError, TypeError) as exc:
            error, status = str(exc), 422
        return render(request, "data_fragment.html" if request.headers.get("HX-Request") else "data.html", {"section": "resume" if name == "profile" else "courses" if name.startswith("course/") else "personal" if name == "photos" else "portfolio", "name": name, "data": values, "fields": form_fields(values), "collections": collections(values), "revision": revision, "error": error, "saved": not error}, status)

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

    @router.get("/figure/{artifact_id:path}")
    def portfolio_figure(request: Request, artifact_id: str) -> Response:
        record = request.app.state.content.inspect(artifact_id)
        figure = record.get("detail", {}).get("figure_path")
        if not figure:
            return HTMLResponse("No figure configured", status_code=404)
        path = (root / figure).resolve()
        if not path.is_relative_to(root / "content") or not path.is_file():
            return HTMLResponse("Figure is outside authored content or missing", status_code=404)
        return FileResponse(path)

    @router.get("/photo/{index}")
    def gallery_photo(request: Request, index: int) -> Response:
        photos = request.app.state.content.read_data("photos")["data"].get("photos", [])
        if not 0 <= index < len(photos):
            return HTMLResponse("Unknown photo", status_code=404)
        path = (root / photos[index]["path"]).resolve()
        if not path.is_relative_to(root / "content") or not path.is_file():
            return HTMLResponse("Photo is outside authored content or missing", status_code=404)
        return FileResponse(path)

    @router.get("/{section}")
    def section(request: Request, section: str, tag: str | None = None, lifecycle: str | None = None, visibility: str | None = None) -> HTMLResponse:
        if section not in dict(NAVIGATION):
            return HTMLResponse("Unknown author section", status_code=404)
        listing = request.app.state.content.list()
        all_items = listing["artifacts"]
        items = [item for item in all_items if item["kind"] == KINDS.get(section) or section == "personal" and item["kind"] == "gallery"]
        tags = sorted({tag for item in items for tag in item.get("tags", [])}, key=str.casefold)
        items = [item for item in items if (not tag or tag in item.get("tags", [])) and (not lifecycle or item["lifecycle"] == lifecycle) and (not visibility or item["visibility"] == visibility)]
        records = {item["id"]: request.app.state.content.inspect(item["id"]) for item in items} if section in {"courses", "portfolio"} else {}
        profile = request.app.state.content.read_data("profile")["data"] if section in {"home", "resume"} else None
        photos = request.app.state.content.read_data("photos")["data"].get("photos", []) if section == "personal" else None
        return render(request, "section.html", {"section": section, "title": dict(NAVIGATION)[section], "artifacts": items, "all_artifacts": all_items, "records": records, "profile": profile, "photos": photos, "tags": tags, "tag": tag, "lifecycle": lifecycle, "visibility": visibility, "data_name": DATA_NAMES.get(section), "kind": KINDS.get(section) if section != "personal" else None, "last_build": request.app.state.builds.last_successful(mode="preview")})

    return router
