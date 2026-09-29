"""Deterministic lexical and hybrid search with an adapter-friendly API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from autocode.search.chunkers import Chunk, chunk_text, tokens


@dataclass(frozen=True)
class SearchHit:
    document_id: str
    score: float
    text: str
    method: str


class LocalSearchIndex:
    """An offline baseline that makes later vector comparisons measurable."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._document_tokens: dict[str, set[str]] = {}
        self._fingerprints: dict[str, str] = {}

    def add(self, document_id: str, text: str, *, lines_per_chunk: int = 40) -> None:
        chunks = chunk_text(document_id, text, lines_per_chunk=lines_per_chunk)
        for old_id in [key for key in self._chunks if key.startswith(f"{document_id}#")]:
            self._chunks.pop(old_id, None)
            self._document_tokens.pop(old_id, None)
        for chunk in chunks:
            chunk_id = f"{chunk.document_id}#{chunk.ordinal}"
            self._chunks[chunk_id] = chunk
            self._document_tokens[chunk_id] = tokens(chunk.text)
        import hashlib

        self._fingerprints[document_id] = hashlib.sha256(text.encode()).hexdigest()

    def add_path(self, path: str | Path, *, lines_per_chunk: int = 40) -> None:
        path = Path(path)
        self.add(str(path), path.read_text(encoding="utf-8"), lines_per_chunk=lines_per_chunk)

    def search(self, query: str, *, limit: int = 10, method: str = "hybrid") -> list[SearchHit]:
        query_tokens = tokens(query)
        scored: list[SearchHit] = []
        for chunk_id, chunk_tokens in self._document_tokens.items():
            chunk = self._chunks[chunk_id]
            overlap = len(query_tokens & chunk_tokens)
            if not overlap:
                continue
            lexical = overlap / max(len(query_tokens), 1)
            exact_bonus = sum(1 for token in query_tokens if token in chunk.text.lower()) / max(len(query_tokens), 1)
            # The dense baseline is a deterministic token-set proxy. It keeps the
            # notebook experiment offline while preserving the adapter boundary.
            dense = overlap / max(len(query_tokens | chunk_tokens), 1)
            score = lexical + (0.15 * exact_bonus if method != "dense" else 0) + (0.35 * dense if method == "hybrid" else 0)
            scored.append(SearchHit(chunk_id, score, chunk.text, method))
        return sorted(scored, key=lambda hit: (-hit.score, hit.document_id))[:limit]

    def freshness(self, document_id: str, text: str) -> str:
        import hashlib

        current = hashlib.sha256(text.encode()).hexdigest()
        return "fresh" if self._fingerprints.get(document_id) == current else "stale"

    def snapshot(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((key, chunk.text) for key, chunk in self._chunks.items()))

    def __len__(self) -> int:
        return len(self._chunks)
