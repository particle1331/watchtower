"""Command-line entry point for the deterministic Change Planner fixture."""

import argparse
import json
from pathlib import Path

from change_planner.evaluation import evaluate_suite, retrieval_scorecard
from change_planner.ingestion import ingest_repository
from change_planner.schemas import ChangeRequest
from change_planner.workflow import run_fixture, run_indexed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="change-planner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--scenario", default="dry-run-01")
    run.add_argument("--root", type=Path)
    run.add_argument("--request")
    run.add_argument("--repository")
    run.add_argument("--revision")
    run.add_argument("--with-history", action="store_true")
    run.add_argument("--allow-targeted-tests", action="store_true")
    run.add_argument("--output-dir", type=Path, default=Path.cwd() / ".tmp" / "change-planner")
    evaluate = subparsers.add_parser("eval")
    evaluate.add_argument("--variant", default="full")
    index = subparsers.add_parser("index")
    index.add_argument("--root", type=Path, required=True)
    index.add_argument("--repository")
    index.add_argument("--revision")
    index.add_argument("--with-history", action="store_true")
    index.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        if args.root:
            if not args.request:
                raise SystemExit("--request is required when --root is provided")
            indexed = ingest_repository(
                args.root,
                repository=args.repository,
                revision=args.revision,
                include_history=args.with_history,
            )
            request = ChangeRequest(
                scenario_id="local",
                repository=indexed.snapshot.repository,
                revision=indexed.snapshot.revision,
                request=args.request,
                execution_policy=(
                    "allow_targeted_tests" if args.allow_targeted_tests else "read_only"
                ),
            )
            state = run_indexed(indexed, request)
        else:
            state = run_fixture(args.scenario)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "change-plan.md").write_text(state["artifact"]["markdown"], encoding="utf-8")
        (args.output_dir / "investigation.json").write_text(
            json.dumps(state, indent=2, default=str), encoding="utf-8"
        )
        print(f"wrote {args.output_dir / 'change-plan.md'}")
        print(f"wrote {args.output_dir / 'investigation.json'}")
        return 0
    if args.command == "index":
        indexed = ingest_repository(
            args.root,
            repository=args.repository,
            revision=args.revision,
            include_history=args.with_history,
        )
        payload = {
            "snapshot": indexed.snapshot.model_dump(),
            "source_count": len(indexed.catalog.sources),
            "sources": [
                {
                    "path": source.path,
                    "kind": source.source_kind,
                    "symbols": source.symbols,
                    "related_tests": source.related_tests,
                }
                for source in indexed.catalog.sources.values()
            ],
        }
        rendered = json.dumps(payload, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"wrote {args.output}")
        else:
            print(rendered)
        return 0
    report = evaluate_suite(args.variant)
    payload = report.model_dump()
    payload["retrieval_scorecard"] = retrieval_scorecard()
    print(json.dumps(payload, indent=2))
    return 0
