"""Small deterministic chunkers used before an ANN adapter is introduced."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    document_id: str
    ordinal: int
    text: str


def chunk_text(document_id: str, text: str, *, lines_per_chunk: int = 40) -> list[Chunk]:
    lines = text.splitlines() or [""]
    return [
        Chunk(document_id, ordinal, "\n".join(lines[start : start + lines_per_chunk]))
        for ordinal, start in enumerate(range(0, len(lines), lines_per_chunk))
    ]


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9]+", text.lower()))
