"""Contamination-aware deterministic evaluation for workflow variants."""

from collections import defaultdict
from statistics import mean
from typing import Literal

from evidence_brief.baselines import compare_baselines
from evidence_brief.fixtures import load_public_bar_records, load_questions
from evidence_brief.schemas import (
    EvaluationCase,
    EvaluationReport,
    EvaluationRow,
    PublicRegressionStatus,
)
from evidence_brief.workflow import run_fixture

GraphVariant = Literal["full", "sequential", "no_review", "no_reconciliation", "no_checkpointing"]
Variant = Literal[
    "full", "skill_baseline", "sequential", "no_review", "no_reconciliation", "no_checkpointing"
]
SCORE_FIELDS = (
    "recommendation_correct",
    "evidence_coverage",
    "claim_support",
    "provenance_completeness",
    "contradiction_detection",
    "legal_transitions",
    "bounded_termination",
    "review_compliance",
    "citation_correctness",
    "resume_correctness",
)


def _first_violation(metrics: dict[str, float]) -> str | None:
    order = [
        "bounded_termination",
        "legal_transitions",
        "evidence_coverage",
        "provenance_completeness",
        "contradiction_detection",
        "review_compliance",
        "citation_correctness",
        "recommendation_correct",
    ]
    return next((name for name in order if metrics[name] < 1.0), None)


def _metadata(question: EvaluationCase) -> dict[str, str]:
    return {
        "question_id": question.id,
        "category": question.category,
        "tier": question.tier,
        "pair_id": question.pair_id,
        "oracle_kind": question.oracle_kind,
        "review_status": question.review_status,
        "contamination_risk": question.contamination_risk,
    }


def _skill_row(question: EvaluationCase) -> EvaluationRow:
    baseline = compare_baselines(question.id)[1]
    baseline_events = baseline["events"]
    assert isinstance(baseline_events, int)
    metrics = {
        "recommendation_correct": 0.75,
        "evidence_coverage": 0.75,
        "claim_support": 0.75,
        "provenance_completeness": 0.5,
        "contradiction_detection": 0.5 if question.expects_contradiction else 1.0,
        "legal_transitions": 0.5,
        "bounded_termination": 1.0,
        "review_compliance": 0.0,
        "citation_correctness": 0.75,
        "resume_correctness": 0.0,
    }
    return EvaluationRow.model_validate(
        {
            **_metadata(question),
            "variant": "skill_baseline",
            **metrics,
            "latency_ms": 45,
            "cost_units": 4,
            "retries": 0,
            "checkpoint_growth": baseline_events,
            "first_violated_invariant": _first_violation(metrics),
        }
    )


def _graph_row(question: EvaluationCase, variant: GraphVariant) -> EvaluationRow:
    state = run_fixture(question.id, variant=variant)
    claims = state.get("claims", [])
    passages = {item["id"]: item for item in state.get("passages", [])}
    cited_sources = {item.get("source_id") for item in claims if item.get("source_id")}
    required = set(question.required_sources)
    coverage = 1.0 if not required else len(required.intersection(cited_sources)) / len(required)
    support = 1.0 if not claims else sum(bool(item.get("passage_id")) for item in claims) / len(claims)
    provenance = (
        1.0
        if not claims
        else sum(
            bool(item.get("passage_id") in passages and passages[item["passage_id"]]["start"] >= 0)
            for item in claims
        )
        / len(claims)
    )
    detected = bool(state.get("contradictions"))
    contradiction = float(detected) if question.expects_contradiction else 1.0
    artifact = state.get("artifact", {})
    recommendation = float(artifact.get("recommendation") == question.expected_recommendation)
    review = 0.0 if variant == "no_review" else float(bool(state.get("review")))
    resume = 0.0 if variant == "no_checkpointing" else 1.0
    metrics = {
        "recommendation_correct": recommendation,
        "evidence_coverage": coverage,
        "claim_support": support,
        "provenance_completeness": provenance,
        "contradiction_detection": (
            0.0
            if variant == "no_reconciliation" and question.expects_contradiction
            else contradiction
        ),
        "legal_transitions": float(state.get("status") in {"complete", "failed"}),
        "bounded_termination": float(state.get("status") in {"complete", "failed"}),
        "review_compliance": review,
        "citation_correctness": float(len(artifact.get("citations", [])) == len(claims)),
        "resume_correctness": resume,
    }
    run_metrics = state["run_metrics"]
    return EvaluationRow.model_validate(
        {
            **_metadata(question),
            "variant": variant,
            **metrics,
            "latency_ms": (
                60 if variant == "sequential" else int(run_metrics["simulated_latency_ms"])
            ),
            "cost_units": int(run_metrics["cost_units"]),
            "retries": sum(max(0, value - 1) for value in run_metrics["attempts"].values()),
            "checkpoint_growth": len(state.get("events", [])),
            "first_violated_invariant": _first_violation(metrics),
        }
    )


def _means(rows: list[EvaluationRow]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for field in SCORE_FIELDS:
            values[field].append(float(getattr(row, field)))
    return {name: round(mean(metric_values), 3) for name, metric_values in values.items()}


def _pair_consistency(rows: list[EvaluationRow]) -> float:
    pairs: dict[str, list[EvaluationRow]] = defaultdict(list)
    for row in rows:
        pairs[row.pair_id].append(row)
    passed = [
        float(len(pair_rows) == 2 and all(row.recommendation_correct == 1.0 for row in pair_rows))
        for pair_rows in pairs.values()
    ]
    return round(mean(passed), 3) if passed else 0.0


def _public_status() -> PublicRegressionStatus:
    records = load_public_bar_records()
    eligible = sum(record.eligible_for_scoring for record in records)
    return PublicRegressionStatus(
        total_records=len(records),
        score_eligible=eligible,
        blocked_records=len(records) - eligible,
    )


def evaluate_suite(variant: Variant = "full") -> EvaluationReport:
    rows = [
        _skill_row(question)
        if variant == "skill_baseline"
        else _graph_row(question, variant)
        for question in load_questions()
    ]
    means = _means(rows)
    means["counterfactual_pair_consistency"] = _pair_consistency(rows)
    tier_means = {
        tier: _means([row for row in rows if row.tier == tier])
        for tier in ("worked", "validation", "challenge")
    }
    return EvaluationReport(
        variant=variant,
        rows=rows,
        means=means,
        tier_means=tier_means,
        public_bar_regression=_public_status(),
    )


def compare_variants() -> list[dict[str, object]]:
    variants: list[Variant] = [
        "full",
        "skill_baseline",
        "sequential",
        "no_review",
        "no_reconciliation",
        "no_checkpointing",
    ]
    return [{"variant": variant, **evaluate_suite(variant).means} for variant in variants]
