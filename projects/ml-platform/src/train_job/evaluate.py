"""Evaluation entrypoint: score an exact registered version and gate promotion.

The separate eval Job loads a candidate by ``models:/<name>/<version>``, scores
it on a held-out set, logs metrics to its own MLflow run, and writes its own
results-DB record.

The job **exits non-zero** when the candidate misses the recorded threshold, so
the promotion entrypoint only proceeds on a passing evaluation.
"""

import argparse
import os
import sys

import mlflow
import numpy as np
from ml_platform.common import datasets, results, schemas
from ml_platform.common.mlflow_client import configure_mlflow
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split


class EvaluationGateFailed(RuntimeError):
    """Raised inside run contexts so a rejected candidate is recorded as failed."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a registered version; gate promotion.")
    p.add_argument(
        "--registered-name",
        default=os.environ.get("MODEL_NAME", "wine-quality"),
    )
    p.add_argument(
        "--version",
        default=os.environ.get("MODEL_VERSION"),
        help="registered version to evaluate; defaults to MODEL_VERSION",
    )
    p.add_argument(
        "--data-source",
        default=os.environ.get("DATA_SOURCE"),
        help="held-out CSV URL or path; defaults to DATA_SOURCE",
    )
    p.add_argument("--delimiter", default=";")
    p.add_argument("--experiment", default="wine-quality-eval")
    p.add_argument("--target", default="quality")
    p.add_argument(
        "--max-rmse",
        type=float,
        default=float(os.environ.get("EVAL_MAX_RMSE", "0.8")),
        help="promotion threshold; defaults to EVAL_MAX_RMSE or 0.8",
    )
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--random-state", type=int, default=42)
    args = p.parse_args(argv)
    if not args.version:
        p.error("--version or MODEL_VERSION is required")
    if not args.data_source:
        p.error("--data-source or DATA_SOURCE is required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_mlflow(args.experiment)

    raw = schemas.validate(datasets.load_csv(args.data_source, delimiter=args.delimiter))
    features = raw.drop(columns=[args.target])
    target = raw[args.target]
    _, x_test, _, y_test = train_test_split(
        features, target, test_size=args.test_size, random_state=args.random_state
    )

    model_uri = f"models:/{args.registered_name}/{args.version}"
    # pyfunc keeps evaluation on the same loading contract as serving and
    # batch scoring while preserving the tabular DataFrame input here.
    model = mlflow.pyfunc.load_model(model_uri)

    try:
        with results.record_run(f"eval:{args.registered_name}") as rec, mlflow.start_run() as run:
            preds = model.predict(x_test)
            rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
            passed = rmse <= args.max_rmse
            mlflow.log_metric("rmse", rmse)
            mlflow.set_tags(
                {
                    "eval.model_uri": model_uri,
                    "eval.max_rmse": args.max_rmse,
                    "eval.passed": str(passed),
                }
            )
            rec.update(
                {
                    "mlflow_run_id": run.info.run_id,
                    "model_uri": model_uri,
                    "rmse": rmse,
                    "max_rmse": args.max_rmse,
                    "passed": passed,
                }
            )
            print(f"eval {model_uri}: rmse={rmse:.4f} threshold={args.max_rmse} passed={passed}")
            if not passed:
                raise EvaluationGateFailed(
                    f"Evaluation gate failed: rmse {rmse:.4f} > {args.max_rmse:.4f}"
                )
    except EvaluationGateFailed as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
