"""Application use cases shared by the CLI and web transports."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from autocode.artifacts import ArtifactRef, LocalArtifactStore
from autocode.domain import SessionEvent, SessionRecord
from autocode.realtime import SessionBroker
from autocode.runner import AgentRunner, DemoAgentRunner
from autocode.search.index import LocalSearchIndex, SearchHit
from autocode.store.repository import SessionRepository


class SessionNotFound(LookupError):
    pass


class AutocodeApplication:
    """Coordinate durable session state, agent runs, and live publication."""

    def __init__(
        self,
        repository: SessionRepository,
        runner: AgentRunner | None = None,
        broker: SessionBroker | None = None,
        artifact_store: LocalArtifactStore | None = None,
        search_index: LocalSearchIndex | None = None,
    ) -> None:
        self.repository = repository
        self.runner = runner or DemoAgentRunner()
        self.broker = broker or SessionBroker()
        self.artifact_store = artifact_store
        self.search_index = search_index or LocalSearchIndex()
        self._run_locks: dict[str, asyncio.Lock] = {}

    def create_session(self, title: str = "Untitled session") -> SessionRecord:
        return self.repository.create(title=title.strip() or "Untitled session")

    def list_sessions(self, limit: int = 50) -> list[SessionRecord]:
        return self.repository.list(limit=limit)

    def get_session(self, session_id: str) -> SessionRecord:
        session = self.repository.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    def events_after(self, session_id: str, cursor: int = 0) -> list[SessionEvent]:
        self.get_session(session_id)
        return self.repository.events_after(session_id, cursor)

    def put_artifact(
        self, content: bytes, content_type: str = "application/octet-stream"
    ) -> ArtifactRef:
        return self._artifacts().put(content, content_type)

    def list_artifacts(self) -> list[ArtifactRef]:
        return self._artifacts().list()

    def get_artifact(self, digest: str) -> bytes:
        return self._artifacts().get(digest)

    def delete_artifact(self, digest: str) -> None:
        self._artifacts().delete(digest)

    def restore_artifact(self, digest: str) -> ArtifactRef:
        return self._artifacts().restore(digest)

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        return self.search_index.search(query, limit=limit)

    async def stream_message(
        self, session_id: str, content: str
    ) -> AsyncIterator[SessionEvent]:
        message = content.strip()
        if not message:
            raise ValueError("message content cannot be empty")
        self.get_session(session_id)
        lock = self._run_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            user_event = self._record(session_id, "user_message", {"content": message})
            yield user_event
            try:
                async for runner_event in self.runner.stream(session_id, message):
                    event = self._record(session_id, runner_event.kind, runner_event.payload)
                    yield event
            except asyncio.CancelledError:
                event = self._record(session_id, "run_finished", {"reason": "cancelled"})
                yield event
                raise
            except Exception as exc:
                event = self._record(session_id, "run_error", {"error": str(exc)})
                yield event

    def _record(self, session_id: str, kind: str, payload: dict[str, Any]) -> SessionEvent:
        event = self.repository.append(session_id, kind, payload)
        content = payload.get("content")
        if kind in {"user_message", "assistant_message"} and isinstance(content, str):
            self.search_index.add(f"session:{session_id}:{event.cursor}", content)
        self.broker.publish(session_id, event.to_dict())
        return event

    def _artifacts(self) -> LocalArtifactStore:
        if self.artifact_store is None:
            raise RuntimeError("artifact storage is not configured")
        return self.artifact_store
