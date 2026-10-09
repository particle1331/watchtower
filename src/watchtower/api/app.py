"""Thin HTTP adapters: all saved-input operations belong to shared services."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from watchtower.api.attachments import read_uploads
from watchtower.api.schemas import (
    ArtifactCreate,
    ArtifactList,
    ArtifactPatch,
    ArtifactResult,
    BatchUpdate,
    BuildRequest,
    DataResult,
    GalleryState,
    GalleryUpdate,
    KanbanCreate,
    KanbanPatch,
    Kind,
    ServiceResult,
    StructuredUpdate,
)
from watchtower.services.attachments import INLINE_IMAGES, AttachmentService
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError


def require_revision(if_match: str | None) -> str:
    """Accept one opaque ETag; wildcard and weak comparisons are unsafe for writes."""
    if not if_match:
        raise HTTPException(428, detail={"code": "precondition_required", "message": "Load the record and send its ETag in If-Match."})
    value = if_match.strip()
    if value == "*" or value.startswith("W/") or "," in value:
        raise HTTPException(400, detail={"code": "invalid_revision", "message": "If-Match must contain one strong revision."})
    return value.strip('"')


def set_etag(response: Response, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("revision"):
        response.headers["ETag"] = f'"{result["revision"]}"'
    return result


def create_app(root: Path | None = None) -> FastAPI:
    root = (root or Path.cwd()).resolve()
    content = ContentService(root)
    builds = BuildService(root)
    kanban = KanbanService(root)
    attachments = AttachmentService(root)
    app = FastAPI(title="Watchtower author API", version="1.0.0")
    app.state.root = root
    app.state.content = content
    app.state.builds = builds
    app.state.kanban = kanban
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_origin(request: Request, call_next: Any) -> Response:
        # A remote webpage must not be able to submit forms to the local author server.
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin != expected:
                return JSONResponse({"error": {"code": "foreign_origin", "message": "Use the local author interface."}}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceError)
    async def domain_error(request: Request, error: ServiceError) -> JSONResponse:
        return JSONResponse({"error": error.as_dict()}, status_code=error.status)

    @app.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse("/cms/")

    @app.get("/api/artifacts", response_model=ArtifactList)
    def artifacts(response: Response, kind: Kind | None = None) -> dict[str, Any]:
        return set_etag(response, content.list(kind=kind))

    @app.post("/api/artifacts", response_model=ArtifactResult, status_code=201)
    def create(data: ArtifactCreate, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, content.create(data.model_dump(exclude_none=True), expected_revision=require_revision(if_match)))

    # Action routes precede the path converter used for slash-containing stable IDs.
    @app.post("/api/actions/{action}/{artifact_id:path}", response_model=ServiceResult)
    def action(action: str, artifact_id: str, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        if action not in {"start", "publish", "draft"}:
            raise HTTPException(404, "Unknown content action")
        result = getattr(content, action)(artifact_id, expected_revision=require_revision(if_match))
        return set_etag(response, result)

    @app.get("/api/deletions/{artifact_id:path}", response_model=ServiceResult)
    def deletion_plan(artifact_id: str, response: Response) -> dict[str, Any]:
        return set_etag(response, content.deletion_plan(artifact_id))

    @app.delete("/api/artifacts/{artifact_id:path}", response_model=ServiceResult)
    def delete(artifact_id: str, response: Response, cascade: bool = False, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, content.delete(artifact_id, require_revision(if_match), cascade=cascade))

    @app.get("/api/artifacts/{artifact_id:path}", response_model=ArtifactResult)
    def inspect(artifact_id: str, response: Response) -> dict[str, Any]:
        return set_etag(response, content.inspect(artifact_id))

    @app.patch("/api/artifacts/{artifact_id:path}", response_model=ArtifactResult)
    def update(artifact_id: str, patch: ArtifactPatch, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, content.update(artifact_id, patch.model_dump(exclude_unset=True), expected_revision=require_revision(if_match)))

    @app.get("/api/data/{name:path}", response_model=DataResult)
    def read_data(name: str, response: Response) -> dict[str, Any]:
        return set_etag(response, content.read_data(name))

    @app.get("/api/kanban", response_model=ServiceResult)
    def read_kanban(response: Response, column: str | None = None, q: str = "") -> dict[str, Any]:
        return set_etag(response, kanban.read(column=column, query=q))

    @app.get("/api/kanban/{card_id}", response_model=ServiceResult)
    def card_context(card_id: str, response: Response) -> dict[str, Any]:
        return set_etag(response, kanban.context(card_id))

    @app.get("/api/attachments/{attachment_id}")
    def attachment_file(attachment_id: str, inline: bool = False) -> Response:
        item, value = attachments.file(attachment_id)
        disposition = "inline" if inline and item.media_type in INLINE_IMAGES else "attachment"
        return Response(value, media_type=item.media_type, headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(item.name, safe='')}", "Content-Security-Policy": "default-src 'none'; sandbox"})

    @app.get("/api/context-attachments/{owner:path}")
    def owner_attachments(owner: str, response: Response) -> dict[str, Any]:
        return set_etag(response, attachments.read(owner))

    @app.post("/api/context-attachments/{owner:path}")
    async def upload_attachments(owner: str, request: Request, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        token = require_revision(if_match)
        form = await request.form()
        return set_etag(response, attachments.change(owner, uploads=await read_uploads(form), link=str(form.get("link")) if form.get("link") else None, expected_revision=token))

    @app.delete("/api/context-attachments/{owner:path}")
    def detach_attachment(owner: str, attachment_id: str, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, attachments.change(owner, remove=[attachment_id], expected_revision=require_revision(if_match)))

    @app.post("/api/kanban", response_model=ServiceResult, status_code=201)
    def create_card(payload: KanbanCreate, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, kanban.create(payload.model_dump(exclude_none=True), require_revision(if_match)))

    @app.patch("/api/kanban/{card_id}", response_model=ServiceResult)
    def update_card(card_id: str, payload: KanbanPatch, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, kanban.update(card_id, payload.model_dump(exclude_unset=True), require_revision(if_match)))

    @app.delete("/api/kanban/{card_id}", response_model=ServiceResult)
    def remove_card(card_id: str, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, kanban.remove(card_id, require_revision(if_match)))

    @app.put("/api/data/{name:path}", response_model=DataResult)
    def update_data(name: str, payload: StructuredUpdate, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        return set_etag(response, content.update_data(name, payload.data, expected_revision=require_revision(if_match)))

    @app.post("/api/validate", response_model=ServiceResult)
    def validate() -> dict[str, Any]:
        return content.validate()

    @app.get("/api/gallery", response_model=GalleryState)
    def read_gallery(response: Response) -> dict[str, Any]:
        catalog = content.list(kind="gallery")
        if len(catalog["artifacts"]) != 1:
            raise ServiceError("Expected one registered gallery", status=404, code="not_found")
        result = content.read_data("photos")
        if result["revision"] != catalog["revision"]:
            raise ServiceError("Gallery changed during inspection; reload it.", status=412, code="conflict")
        return set_etag(response, {"photos": result["data"]["photos"], "revision": result["revision"]})

    @app.put("/api/gallery", response_model=ServiceResult)
    def update_gallery(payload: GalleryUpdate, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        data = {"version": 1, "photos": [photo.model_dump() for photo in payload.photos]}
        return set_etag(response, content.update_gallery(data, expected_revision=require_revision(if_match)))

    @app.post("/api/batch", response_model=ServiceResult)
    def batch(payload: BatchUpdate, response: Response, if_match: str | None = Header(None)) -> dict[str, Any]:
        updates = [update.model_dump(exclude_unset=True) for update in payload.updates]
        return set_etag(response, content.batch(updates, payload.data, expected_revision=require_revision(if_match)))

    @app.post("/api/builds", response_model=ServiceResult, status_code=202)
    def build(payload: BuildRequest) -> dict[str, Any]:
        return builds.submit(mode=payload.mode)

    @app.get("/api/builds/{build_id}", response_model=ServiceResult)
    def build_status(build_id: str) -> dict[str, Any]:
        return builds.get(build_id)

    @app.get("/api/builds/{build_id}/logs", response_model=ServiceResult)
    def build_logs(build_id: str) -> dict[str, Any]:
        # IDs and runtime paths are resolved and checked by the build service.
        record = builds.get(build_id)
        return {"id": build_id, "status": record.get("status"), "logs": record.get("logs", record.get("log", "")), "error": record.get("error")}

    from watchtower.api.cms import cms_router

    app.include_router(cms_router(root))
    app.mount("/cms/static", StaticFiles(directory=root / "frontend/templates/cms/static"), name="cms-static")
    return app
