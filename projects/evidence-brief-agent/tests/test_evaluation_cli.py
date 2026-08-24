import json
from pathlib import Path

from evidence_brief.cli import main
from evidence_brief.evaluation import evaluate_suite


def test_evaluation_covers_twelve_questions() -> None:
    report = evaluate_suite("full")
    assert len(report.rows) == 12
    assert {row.category for row in report.rows} == {
        "straightforward",
        "conflicting",
        "insufficient",
        "scope-sensitive",
    }
    assert report.means["bounded_termination"] == 1.0


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
