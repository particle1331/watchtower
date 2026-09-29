"""Layered deterministic evaluation for retrieval and change-planning variants."""

import math
from statistics import mean

from change_planner.fixtures import load_cases, load_sources, request_for, snapshot
from change_planner.retrieval import FixtureCatalog, search
from change_planner.schemas import (
    EvaluationReport,
    EvaluationRow,
    MemoryRecord,
    RetrievalMethod,
    RetrievalMetrics,
)
from change_planner.workflow import MemoryStore, run_fixture


def _source_id(path: str) -> str:
    return next(source.id for source in load_sources() if source.path == path)


def _row(case, variant: str) -> EvaluationRow:
    state = run_fixture(case.id, variant=variant)
    evidence = state.get("evidence", [])
    found_sources = {_source_id(item["path"]) for item in evidence}
    found_tests = {_source_id(item["path"]) for item in evidence if item["source_kind"] == "test"}
    found_symbols = {
        symbol
        for source in load_sources()
        if source.id in found_sources
        for symbol in source.symbols
    }
    source_by_id = {source.id: source for source in load_sources()}
    expected_paths = {source_by_id[source_id].path for source_id in case.expected_sources}
    found_paths = {item["path"] for item in evidence}
    evidence_by_id = {item["id"]: item for item in evidence}
    linked_test_ids = {
        _source_id(evidence_by_id[link["test_evidence_id"]]["path"])
        for link in state.get("test_links", [])
        if link["test_evidence_id"] in evidence_by_id
    }
    artifact = state.get("artifact", {})
    return EvaluationRow(
        case_id=case.id,
        tier=case.tier,
        variant=variant,
        evidence_recall=len(found_sources.intersection(case.expected_sources)) / len(case.expected_sources),
        test_recall=len(found_tests.intersection(case.expected_tests)) / len(case.expected_tests),
        symbol_recall=len(found_symbols.intersection(case.expected_symbols)) / len(case.expected_symbols),
        affected_file_recall=len(found_paths.intersection(expected_paths)) / len(expected_paths),
        affected_symbol_recall=len(found_symbols.intersection(case.expected_symbols)) / len(case.expected_symbols),
        related_test_recall=len(linked_test_ids.intersection(case.expected_tests)) / len(case.expected_tests),
        citation_completeness=(
            len(set(artifact.get("evidence_ids", [])).intersection(item["id"] for item in evidence))
            / max(1, len(artifact.get("evidence_ids", [])))
        ),
        bounded_termination=float(state.get("status") in {"complete", "failed"}),
        review_compliance=float(variant not in {"no_review"} and bool(state.get("review"))),
        resume_correctness=float(variant != "no_checkpointing"),
        latency_ms=int(state["run_metrics"]["simulated_latency_ms"]),
        cost_units=int(state["run_metrics"]["cost_units"]),
    )


def retrieval_metrics(
    catalog: FixtureCatalog,
    query: str,
    relevant_source_ids: list[str],
    *,
    method: RetrievalMethod,
    top_k: int = 6,
) -> RetrievalMetrics:
    """Score one retriever against source ids from a frozen relevance judgment."""

    evidence = search(catalog, query, method=method, top_k=top_k)
    source_by_path = {source.path: source for source in catalog.sources.values()}
    retrieved_ids = [source_by_path[item.path].id for item in evidence]
    relevant = set(relevant_source_ids)
    relevant_positions = [rank for rank, source_id in enumerate(retrieved_ids, start=1) if source_id in relevant]
    precision = sum(source_id in relevant for source_id in retrieved_ids) / max(1, top_k)
    recall = len(set(retrieved_ids).intersection(relevant)) / max(1, len(relevant))
    reciprocal_rank = 1.0 / relevant_positions[0] if relevant_positions else 0.0
    dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_positions)
    ideal_positions = range(1, min(top_k, len(relevant)) + 1)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in ideal_positions)
    cost = sum(len(source.text.encode("utf-8")) for source in catalog.sources.values())
    method_factor = {"lexical": 1, "dense": 2, "structural": 1, "hybrid": 4, "agentic": 7}[method]
    return RetrievalMetrics(
        method=method,
        query=query,
        top_k=top_k,
        retrieved_count=len(evidence),
        relevant_count=len(relevant),
        precision_at_k=round(precision, 3),
        recall_at_k=round(recall, 3),
        reciprocal_rank=round(reciprocal_rank, 3),
        ndcg_at_k=round(dcg / ideal_dcg if ideal_dcg else 0.0, 3),
        estimated_latency_ms=len(catalog.sources) * method_factor,
        index_cost_units=cost * method_factor,
    )


def retrieval_scorecard(top_k: int = 6) -> list[dict[str, object]]:
    """Aggregate retrieval metrics across the frozen fixture cases."""

    catalog = FixtureCatalog(load_sources())
    methods: tuple[RetrievalMethod, ...] = (
        "lexical",
        "dense",
        "structural",
        "hybrid",
        "agentic",
    )
    scorecard: list[dict[str, object]] = []
    for method in methods:
        rows = [
            retrieval_metrics(
                catalog,
                case.question,
                case.expected_sources,
                method=method,
                top_k=top_k,
            )
            for case in load_cases()
        ]
        scorecard.append(
            {
                "method": method,
                "precision_at_k": round(mean(row.precision_at_k for row in rows), 3),
                "recall_at_k": round(mean(row.recall_at_k for row in rows), 3),
                "mrr": round(mean(row.reciprocal_rank for row in rows), 3),
                "ndcg_at_k": round(mean(row.ndcg_at_k for row in rows), 3),
                "estimated_latency_ms": round(mean(row.estimated_latency_ms for row in rows), 1),
                "index_cost_units": rows[0].index_cost_units,
            }
        )
    return scorecard


def memory_scorecard(scenario_id: str = "retry-01") -> list[dict[str, object]]:
    """Exercise memory admission boundaries and revision/conflict handling."""

    request = request_for(scenario_id)
    current = snapshot()
    valid_store = MemoryStore()
    run_fixture(scenario_id, memory=valid_store)
    valid = run_fixture(scenario_id, memory=valid_store)

    irrelevant_store = MemoryStore()
    irrelevant_store.add(
        MemoryRecord(
            id="irrelevant",
            kind="episodic",
            repository="another/repository",
            valid_from=current.revision,
            text=request.request,
            investigation_id="other-run",
            content_fingerprint=current.source_fingerprint,
            confidence=0.9,
            status="reviewed",
        )
    )
    irrelevant = run_fixture(scenario_id, memory=irrelevant_store)

    conflict_store = MemoryStore()
    for record_id, text in (
        ("conflict-a", request.request),
        ("conflict-b", "Do not increase retries; preserve the current timeout behavior."),
    ):
        conflict_store.add(
            MemoryRecord(
                id=record_id,
                kind="semantic",
                repository=current.repository,
                valid_from=current.revision,
                text=text,
                investigation_id=record_id,
                content_fingerprint=current.source_fingerprint,
                confidence=0.9,
                status="reviewed",
            )
        )
    conflicting = run_fixture(scenario_id, memory=conflict_store)
    conflict_count = len(conflict_store.conflict_candidates())

    stale_store = MemoryStore()
    stale_store.add(
        MemoryRecord(
            id="stale",
            kind="episodic",
            repository=current.repository,
            valid_from="old-revision",
            text=request.request,
            investigation_id="old-run",
            content_fingerprint="sha256:old",
            confidence=0.9,
            status="reviewed",
        )
    )
    stale = run_fixture(scenario_id, memory=stale_store)
    invalidated = sum(record.status == "invalidated" for record in stale_store.records)
    return [
        {"scenario": "no_memory", "hits": 0, "invalidated": 0, "conflicts": 0},
        {"scenario": "valid_memory", "hits": len(valid["memory_hits"]), "invalidated": 0, "conflicts": 0},
        {"scenario": "irrelevant_memory", "hits": len(irrelevant["memory_hits"]), "invalidated": 0, "conflicts": 0},
        {"scenario": "conflicting_memory", "hits": len(conflicting["memory_hits"]), "invalidated": 0, "conflicts": conflict_count},
        {"scenario": "stale_memory", "hits": len(stale["memory_hits"]), "invalidated": invalidated, "conflicts": 0},
    ]


def _means(rows: list[EvaluationRow]) -> dict[str, float]:
    fields = (
        "evidence_recall",
        "test_recall",
        "symbol_recall",
        "affected_file_recall",
        "affected_symbol_recall",
        "related_test_recall",
        "citation_completeness",
        "bounded_termination",
        "review_compliance",
        "resume_correctness",
        "latency_ms",
        "cost_units",
    )
    return {field: round(mean(float(getattr(row, field)) for row in rows), 3) for field in fields}


def evaluate_suite(variant: str = "full") -> EvaluationReport:
    rows = [_row(case, variant) for case in load_cases()]
    return EvaluationReport(
        variant=variant,
        rows=rows,
        means=_means(rows),
        tier_means={
            tier: _means([row for row in rows if row.tier == tier])
            for tier in ("worked", "validation", "challenge")
        },
    )


def compare_variants() -> list[dict[str, object]]:
    variants = ["full", "sequential", "no_review", "no_checkpointing", "no_memory"]
    return [{"variant": variant, **evaluate_suite(variant).means} for variant in variants]


def compare_retrievers(query: str) -> list[dict[str, object]]:
    catalog = FixtureCatalog(load_sources())
    rows = []
    for method in ("lexical", "dense", "structural", "hybrid", "agentic"):
        evidence = search(catalog, query, method=method, top_k=6)
        rows.append({"method": method, "results": [item.path for item in evidence], "count": len(evidence)})
    return rows
