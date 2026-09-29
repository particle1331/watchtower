"""Presentation helpers for streamed messages and tool-call cards."""

from __future__ import annotations

from autocode.state import ToolCard


def card_label(card: ToolCard) -> str:
    if card.status == "error":
        return f"{card.name}: error: {card.error}"
    return f"{card.name}: {card.status}"


def stream_buffer(chunks: list[str]) -> str:
    return "".join(chunks)
