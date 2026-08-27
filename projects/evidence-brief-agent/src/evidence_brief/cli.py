"""Command-line entry points for fixture runs and evaluation."""

import argparse
import json
from pathlib import Path
from typing import Any

from evidence_brief.evaluation import evaluate_suite
from evidence_brief.workflow import run_fixture


def _default_output() -> Path:
    return Path.cwd() / ".tmp" / "evidence-brief"


def _write_run(state: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    question_id = str(state["request"]["question_id"])
    markdown_path = output_dir / f"{question_id}.md"
    json_path = output_dir / f"{question_id}.json"
    markdown_path.write_text(state["artifact"]["markdown"] + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return markdown_path, json_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence-brief", description="Run the Philippine legal-research fixture agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--question-id", default="conflict-01")
    run.add_argument("--output-dir", type=Path, default=_default_output())
    evaluate = subparsers.add_parser("eval")
    evaluate.add_argument(
        "--variant",
        choices=("full", "skill_baseline", "sequential", "no_review", "no_reconciliation", "no_checkpointing"),
        default="full",
    )
    evaluate.add_argument("--output-dir", type=Path, default=_default_output())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        markdown_path, json_path = _write_run(run_fixture(args.question_id), args.output_dir)
        print(markdown_path)
        print(json_path)
        return 0
    report = evaluate_suite(args.variant)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"evaluation-{args.variant}.json"
    output_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
