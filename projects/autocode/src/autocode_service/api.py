"""FastAPI transport for the autocode full-stack application."""

from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from autocode.application import AutocodeApplication, SessionNotFound
from autocode.artifacts import LocalArtifactStore
from autocode.domain import SessionRecord
from autocode.ops.metrics import Metrics
from autocode.runner import AgentRunner, runner_for_mode
from autocode.store.repository import SessionRepository
from autocode_service.api_sync import SyncService
from autocode_service.auth import TokenAuthority
from autocode_service.deps import health_report

STATIC_DIR = Path(__file__).resolve().parent.parent / "autocode" / "web"


class SessionCreate(BaseModel):
    title: str = Field(default="Untitled session", max_length=120)


class SocketCommand(BaseModel):
    type: Literal["user_message", "cancel"]
    content: str = Field(default="", max_length=20_000)


class SyncPush(BaseModel):
    session: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=200)


def create_app(
    application: AutocodeApplication | None = None,
    *,
    database_path: str | Path | None = None,
    runner: AgentRunner | None = None,
    agent_mode: str | None = None,
    token_authority: TokenAuthority | None = None,
    sync_service: SyncService | None = None,
) -> FastAPI:
    """Compose the browser, HTTP, WebSocket, application, and storage layers."""

    mode = agent_mode or os.environ.get("AUTOCODE_AGENT_MODE", "demo")
    if application is None:
        path = Path(database_path) if database_path else _default_database_path()
        selected_runner = runner or runner_for_mode(mode, cwd=os.getcwd())
        application = AutocodeApplication(
            SessionRepository(path),
            selected_runner,
            artifact_store=LocalArtifactStore(path.parent / "artifacts"),
        )

    app = FastAPI(title="autocode", version="0.2.0")
    app.state.application = application
    app.state.agent_mode = mode
    app.state.active_runs = {}
    app.state.token_authority = token_authority
    app.state.sync_service = sync_service or SyncService()
    app.state.metrics = Metrics()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readiness() -> dict[str, object]:
        try:
            application.list_sessions(limit=1)
            database_ready = True
        except Exception:
            database_ready = False
        try:
            application.list_artifacts()
            artifacts_ready = True
        except (OSError, RuntimeError):
            artifacts_ready = False
        return health_report(database=database_ready, artifacts=artifacts_ready)

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        return app.state.metrics.prometheus()

    @app.get("/api/config")
    async def config() -> dict[str, str]:
        return {"agent_mode": app.state.agent_mode, "transport": "rest+websocket"}

    @app.get("/api/sessions")
    async def list_sessions(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
        return [_session_summary(session) for session in application.list_sessions(limit)]

    @app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
    async def create_session(body: SessionCreate) -> dict[str, Any]:
        session = application.create_session(body.title)
        app.state.metrics.inc("sessions_created")
        return session.to_dict()

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        try:
            return application.get_session(session_id).to_dict()
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc

    @app.get("/api/sessions/{session_id}/events")
    async def get_events(session_id: str, after: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
        try:
            return [event.to_dict() for event in application.events_after(session_id, after)]
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc

    @app.get("/api/search")
    async def search(
        q: str = Query(min_length=1, max_length=500),
        limit: int = Query(default=10, ge=1, le=50),
    ) -> list[dict[str, Any]]:
        return [asdict(hit) for hit in application.search(q, limit)]

    @app.get("/api/artifacts")
    async def list_artifacts() -> list[dict[str, Any]]:
        try:
            return [asdict(ref) for ref in application.list_artifacts()]
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/artifacts", status_code=status.HTTP_201_CREATED)
    async def put_artifact(request: Request) -> dict[str, Any]:
        content = await request.body()
        if not content:
            raise HTTPException(status_code=422, detail="artifact body cannot be empty")
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="artifact exceeds the 5 MiB local limit")
        try:
            ref = application.put_artifact(
                content, request.headers.get("content-type", "application/octet-stream")
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        app.state.metrics.inc("artifacts_uploaded")
        return asdict(ref)

    @app.get("/api/artifacts/{digest}")
    async def get_artifact(digest: str) -> StreamingResponse:
        try:
            content = application.get_artifact(digest)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return StreamingResponse(iter([content]), media_type="application/octet-stream")

    @app.delete("/api/artifacts/{digest}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_artifact(digest: str) -> Response:
        try:
            application.delete_artifact(digest)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/api/artifacts/{digest}/restore")
    async def restore_artifact(digest: str) -> dict[str, Any]:
        try:
            return asdict(application.restore_artifact(digest))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/sync/sessions")
    async def push_sync_session(
        body: SyncPush, authorization: str | None = Header(default=None)
    ) -> dict[str, Any]:
        _authorize_device(app, authorization)
        try:
            record = SessionRecord.from_dict(body.session)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid session record") from exc
        return app.state.sync_service.put_session(record, body.idempotency_key)

    @app.get("/api/sync/sessions/{session_id}/events")
    async def pull_sync_events(
        session_id: str,
        cursor: int = Query(default=0, ge=0),
        authorization: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        _authorize_device(app, authorization)
        return app.state.sync_service.get_events(session_id, cursor)

    @app.websocket("/ws/sessions/{session_id}")
    async def session_socket(websocket: WebSocket, session_id: str, after: int = 0) -> None:
        try:
            replay = application.events_after(session_id, after)
        except SessionNotFound:
            await websocket.close(code=4404, reason="session not found")
            return

        await websocket.accept()
        observer_id, queue = application.broker.subscribe(session_id)
        for event in replay:
            await websocket.send_json(event.to_dict())
        sender = asyncio.create_task(_forward_events(websocket, queue))

        try:
            while True:
                raw = await websocket.receive_json()
                try:
                    command = SocketCommand.model_validate(raw)
                except ValidationError as exc:
                    await websocket.send_json(
                        {"type": "protocol_error", "detail": exc.errors(include_url=False)}
                    )
                    continue

                if command.type == "cancel":
                    active = app.state.active_runs.get(session_id)
                    if active is not None and not active.done():
                        active.cancel()
                    continue

                if not command.content.strip():
                    await websocket.send_json(
                        {"type": "protocol_error", "detail": "message content cannot be empty"}
                    )
                    continue
                active = app.state.active_runs.get(session_id)
                if active is not None and not active.done():
                    await websocket.send_json(
                        {"type": "protocol_error", "detail": "a run is already active"}
                    )
                    continue
                task = asyncio.create_task(_complete_run(application, session_id, command.content))
                app.state.active_runs[session_id] = task
                app.state.metrics.inc("runs_started")
                task.add_done_callback(
                    lambda completed, target=session_id: _discard_run(app, target, completed)
                )
        except WebSocketDisconnect:
            pass
        finally:
            application.broker.unsubscribe(session_id, observer_id)
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender

    return app


async def _complete_run(
    application: AutocodeApplication, session_id: str, content: str
) -> None:
    async for _event in application.stream_message(session_id, content):
        pass


async def _forward_events(
    websocket: WebSocket, queue: asyncio.Queue[dict[str, Any]]
) -> None:
    while True:
        await websocket.send_json(await queue.get())


def _discard_run(app: FastAPI, session_id: str, completed: asyncio.Task[None]) -> None:
    if app.state.active_runs.get(session_id) is completed:
        app.state.active_runs.pop(session_id, None)
    with contextlib.suppress(asyncio.CancelledError, Exception):
        completed.result()


def _session_summary(session: SessionRecord) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "title": session.title,
        "version": session.version,
        "updated_at": session.updated_at,
    }


def _default_database_path() -> Path:
    return Path(os.environ.get("AUTOCODE_DATA_DIR", ".autocode")) / "sessions.db"


def _authorize_device(app: FastAPI, authorization: str | None) -> dict[str, object]:
    authority: TokenAuthority | None = app.state.token_authority
    if authority is None:
        raise HTTPException(status_code=503, detail="sync authentication is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return authority.verify(token)
    except PermissionError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
