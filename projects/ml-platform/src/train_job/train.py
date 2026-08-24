"""Training entrypoint — ACA Job that produces a registered model version.

Flow:
  1. Load the source data and validate it at the boundary (Pandera).
  2. Build an MLflow-tracked dataset (source + content digest + schema).
  3. Start an MLflow run; log the dataset, params, and the code image digest.
  4. Train + evaluate on a held-out split; log metrics and the model.
  5. Register the model as a new version, and write a results-DB record whose
     `output` carries the MLflow run id and registered version.

Run as the `id-jobs-train` managed identity; all connection info comes from env
(no secrets in the image). Reproducible because the image is pinned and the
dataset's source + digest are logged: same image + same dataset + same params
=> equivalent registered version.
"""


import argparse
import os

import mlflow
import numpy as np
from ml_platform.common import datasets, results, schemas
from ml_platform.common.mlflow_client import configure_mlflow
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

# The runnable demonstration uses the UCI white wine-quality dataset.
DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/mlflow/mlflow/master/"
    "tests/datasets/winequality-white.csv"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train + register a model as an ACA Job.")
    p.add_argument("--data-source", default=DEFAULT_SOURCE, help="CSV URL or path")
    p.add_argument("--delimiter", default=";", help="CSV delimiter (wine-quality uses ';')")
    p.add_argument("--experiment", default="wine-quality", help="MLflow experiment name")
    p.add_argument("--registered-name", default="wine-quality", help="registered model name")
    p.add_argument("--dataset-name", default="wine-quality-white", help="tracked dataset name")
    p.add_argument("--target", default="quality", help="target column")
    p.add_argument("--alpha", type=float, default=0.5, help="ElasticNet alpha")
    p.add_argument("--l1-ratio", type=float, default=0.5, help="ElasticNet l1_ratio")
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--random-state", type=int, default=42)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_mlflow(args.experiment)

    # (1) Load + validate at the boundary — bad data fails the run early.
    raw = datasets.load_csv(args.data_source, delimiter=args.delimiter)
    raw = schemas.validate(raw)

    # (2) Track the exact data consumed (source + digest + schema).
    dataset = datasets.tracked_dataset(
        raw, source=args.data_source, name=args.dataset_name, targets=args.target
    )

    features = raw.drop(columns=[args.target])
    target = raw[args.target]
    x_train, x_test, y_train, y_test = train_test_split(
        features, target, test_size=args.test_size, random_state=args.random_state
    )

    image_digest = os.environ.get("IMAGE_DIGEST", "unknown")

    with results.record_run(f"train:{args.registered_name}") as rec, mlflow.start_run() as run:
        # (3) Lineage: dataset, params, code image digest.
        mlflow.log_input(dataset, context="training")
        mlflow.log_params({"alpha": args.alpha, "l1_ratio": args.l1_ratio})
        mlflow.set_tag("code.image_digest", image_digest)

        # (4) Train + evaluate on the held-out split.
        model = ElasticNet(
            alpha=args.alpha, l1_ratio=args.l1_ratio, random_state=args.random_state
        )
        model.fit(x_train, y_train)
        preds = model.predict(x_test)
        metrics = {
            "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
            "mae": float(mean_absolute_error(y_test, preds)),
            "r2": float(r2_score(y_test, preds)),
        }
        mlflow.log_metrics(metrics)

        # (5) Register the model as a new version.
        info = mlflow.sklearn.log_model(
            model, name="model", registered_model_name=args.registered_name
        )
        version = _registered_version(args.registered_name, run.info.run_id)

        rec["output"] = {
            "mlflow_run_id": run.info.run_id,
            "registered_model": args.registered_name,
            "registered_version": version,
            "model_uri": info.model_uri,
            "metrics": metrics,
        }
        print(
            f"registered {args.registered_name} v{version} "
            f"(run {run.info.run_id}) rmse={metrics['rmse']:.4f}"
        )


def _registered_version(name: str, run_id: str) -> str | None:
    """Resolve the version just registered for this run (best-effort)."""
    from mlflow import MlflowClient

    client = MlflowClient()
    versions = client.search_model_versions(f"name = '{name}' and run_id = '{run_id}'")
    return versions[0].version if versions else None


if __name__ == "__main__":
    main()
