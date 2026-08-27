"""Transport-neutral synchronization use cases used by the HTTP adapter."""

from __future__ import annotations

from typing import Any

from autocode.domain import SessionRecord
from autocode.sync.client import InMemorySyncServer


class SyncService:
    def __init__(self) -> None:
        self.server = InMemorySyncServer()

    def put_session(self, record: SessionRecord, idempotency_key: str) -> dict[str, Any]:
        return self.server.push(record, idempotency_key=idempotency_key).to_dict()

    def get_events(self, session_id: str, cursor: int = 0) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.server.pull(session_id, cursor)]
