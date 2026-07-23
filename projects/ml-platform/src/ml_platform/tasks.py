"""Celery tasks for batch inference with idempotency and retry.

Core task: process_document — the batch inference worker.
Reconciliation: reconcile_documents — Celery Beat schedule that recovers
    queue state lost to Redis restarts.
"""

import logging
import time
from typing import Any

from ml_platform.celeryconfig import app
from ml_platform.idempotency import idempotency_guard, make_idempotency_key

logger = logging.getLogger(__name__)

# The current task contract version. Incremented when the task signature,
# model input format, or output schema changes incompatibly.
TASK_CONTRACT_VERSION = 1

# Release identifier — set at build/deploy time.
RELEASE_ID = "dev"


@app.task(
    bind=True,
    acks_late=True,
    task_reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def process_document(
    self,
    doc_id: str,
    doc_content: str,
    model_version: str,
    prompt_version: str,
    contract_version: int,
    release_id: str,
) -> dict[str, Any]:
    """Process a single document through the inference pipeline.

    Idempotency key is derived from doc_id + contract_version. Duplicate
    deliveries are skipped — no double OpenAI call, no double side effect.

    Args:
        doc_id: Immutable document identifier (Blob path or DB primary key).
        doc_content: The raw document text/content to process.
        model_version: Exact MLflow model version to use (not alias).
        prompt_version: Exact MLflow prompt version to use (not alias).
        contract_version: Task contract version this payload conforms to.
        release_id: Deploy release identifier for audit.

    Returns:
        Processing result with trace metadata.
    """
    if contract_version != TASK_CONTRACT_VERSION:
        logger.warning(
            "Rejecting unsupported task contract: got %s, expected %s",
            contract_version,
            TASK_CONTRACT_VERSION,
        )
        return {"status": "rejected", "reason": f"contract {contract_version} != {TASK_CONTRACT_VERSION}"}

    idem_key = make_idempotency_key(doc_id, contract_version)

    with idempotency_guard(idem_key) as should_process:
        if not should_process:
            logger.info("Duplicate delivery for doc=%s — skipping", doc_id)
            return {"status": "skipped", "reason": "duplicate", "doc_id": doc_id}

        logger.info(
            "Processing doc=%s model=%s prompt=%s release=%s",
            doc_id,
            model_version,
            prompt_version,
            release_id,
        )

        start = time.monotonic()

        result = _run_inference(doc_content, model_version, prompt_version)

        elapsed_ms = (time.monotonic() - start) * 1000

        output = {
            "status": "completed",
            "doc_id": doc_id,
            "model_version": model_version,
            "prompt_version": prompt_version,
            "contract_version": contract_version,
            "release_id": release_id,
            "elapsed_ms": round(elapsed_ms, 2),
            "result": result,
        }
        logger.info("Completed doc=%s in %.2fms", doc_id, elapsed_ms)
        return output


def _run_inference(
    doc_content: str,
    model_version: str,
    prompt_version: str,
) -> str:
    """Stub inference — replace with actual model/LLM call.

    In production this would:
    1. Load the MLflow model by version.
    2. Load the MLflow prompt by version.
    3. Call Azure OpenAI with the prompt + document content.
    4. Post-process the response.
    """
    # TODO: load model and prompt from MLflow registry
    # model = mlflow.pyfunc.load_model(f"models:/my-model/{model_version}")
    # prompt = mlflow.prompts.load_prompt(f"prompts:/my-prompt/{prompt_version}")

    # Stub: return a simulated result
    words = len(doc_content.split())
    return f"Inference complete: {words} words processed (model={model_version}, prompt={prompt_version})"


@app.task(
    bind=True,
    acks_late=True,
)
def reconcile_documents(self) -> dict[str, Any]:
    """Celery Beat reconciliation task.

    Scans the document store for records without a completed status,
    diffs them against Redis result keys, and republishes missing work
    with the same idempotency key. Recovers queue state lost to Redis
    restarts without manual intervention.

    This runs on a schedule (default: every 5 minutes) and is safe because:
    1. Each document gets a stable idempotency key.
    2. process_document skips duplicates via the idempotency guard.
    3. The reconciliation window matches the idempotency TTL (7 days).
    """
    logger.info("Reconciliation scan starting")

    # TODO: query the document store for unprocessed documents
    # docs = get_unprocessed_documents()
    # for doc in docs:
    #     idem_key = make_idempotency_key(doc.id, TASK_CONTRACT_VERSION)
    #     if not is_duplicate(idem_key):
    #         process_document.delay(
    #             doc_id=doc.id,
    #             doc_content=doc.content,
    #             model_version=doc.model_version,
    #             prompt_version=doc.prompt_version,
    #             contract_version=TASK_CONTRACT_VERSION,
    #             release_id=RELEASE_ID,
    #         )

    logger.info("Reconciliation scan complete")
    return {"status": "ok", "reconciled": 0, "skipped": 0}
