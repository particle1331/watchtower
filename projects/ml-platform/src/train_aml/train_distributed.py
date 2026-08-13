"""Distributed training entrypoint for Azure ML command jobs (docs/08).

This script runs on an AML compute cluster under our own container image.
Lineage and model identity are exactly the same as the ACA training job
(docs/02): dataset digest, code image digest, params, metrics, and a
registered version in the **self-hosted** MLflow — not AML managed MLflow.

Usage (submitted via AML SDK or job.yml):
    python train_distributed.py --data-source <url-or-path> ...

The script detects the local rank (torch.distributed) and only one process
(rank 0) writes to MLflow and the results DB, to avoid concurrent writes.
"""


import argparse
import os

import mlflow
import numpy as np
from ml_platform.common import datasets, results, schemas
from ml_platform.common.mlflow_client import configure_mlflow
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split

DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/mlflow/mlflow/master/"
    "tests/datasets/winequality-white.csv"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Distributed training via AML command job.")
    p.add_argument("--data-source", default=DEFAULT_SOURCE)
    p.add_argument("--delimiter", default=";")
    p.add_argument("--experiment", default="wine-quality-aml")
    p.add_argument("--registered-name", default="wine-quality")
    p.add_argument("--dataset-name", default="wine-quality-white")
    p.add_argument("--target", default="quality")
    p.add_argument("--alpha", type=float, default=0.5)
    p.add_argument("--l1-ratio", type=float, default=0.5)
    p.add_argument("--test-size", type=float, default=0.25)
    p.add_argument("--random-state", type=int, default=42)
    return p.parse_args(argv)


def _local_rank() -> int:
    """Return the local process rank (0 on single-node runs)."""
    return int(os.environ.get("LOCAL_RANK", os.environ.get("OMPI_COMM_WORLD_LOCAL_RANK", "0")))


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    is_primary = _local_rank() == 0

    # Only rank-0 drives MLflow + results DB writes.
    if is_primary:
        configure_mlflow(args.experiment)

    raw = datasets.load_csv(args.data_source, delimiter=args.delimiter)
    raw = schemas.validate(raw)
    dataset = datasets.tracked_dataset(
        raw, source=args.data_source, name=args.dataset_name, targets=args.target
    )

    features = raw.drop(columns=[args.target])
    target = raw[args.target]
    x_train, x_test, y_train, y_test = train_test_split(
        features, target, test_size=args.test_size, random_state=args.random_state
    )

    # In a real distributed run, each rank trains on its data shard and
    # collective communication averages gradients (e.g. torch DDP). Here we
    # show the structure: all ranks train, only rank-0 logs + registers.
    model = ElasticNet(alpha=args.alpha, l1_ratio=args.l1_ratio, random_state=args.random_state)
    model.fit(x_train, y_train)

    if is_primary:
        preds = model.predict(x_test)
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        image_digest = os.environ.get("IMAGE_DIGEST", "unknown")

        with results.record_run(f"train:{args.registered_name}") as rec, mlflow.start_run() as _run:
            mlflow.log_input(dataset, context="training")
            mlflow.log_params({"alpha": args.alpha, "l1_ratio": args.l1_ratio})
            mlflow.set_tag("code.image_digest", image_digest)
            mlflow.set_tag("training.backend", "aml-distributed")
            mlflow.log_metric("rmse", rmse)
            mlflow.sklearn.log_model(
                model,
                name="model",
                registered_model_name=args.registered_name,
            )
            rec["rmse"] = rmse
            rec["image_digest"] = image_digest


if __name__ == "__main__":
    main()
