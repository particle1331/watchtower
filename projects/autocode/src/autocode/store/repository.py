"""SQLite projection for browsing and resuming sessions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from autocode.domain import SessionEvent, SessionRecord
from autocode.store.journal import Journal

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    cursor INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS events_session_cursor ON events(session_id, cursor);
CREATE INDEX IF NOT EXISTS sessions_updated_at ON sessions(updated_at DESC);
"""


class SessionRepository:
    """Single access layer for the local session database."""

    def __init__(self, path: str | Path, journal_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(journal_path or self.path.with_suffix(".journal"))
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, title: str = "Untitled session", config_hash: str = "") -> SessionRecord:
        record = SessionRecord(str(uuid.uuid4()), title=title, config_hash=config_hash)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (record.session_id, record.title, record.config_hash, record.version, record.updated_at),
            )
        return record

    def append(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str = "",
    ) -> SessionEvent:
        current = self.get(session_id)
        if current is None:
            raise KeyError(f"unknown session: {session_id}")
        event = SessionEvent(
            session_id,
            len(current.events) + 1,
            kind,
            payload,
            idempotency_key=idempotency_key,
        )
        if idempotency_key:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM events WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
            if row is not None:
                return self._event_from_row(row)

        # The durable fact is recorded before the queryable projection changes.
        self.journal.append({"type": "session_event", "event": event.to_dict()})
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.session_id,
                    event.cursor,
                    event.kind,
                    json.dumps(event.payload, sort_keys=True),
                    event.created_at,
                    event.idempotency_key or None,
                ),
            )
            connection.execute(
                "UPDATE sessions SET version = ?, updated_at = ? WHERE session_id = ?",
                (event.cursor, event.created_at, session_id),
            )
        return event

    def get(self, session_id: str) -> SessionRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            events = connection.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY cursor", (session_id,)
            ).fetchall()
        return SessionRecord(
            session_id=row["session_id"],
            title=row["title"],
            config_hash=row["config_hash"],
            version=row["version"],
            updated_at=row["updated_at"],
            events=[self._event_from_row(event) for event in events],
        )

    def list(self, limit: int = 50) -> list[SessionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT session_id FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        records: list[SessionRecord] = []
        for row in rows:
            record = self.get(row["session_id"])
            if record is not None:
                records.append(record)
        return records

    def events_after(self, session_id: str, cursor: int = 0) -> list[SessionEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE session_id = ? AND cursor > ? ORDER BY cursor",
                (session_id, cursor),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def recover(self) -> int:
        """Project journal records missing from SQLite after an interrupted write."""
        recovered = 0
        with self._connect() as connection:
            for record in self.journal.read():
                event = SessionEvent.from_dict(record["event"])
                exists = connection.execute(
                    "SELECT 1 FROM events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                if exists is not None:
                    continue
                connection.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.session_id,
                        event.cursor,
                        event.kind,
                        json.dumps(event.payload, sort_keys=True),
                        event.created_at,
                        event.idempotency_key or None,
                    ),
                )
                connection.execute(
                    "UPDATE sessions SET version = max(version, ?), updated_at = max(updated_at, ?) WHERE session_id = ?",
                    (event.cursor, event.created_at, event.session_id),
                )
                recovered += 1
        return recovered

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> SessionEvent:
        return SessionEvent(
            session_id=row["session_id"],
            cursor=row["cursor"],
            kind=row["kind"],
            payload=json.loads(row["payload"]),
            event_id=row["event_id"],
            created_at=row["created_at"],
            idempotency_key=row["idempotency_key"] or "",
        )
