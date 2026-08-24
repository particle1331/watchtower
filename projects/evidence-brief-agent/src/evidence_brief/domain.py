"""Deterministic source, retrieval, provenance, and citation tools."""

import re
from dataclasses import dataclass

from evidence_brief.schemas import Claim, Passage, ResearchTask, SourceRecord


@dataclass(frozen=True)
class RetrievalObservation:
    source_id: str
    status: str
    reason: str


class FixtureCatalog:
    def __init__(self, sources: list[SourceRecord]):
        self.sources = {source.id: source for source in sources}

    def select(self, tags: list[str]) -> list[SourceRecord]:
        wanted = set(tags)
        return [source for source in self.sources.values() if wanted.intersection(source.tags)]


def _keywords(text: str) -> set[str]:
    stop = {"and", "the", "for", "does", "should", "with", "from", "atlasvector"}
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 3 and word not in stop}


def retrieve(
    catalog: FixtureCatalog, task: ResearchTask
) -> tuple[list[Passage], list[RetrievalObservation]]:
    passages: list[Passage] = []
    observations: list[RetrievalObservation] = []
    query_terms = _keywords(task.query)
    for source in catalog.select(task.source_tags):
        if not source.available:
            observations.append(RetrievalObservation(source.id, "unavailable", "source unavailable"))
            continue
        if not source.in_scope:
            observations.append(RetrievalObservation(source.id, "rejected", "outside source policy"))
            continue
        matched = False
        for sentence in re.split(r"(?<=\.)\s+", source.text):
            if query_terms.intersection(_keywords(sentence)):
                start = source.text.index(sentence)
                passages.append(
                    Passage(
                        id=f"{source.id}:{start}-{start + len(sentence)}",
                        source_id=source.id,
                        start=start,
                        end=start + len(sentence),
                        text=sentence,
                        query=task.query,
                    )
                )
                matched = True
        observations.append(
            RetrievalObservation(
                source.id,
                "matched" if matched else "empty",
                "matching passage found" if matched else "no matching passage",
            )
        )
    return passages, observations


def render_citation(claim: Claim) -> str:
    if not claim.source_id or not claim.passage_id:
        raise ValueError(f"claim {claim.id} has no resolvable provenance")
    return f"[{claim.source_id}#{claim.passage_id.split(':', 1)[1]}]"


def verify_claim(claim: Claim, passages: list[Passage]) -> bool:
    if claim.kind == "inference":
        return claim.uncertainty != "none"
    passage = next((item for item in passages if item.id == claim.passage_id), None)
    return bool(passage and passage.source_id == claim.source_id)
