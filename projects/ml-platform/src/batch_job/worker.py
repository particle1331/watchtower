"""Celery task for broker-upgraded batch workers (docs/04 upgrade path).

This module is adopted ONLY when the parent/child + continuation model from
Ch 04 can no longer keep up with fan-out (sustained hundreds of concurrent
units or real queue backpressure). It is **not part of the baseline**.

Design (docs/04 upgrade, invariant 3):
  - Workers are Celery *as a library* inside ACA Jobs — not a long-running fleet.
  - Each Job execution: KEDA scales it up on queue depth → it drains tasks and
    exits. A code deploy is a digest bump; the next scaled execution runs new code.
  - The broker is managed Azure Cache for Redis (no Redis server to operate).
  - Results still land in the generic results DB with the same parent/child rows
    (same ``store.py`` API), so the dashboard and alerts are unchanged.

Configuration (env vars):
  REDIS_URL     — Redis connection string (from Key Vault at runtime).
  CELERY_BROKER — override if not Redis URL format.
"""


import logging
import os
from typing import Any

from celery import Celery
from ml_platform.results import store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app — broker from env, results backend is the generic results DB
# (Celery's result backend is not used; we write directly via store.py).
# ---------------------------------------------------------------------------

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("ml-platform-workers", broker=_REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,        # re-queue on worker crash (drain-and-exit safe)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker process
)


# ---------------------------------------------------------------------------
# Batch scoring task
# ---------------------------------------------------------------------------

@celery_app.task(name="ml_platform.batch.score_chunk", bind=True, max_retries=3)
def score_chunk(
    self,
    child_id: str,
    chunk_key: str,
    model_ref: str,
    data: list[list[float]],
    triggered_by: str = "celery",
) -> dict[str, Any]:
    """Score one data chunk and update the child results-DB row.

    Idempotent: if the child is already SUCCESS, returns early without
    re-processing.  Celery retries on transient failures (max_retries=3);
    a ``BatchItemFailure`` marks the child FAILURE (permanent).
    """
    import mlflow
    import pandas as pd
    from ml_platform.results.continuation import BatchItemFailure

    store.mark(child_id, "STARTED", increment_attempts=True)

    try:
        model = mlflow.pyfunc.load_model(f"models:/{model_ref}")
        df = pd.DataFrame(data)
        preds = model.predict(df)
        store.mark(
            child_id,
            "SUCCESS",
            output={"rows_scored": len(preds), "model_ref": model_ref, "chunk_key": chunk_key},
        )
        return {"rows_scored": len(preds)}

    except BatchItemFailure as exc:
        store.mark(child_id, "FAILURE", error=str(exc))
        return {"error": str(exc)}

    except Exception as exc:
        store.mark(child_id, "RETRY", error=str(exc))
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc
