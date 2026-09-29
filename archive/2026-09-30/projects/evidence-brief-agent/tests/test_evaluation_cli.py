import json
from pathlib import Path

from evidence_brief.cli import main
from evidence_brief.evaluation import evaluate_suite
from evidence_brief.fixtures import load_public_bar_records, load_questions
from evidence_brief.schemas import EvaluationCase


def test_evaluation_covers_twelve_questions() -> None:
    report = evaluate_suite("full")
    assert len(report.rows) == 12
    assert {row.category for row in report.rows} == {
        "straightforward",
        "qualified",
        "insufficient",
        "scope-sensitive",
    }
    assert report.means["bounded_termination"] == 1.0
    assert report.means["counterfactual_pair_consistency"] == 1.0
    assert {row.tier for row in report.rows} == {"worked", "validation", "challenge"}
    assert all(len([row for row in report.rows if row.tier == tier]) == 4 for tier in report.tier_means)


def test_counterfactual_pairs_change_one_decisive_fact_and_flip_the_oracle() -> None:
    pairs: dict[str, list[EvaluationCase]] = {}
    for case in load_questions():
        pairs.setdefault(case.pair_id, []).append(case)
    assert len(pairs) == 6
    for pair in pairs.values():
        assert len(pair) == 2
        left, right = pair
        assert left.expected_recommendation != right.expected_recommendation
        left_facts = left.facts.model_dump()
        right_facts = right.facts.model_dump()
        assert sum(left_facts[key] != right_facts[key] for key in left_facts) == 1


def test_public_bar_records_are_metadata_only_and_excluded_from_scoring() -> None:
    records = load_public_bar_records()
    assert records
    assert all(record.contamination_risk == "high" for record in records)
    assert all(not record.answer_text_in_repo for record in records)
    assert all(not record.eligible_for_scoring for record in records)
    report = evaluate_suite("full")
    assert report.public_bar_regression.score_eligible == 0
    assert report.public_bar_regression.blocked_records == len(records)


def test_ablations_expose_their_missing_contracts() -> None:
    assert evaluate_suite("no_review").means["review_compliance"] == 0.0
    assert evaluate_suite("no_checkpointing").means["resume_correctness"] == 0.0
    assert evaluate_suite("no_reconciliation").means["contradiction_detection"] < 1.0


def test_cli_writes_markdown_json_and_evaluation(tmp_path: Path) -> None:
    assert main(["run", "--question-id", "conflict-01", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "conflict-01.md").exists()
    state = json.loads((tmp_path / "conflict-01.json").read_text())
    assert state["status"] == "complete"
    assert main(["eval", "--variant", "full", "--output-dir", str(tmp_path)]) == 0
    assert (tmp_path / "evaluation-full.json").exists()
