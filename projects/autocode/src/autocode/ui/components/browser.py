"""Session-browser view model."""

from __future__ import annotations

from autocode.domain import SessionRecord


def rows(sessions: list[SessionRecord]) -> list[dict[str, object]]:
    return [
        {"session_id": session.session_id, "title": session.title, "events": len(session.events)}
        for session in sessions
    ]
