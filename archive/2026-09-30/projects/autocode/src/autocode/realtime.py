"""Cursor-based event log and bounded fan-out for live runs."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventEnvelope:
    cursor: int
    kind: str
    payload: dict[str, Any]


class ReplayLog:
    def __init__(self) -> None:
        self._events: list[EventEnvelope] = []

    def publish(self, kind: str, payload: dict[str, Any]) -> EventEnvelope:
        event = EventEnvelope(len(self._events) + 1, kind, payload)
        self._events.append(event)
        return event

    def since(self, cursor: int = 0) -> list[EventEnvelope]:
        return [event for event in self._events if event.cursor > cursor]

    @property
    def cursor(self) -> int:
        return len(self._events)


class FanoutHub:
    """Publish to observers without allowing a slow observer to block a run."""

    def __init__(self, log: ReplayLog | None = None, max_queue: int = 32) -> None:
        self.log = log or ReplayLog()
        self.max_queue = max_queue
        self._subscribers: dict[str, asyncio.Queue[EventEnvelope]] = {}

    def subscribe(self, observer_id: str, *, after: int = 0) -> asyncio.Queue[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(self.max_queue)
        for event in self.log.since(after):
            if not queue.full():
                queue.put_nowait(event)
        self._subscribers[observer_id] = queue
        return queue

    def unsubscribe(self, observer_id: str) -> None:
        self._subscribers.pop(observer_id, None)

    def publish(self, kind: str, payload: dict[str, Any]) -> EventEnvelope:
        event = self.log.publish(kind, payload)
        for observer_id, queue in list(self._subscribers.items()):
            if queue.full():
                # Evicting a slow consumer protects the producer. Replay makes
                # it safe for that observer to reconnect later.
                self.unsubscribe(observer_id)
                continue
            queue.put_nowait(event)
        return event

    @property
    def observers(self) -> tuple[str, ...]:
        return tuple(self._subscribers)


class SessionBroker:
    """Fan out persisted session events to every connected browser observer."""

    def __init__(self, max_queue: int = 128) -> None:
        self.max_queue = max_queue
        self._subscribers: dict[str, dict[str, asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, session_id: str) -> tuple[str, asyncio.Queue[dict[str, Any]]]:
        observer_id = str(uuid.uuid4())
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self.max_queue)
        self._subscribers.setdefault(session_id, {})[observer_id] = queue
        return observer_id, queue

    def unsubscribe(self, session_id: str, observer_id: str) -> None:
        observers = self._subscribers.get(session_id)
        if observers is None:
            return
        observers.pop(observer_id, None)
        if not observers:
            self._subscribers.pop(session_id, None)

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        observers = self._subscribers.get(session_id, {})
        for observer_id, queue in list(observers.items()):
            if queue.full():
                self.unsubscribe(session_id, observer_id)
                continue
            queue.put_nowait(event)

    def observer_count(self, session_id: str) -> int:
        return len(self._subscribers.get(session_id, {}))
