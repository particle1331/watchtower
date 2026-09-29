from typing import cast

from change_planner.evaluation import (
    compare_retrievers,
    compare_variants,
    evaluate_suite,
    retrieval_metrics,
    retrieval_scorecard,
)
from change_planner.fixtures import load_cases, load_sources
from change_planner.retrieval import FixtureCatalog


def test_evaluation_reports_all_fixture_cases() -> None:
    report = evaluate_suite()

    assert len(report.rows) == 4
    assert report.means["evidence_recall"] == 1.0
    assert report.means["affected_file_recall"] == 1.0
    assert report.means["affected_symbol_recall"] == 1.0
    assert report.means["related_test_recall"] == 1.0
    assert report.means["review_compliance"] == 1.0


def test_variants_expose_parallelism_and_removed_contracts() -> None:
    variants = {row["variant"]: row for row in compare_variants()}

    full_latency = cast(float, variants["full"]["latency_ms"])
    sequential_latency = cast(float, variants["sequential"]["latency_ms"])
    assert full_latency < sequential_latency
    assert sequential_latency > full_latency
    assert variants["no_review"]["review_compliance"] == 0.0
    assert variants["no_memory"]["resume_correctness"] == 1.0


def test_retriever_comparison_keeps_method_names_visible() -> None:
    rows = compare_retrievers("timeout retry duplicate write")

    assert [row["method"] for row in rows] == ["lexical", "dense", "structural", "hybrid", "agentic"]


def test_retrieval_metrics_report_rank_quality_and_cost() -> None:
    case = load_cases()[0]
    row = retrieval_metrics(
        FixtureCatalog(load_sources()),
        case.question,
        case.expected_sources,
        method="hybrid",
    )

    assert row.retrieved_count > 0
    assert 0.0 <= row.precision_at_k <= 1.0
    assert 0.0 <= row.recall_at_k <= 1.0
    assert row.reciprocal_rank > 0.0
    assert row.index_cost_units > 0


def test_retrieval_scorecard_aggregates_all_methods() -> None:
    rows = retrieval_scorecard()

    assert [row["method"] for row in rows] == ["lexical", "dense", "structural", "hybrid", "agentic"]
    assert all(cast(float, row["ndcg_at_k"]) >= 0.0 for row in rows)
