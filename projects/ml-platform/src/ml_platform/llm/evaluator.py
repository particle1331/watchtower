"""LLM evaluator — scores a candidate pyfunc version against a fixed eval set (docs/03).

The evaluator runs as an ACA Job bound to ``id-jobs-train``. It:
  1. Loads the candidate ``models:/<name>/<version>`` (pyfunc).
  2. Runs predictions on every row in the eval JSONL file.
  3. Computes per-row and aggregate metrics (exact_match, latency, token counts).
  4. Logs all metrics + the eval dataset to the MLflow run.
  5. Applies a threshold gate: exits non-zero if any required metric misses.
  6. Writes a results-DB record via ``record_run`` so the dashboard sees it.

Eval JSONL format (one JSON object per line):
  ``{"input": "...", "expected": "..."}``
  ``expected`` may be omitted if only latency/token metrics are needed.
"""


import argparse
import json
import time
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

from ml_platform.common.mlflow_client import configure_mlflow
from ml_platform.common.results import record_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a pyfunc LLM version.")
    p.add_argument("--model-name", required=True, help="Registered model name")
    p.add_argument("--model-version", required=True, help="Version to evaluate")
    p.add_argument("--eval-dataset", required=True, help="Path or URL to eval JSONL file")
    p.add_argument("--experiment", default="llm-eval", help="MLflow experiment name")
    p.add_argument(
        "--min-exact-match",
        type=float,
        default=0.0,
        help="Minimum exact_match fraction required to pass (0–1); 0 = skip gate",
    )
    p.add_argument(
        "--max-avg-tokens",
        type=float,
        default=0.0,
        help="Maximum average completion_tokens allowed; 0 = skip gate",
    )
    return p.parse_args(argv)


def load_eval_dataset(path: str) -> list[dict[str, Any]]:
    if path.startswith("http://") or path.startswith("https://"):
        import httpx
        rows = [json.loads(line) for line in httpx.get(path).text.splitlines() if line.strip()]
    else:
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"Eval dataset is empty: {path!r}")
    return rows


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_mlflow(args.experiment)

    model_uri = f"models:/{args.model_name}/{args.model_version}"
    run_name = f"eval:{args.model_name}/{args.model_version}"

    with record_run(run_name) as rec, mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "model_name": args.model_name,
            "model_version": args.model_version,
            "eval_dataset": args.eval_dataset,
        })

        # (1) Load candidate version.
        model = mlflow.pyfunc.load_model(model_uri)

        # (2) Load eval dataset.
        rows = load_eval_dataset(args.eval_dataset)
        inputs = pd.DataFrame([{"input": r["input"]} for r in rows])
        expected = [r.get("expected") for r in rows]

        # (3) Run predictions with latency measurement.
        t0 = time.perf_counter()
        preds_df: pd.DataFrame = model.predict(inputs)
        elapsed = time.perf_counter() - t0

        predictions = preds_df["content"].tolist()
        prompt_tokens = preds_df["prompt_tokens"].tolist()
        completion_tokens = preds_df["completion_tokens"].tolist()

        # (4) Compute metrics.
        n = len(rows)
        avg_latency = elapsed / n
        avg_prompt_tokens = sum(prompt_tokens) / n
        avg_completion_tokens = sum(completion_tokens) / n

        exact_matches = sum(
            1 for pred, exp in zip(predictions, expected, strict=True)
            if exp is not None and pred.strip() == str(exp).strip()
        )
        n_with_expected = sum(1 for e in expected if e is not None)
        exact_match_frac = exact_matches / n_with_expected if n_with_expected > 0 else 0.0

        metrics = {
            "exact_match": exact_match_frac,
            "n_samples": n,
            "avg_latency_s": avg_latency,
            "avg_prompt_tokens": avg_prompt_tokens,
            "avg_completion_tokens": avg_completion_tokens,
        }
        mlflow.log_metrics(metrics)

        # Log the eval dataset + per-row results as artifacts.
        results_df = inputs.copy()
        results_df["prediction"] = predictions
        results_df["expected"] = expected
        results_df["exact_match"] = [
            pred.strip() == str(exp).strip() if exp is not None else None
            for pred, exp in zip(predictions, expected, strict=True)
        ]
        results_path = "/tmp/eval_results.csv"  # noqa: S108
        results_df.to_csv(results_path, index=False)
        mlflow.log_artifact(results_path, artifact_path="eval")

        # (5) Threshold gate.
        failures = []
        if args.min_exact_match > 0 and exact_match_frac < args.min_exact_match:
            failures.append(
                f"exact_match {exact_match_frac:.3f} < required {args.min_exact_match:.3f}"
            )
        if args.max_avg_tokens > 0 and avg_completion_tokens > args.max_avg_tokens:
            failures.append(
                f"avg_completion_tokens {avg_completion_tokens:.1f} > max {args.max_avg_tokens:.1f}"
            )

        rec.update(metrics)

        if failures:
            msg = "; ".join(failures)
            mlflow.set_tag("gate_result", "FAIL")
            mlflow.set_tag("gate_failures", msg)
            raise SystemExit(f"Evaluation gate failed: {msg}")

        mlflow.set_tag("gate_result", "PASS")


if __name__ == "__main__":
    main()
