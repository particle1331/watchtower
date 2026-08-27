"""Pure UI state transitions used by both a desktop client and tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class ToolCard:
    call_id: str
    name: str
    status: str = "pending"
    output: str = ""
    error: str = ""


@dataclass(frozen=True)
class UIState:
    session_id: str = ""
    messages: tuple[str, ...] = ()
    streaming: bool = False
    connection: str = "offline"
    draft: str = ""
    cards: tuple[ToolCard, ...] = ()
    notice: str = ""


def reduce(state: UIState, action: dict[str, Any]) -> UIState:
    """Apply one action without mutating prior state.

    Duplicate tool events are idempotent and late completion events cannot
    move a card backwards. This makes reconnect/replay safe for the UI.
    """

    kind = action.get("type", "")
    if kind == "session_selected":
        return replace(state, session_id=action["session_id"], notice="")
    if kind == "draft_changed":
        return replace(state, draft=action.get("value", ""))
    if kind == "message_submitted":
        message = action.get("content", state.draft)
        return replace(state, messages=(*state.messages, message), draft="", streaming=True)
    if kind == "stream_started":
        return replace(state, streaming=True, connection="online")
    if kind == "text_delta":
        delta = action.get("content", "")
        if state.messages and state.streaming:
            return replace(state, messages=(*state.messages[:-1], state.messages[-1] + delta))
        return replace(state, messages=(*state.messages, delta), streaming=True)
    if kind == "stream_finished":
        return replace(state, streaming=False)
    if kind == "connection_changed":
        return replace(state, connection=action.get("value", "offline"))
    if kind == "tool_started":
        call_id = action["call_id"]
        if any(card.call_id == call_id for card in state.cards):
            return state
        card = ToolCard(call_id, action["name"], status="running")
        return replace(state, cards=(*state.cards, card))
    if kind == "tool_finished":
        call_id = action["call_id"]
        status = "done" if action.get("success", True) else "error"
        cards = tuple(
            replace(card, status=status, output=action.get("output", ""), error=action.get("error", ""))
            if card.call_id == call_id and card.status not in {"done", "error"}
            else card
            for card in state.cards
        )
        return replace(state, cards=cards)
    if kind == "cancelled":
        return replace(state, streaming=False, notice="Run cancelled")
    return state
