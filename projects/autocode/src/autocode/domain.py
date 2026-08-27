"""Serializable product records shared by the local and sync tiers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SessionEvent:
    """One append-only observation in a session."""

    session_id: str
    cursor: int
    kind: str
    payload: dict[str, Any]
    event_id: str = ""
    created_at: str = ""
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(self, "created_at", now_iso())
        if not self.event_id:
            payload_hash = hashlib.sha256(
                json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:16]
            object.__setattr__(
                self,
                "event_id",
                f"{self.session_id}:{self.cursor}:{self.kind}:{payload_hash}:{self.created_at}",
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SessionEvent:
        return cls(**value)


@dataclass
class SessionRecord:
    """The canonical entity transported between every product surface."""

    session_id: str
    title: str = "Untitled session"
    config_hash: str = ""
    version: int = 0
    updated_at: str = field(default_factory=now_iso)
    events: list[SessionEvent] = field(default_factory=list)

    def append(self, kind: str, payload: dict[str, Any], *, idempotency_key: str = "") -> SessionEvent:
        cursor = len(self.events) + 1
        event = SessionEvent(
            self.session_id,
            cursor,
            kind,
            payload,
            idempotency_key=idempotency_key,
        )
        self.events.append(event)
        self.version += 1
        self.updated_at = event.created_at
        return event

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["events"] = [event.to_dict() for event in self.events]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SessionRecord:
        fields = dict(value)
        events = [SessionEvent.from_dict(item) for item in fields.pop("events", [])]
        return cls(events=events, **fields)


def merge_append_only_events(*event_lists: list[SessionEvent]) -> list[SessionEvent]:
    """Union append-only events in a stable order, making merge associative."""

    unique = {event.event_id: event for events in event_lists for event in events}
    return sorted(unique.values(), key=lambda event: (event.created_at, event.event_id))
