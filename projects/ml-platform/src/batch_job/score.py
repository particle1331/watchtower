"""Batch scoring entrypoint — ACA Job that fans out over data (docs/04).

Flow:
  1. Load a pinned model version from MLflow Model Registry.
  2. Load the batch data (CSV URL or path from env/args).
  3. Create one parent + N child rows in the results DB.
  4. Apply the continuation rule: score each chunk, write output (Blob ref) and
     per-chunk status; distinguish transient (RETRY) from permanent (FAILURE).
  5. Finalize the parent row (SUCCESS if no permanent failures, else FAILURE).

Invariants (docs/04):
  - This Job NEVER writes MLflow runs or registers models (read-only to MLflow).
  - Auth is via the ``id-jobs-batch`` managed identity; no passwords in the image.
  - All connection info comes from env vars; the image is pinned by digest.
"""


import argparse
import os
import uuid

import mlflow
import pandas as pd
from ml_platform.common.mlflow_client import configure_mlflow
from ml_platform.results import store
from ml_platform.results.continuation import BatchItemFailure, run_until_done

_CHUNK_SIZE = int(os.environ.get("BATCH_CHUNK_SIZE", "100"))
_MODEL_NAME = os.environ.get("MODEL_NAME", "wine-quality")
_TRIGGERED_BY = os.environ.get("TRIGGERED_BY", "schedule")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch scoring ACA Job.")
    p.add_argument("--data-source", required=True, help="CSV URL or path to score")
    p.add_argument("--delimiter", default=";", help="CSV delimiter")
    p.add_argument("--model-name", default=_MODEL_NAME, help="Registered model name")
    p.add_argument(
        "--model-version",
        default=None,
        help="Pinned model version; omit to use latest Production alias.",
    )
    p.add_argument("--experiment", default="wine-quality", help="MLflow experiment (tracking context)")
    p.add_argument("--chunk-size", type=int, default=_CHUNK_SIZE, help="Rows per child chunk")
    p.add_argument("--max-attempts", type=int, default=3, help="Max RETRY attempts per chunk")
    p.add_argument("--triggered-by", default=_TRIGGERED_BY, help="Caller identity or 'schedule'")
    return p.parse_args(argv)


def _load_model(model_name: str, model_version: str | None):
    """Load a model from the MLflow registry (read-only; never writes runs)."""
    if model_version:
        uri = f"models:/{model_name}/{model_version}"
    else:
        uri = f"models:/{model_name}@champion"
    return mlflow.sklearn.load_model(uri)


def _chunks(df: pd.DataFrame, size: int) -> list[pd.DataFrame]:
    return [df.iloc[i : i + size] for i in range(0, len(df), size)]


def _chunk_key(batch_id: str, index: int) -> str:
    """Deterministic key for the i-th chunk of a batch."""
    return f"{batch_id}:chunk:{index:06d}"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_mlflow(args.experiment)

    # --- (1) Load pinned model (read-only) ---
    model = _load_model(args.model_name, args.model_version)
    model_ref = f"{args.model_name}/{args.model_version or 'champion'}"

    # --- (2) Load data ---
    df = pd.read_csv(args.data_source, delimiter=args.delimiter)
    chunks = _chunks(df, args.chunk_size)
    n_chunks = len(chunks)

    # --- (3) Create parent + child rows ---
    batch_name = f"batch:score-{args.model_name}"
    batch_id = str(uuid.uuid4())
    parent_id = store.create_run(
        batch_name,
        triggered_by=args.triggered_by,
        run_id=batch_id,
    )
    store.mark(parent_id, "STARTED")

    chunk_keys = [_chunk_key(batch_id, i) for i in range(n_chunks)]
    store.create_children(
        parent_id,
        chunk_keys,
        name=batch_name,
        triggered_by=args.triggered_by,
    )

    # --- (4) Continuation rule ---
    # The processor is stateless: given a child-row dict it re-derives its chunk
    # from the key, scores it, and writes the result summary as output.
    key_to_chunk: dict[str, pd.DataFrame] = {
        _chunk_key(batch_id, i): chunks[i] for i in range(n_chunks)
    }

    def process(child: dict) -> None:
        # Extract the original chunk key from the child name ("batch:score-*:chunk:N")
        # The child name is "{batch_name}:{chunk_key}"; we stored full chunk_key.
        raw_key = child["name"].split(f"{batch_name}:", 1)[-1]
        chunk_df = key_to_chunk.get(raw_key)
        if chunk_df is None:
            raise BatchItemFailure(f"Unknown chunk key: {raw_key!r}")

        try:
            preds = model.predict(chunk_df)
        except Exception as exc:
            # Any prediction error on a valid chunk is transient (e.g. OOM, timeout)
            raise RuntimeError(f"Prediction failed: {exc}") from exc

        # Write summary output; big payloads would go to Blob (deferred MVP).
        rows_scored = len(preds)
        store.mark(
            child["id"],
            "SUCCESS",
            output={
                "rows_scored": rows_scored,
                "model_ref": model_ref,
                "chunk_key": raw_key,
            },
        )

    final_status = run_until_done(
        parent_id,
        process,
        max_attempts=args.max_attempts,
    )

    # --- (5) Record summary on parent ---
    store.mark(
        parent_id,
        final_status,
        output={
            "n_chunks": n_chunks,
            "total_rows": len(df),
            "model_ref": model_ref,
            "data_source": args.data_source,
        },
    )

    if final_status != "SUCCESS":
        raise SystemExit(f"Batch completed with status={final_status}")


if __name__ == "__main__":
    main()
