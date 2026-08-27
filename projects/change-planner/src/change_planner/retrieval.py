"""Deterministic lexical, dense, hybrid, structural, and agentic retrieval."""

import hashlib
import math
import re
from dataclasses import dataclass

from change_planner.schemas import (
    Evidence,
    FixtureSource,
    RetrievalHit,
    RetrievalMethod,
    SourceKind,
)


@dataclass(frozen=True)
class SearchResult:
    source: FixtureSource
    lexical: float
    dense: float
    structural: float


class FixtureCatalog:
    def __init__(self, sources: list[FixtureSource]):
        self.sources = {source.id: source for source in sources}

    def get(self, source_id: str) -> FixtureSource:
        return self.sources[source_id]

    def select(self, source_kinds: list[SourceKind] | None = None) -> list[FixtureSource]:
        if not source_kinds:
            return list(self.sources.values())
        wanted = set(source_kinds)
        return [source for source in self.sources.values() if source.source_kind in wanted]


def tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", text.lower())
    expanded = [part for word in raw for part in word.split("_")]
    return {word for word in expanded if len(word) > 2}


def _vector(text: str, width: int = 32) -> list[float]:
    vector = [0.0] * width
    for token in tokens(text):
        digest = hashlib.sha256(token.encode()).digest()
        index = digest[0] % width
        vector[index] += 1.0 if digest[1] % 2 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return max(0.0, sum(a * b for a, b in zip(left, right, strict=True)))


def _score(query: str, source: FixtureSource) -> tuple[float, float, float]:
    query_tokens = tokens(query)
    source_text = " ".join([source.path, *source.tags, *source.symbols, source.text])
    source_tokens = tokens(source_text)
    lexical = len(query_tokens & source_tokens) / max(1, len(query_tokens))
    dense = _cosine(_vector(query), _vector(source_text))
    structural = float(bool(query_tokens & set(tokens(" ".join(source.symbols + source.related_sources)))))
    return lexical, dense, structural


def _evidence(source: FixtureSource, hits: list[RetrievalHit]) -> Evidence:
    content_hash = hashlib.sha256(source.text.encode()).hexdigest()[:16]
    return Evidence(
        id=f"{source.repository}@{source.revision}:{source.path}",
        repository=source.repository,
        revision=source.revision,
        source_kind=source.source_kind,
        path=source.path,
        symbol=source.symbols[0] if source.symbols else None,
        start_line=1,
        end_line=max(1, source.text.count("\n") + 1),
        content_hash=f"sha256:{content_hash}",
        text=source.text,
        retrieval=hits,
    )


def search(
    catalog: FixtureCatalog,
    query: str,
    *,
    source_kinds: list[SourceKind] | None = None,
    method: RetrievalMethod = "hybrid",
    top_k: int = 5,
) -> list[Evidence]:
    candidates = [
        SearchResult(source, *_score(query, source))
        for source in catalog.select(source_kinds)
        if source.available
    ]
    if method == "lexical":
        candidates.sort(key=lambda row: (-row.lexical, row.source.id))
        scores = [row.lexical for row in candidates]
    elif method == "dense":
        candidates.sort(key=lambda row: (-row.dense, row.source.id))
        scores = [row.dense for row in candidates]
    elif method == "structural":
        candidates.sort(key=lambda row: (-row.structural, -row.lexical, row.source.id))
        scores = [row.structural for row in candidates]
    elif method == "agentic":
        return agentic_search(catalog, query, source_kinds=source_kinds, top_k=top_k)
    else:
        candidates.sort(
            key=lambda row: (-(0.55 * row.lexical + 0.3 * row.dense + 0.15 * row.structural), row.source.id)
        )
        scores = [0.55 * row.lexical + 0.3 * row.dense + 0.15 * row.structural for row in candidates]
    selected = [(row, score) for row, score in zip(candidates, scores, strict=True) if score > 0][:top_k]
    return [
        _evidence(
            row.source,
            [RetrievalHit(method=method, rank=rank, score=round(score, 4))],
        )
        for rank, (row, score) in enumerate(selected, start=1)
    ]


def hybrid_search(
    catalog: FixtureCatalog,
    query: str,
    *,
    source_kinds: list[SourceKind] | None = None,
    top_k: int = 5,
) -> list[Evidence]:
    methods = [
        search(catalog, query, source_kinds=source_kinds, method="lexical", top_k=top_k * 2),
        search(catalog, query, source_kinds=source_kinds, method="dense", top_k=top_k * 2),
        search(catalog, query, source_kinds=source_kinds, method="structural", top_k=top_k * 2),
    ]
    by_id: dict[str, Evidence] = {}
    for rows in methods:
        for evidence in rows:
            current = by_id.setdefault(evidence.id, evidence.model_copy(update={"retrieval": []}))
            current.retrieval.extend(evidence.retrieval)
    for evidence in by_id.values():
        evidence.retrieval.sort(key=lambda hit: (hit.method, hit.rank))
    ranked = sorted(
        by_id.values(),
        key=lambda evidence: (
            -sum(1.0 / (20 + hit.rank) for hit in evidence.retrieval),
            evidence.id,
        ),
    )
    return [item.model_copy(update={"retrieval": item.retrieval}) for item in ranked[:top_k]]


def agentic_search(
    catalog: FixtureCatalog,
    query: str,
    *,
    source_kinds: list[SourceKind] | None = None,
    top_k: int = 5,
) -> list[Evidence]:
    """Perform a bounded search-refine-search loop using recovered symbols.

    This deterministic stand-in for an agentic retriever makes the first pass
    propose anchors, then expands the query with their symbols and linked
    source paths. Returned evidence keeps that second-pass result observable.
    """

    initial = hybrid_search(catalog, query, source_kinds=source_kinds, top_k=max(top_k, 3))
    by_path = {source.path: source for source in catalog.select(source_kinds)}
    expansion = [
        token
        for item in initial[:3]
        for token in [*by_path[item.path].symbols, *by_path[item.path].related_sources]
    ]
    refined_query = " ".join([query, *expansion])
    refined = hybrid_search(catalog, refined_query, source_kinds=source_kinds, top_k=top_k * 2)
    merged: dict[str, Evidence] = {}
    for item in [*refined, *initial]:
        merged.setdefault(item.id, item)
    return [
        item.model_copy(
            update={
                "retrieval": [
                    RetrievalHit(method="agentic", rank=rank, score=round(1.0 / rank, 4))
                ]
            }
        )
        for rank, item in enumerate(merged.values(), start=1)
        if rank <= top_k
    ]
