"""Evaluation entrypoint — score a registered version and gate promotion (docs/02).

Evaluation computes the metrics that gate promotion. It can run inline in the
train job or as a **separate eval Job** (docs/02 open decision) that loads a
candidate version by ``models:/<name>/<version>``, scores it on a held-out set,
logs metrics to its own MLflow run, and writes its own results-DB record.

The job **exits non-zero** when the candidate misses the recorded threshold, so
a downstream promotion step (docs/06) only proceeds on a passing evaluation.
"""


import argparse
import sys

import mlflow
import numpy as np
from ml_platform.common import datasets, results, schemas
from ml_platform.common.mlflow_client import configure_mlflow
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a registered version; gate promotion.")
    p.add_argument("--registered-name", default="wine-quality")
    p.add_argument("--version", required=True, help="registered version to evaluate")
    p.add_argument("--data-source", required=True, help="held-out CSV URL or path")
    p.add_argument("--delimiter", default=";")
    p.add_argument("--experiment", default="wine-quality-eval")
    p.add_argument("--target", default="quality")
    p.add_argument("--max-rmse", type=float, default=0.8, help="promotion threshold")
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--random-state", type=int, default=42)
    return p.parse_args(argv)


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
        rec["output"] = {
            "mlflow_run_id": run.info.run_id,
            "model_uri": model_uri,
            "rmse": rmse,
            "max_rmse": args.max_rmse,
            "passed": passed,
        }
        print(f"eval {model_uri}: rmse={rmse:.4f} threshold={args.max_rmse} passed={passed}")
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
