"""A cursor and idempotency-key based sync client for the local contract."""

from __future__ import annotations

from dataclasses import replace

from autocode.domain import SessionEvent, SessionRecord
from autocode.sync.conflicts import merge_records


class InMemorySyncServer:
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}
        self.applied_keys: set[str] = set()

    def push(self, record: SessionRecord, *, idempotency_key: str) -> SessionRecord:
        if idempotency_key in self.applied_keys:
            return self.records[record.session_id]
        self.applied_keys.add(idempotency_key)
        self.records[record.session_id] = merge_records(self.records.get(record.session_id, record), record)
        return self.records[record.session_id]

    def pull(self, session_id: str, cursor: int = 0) -> list[SessionEvent]:
        return [event for event in self.records.get(session_id, SessionRecord(session_id)).events if event.cursor > cursor]


class SyncClient:
    def __init__(self, device_id: str, server: InMemorySyncServer) -> None:
        self.device_id = device_id
        self.server = server
        self.cursors: dict[str, int] = {}

    def push(self, record: SessionRecord) -> SessionRecord:
        key = f"{self.device_id}:{record.session_id}:{record.version}"
        return self.server.push(record, idempotency_key=key)

    def pull_into(self, record: SessionRecord) -> SessionRecord:
        cursor = self.cursors.get(record.session_id, 0)
        remote_events = self.server.pull(record.session_id, cursor)
        remote = replace(record, events=remote_events, version=len(remote_events))
        merged = merge_records(record, remote)
        self.cursors[record.session_id] = max((event.cursor for event in remote_events), default=cursor)
        return merged
