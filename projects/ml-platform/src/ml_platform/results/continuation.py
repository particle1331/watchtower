"""Stateless continuation rule for batch workflows (docs/04).

"Run until done" without an orchestration engine: all per-item state lives in the
results DB, so a batch Job (or a cron sweeper) can re-evaluate this rule after a
crash and pick up exactly where it left off.

Rule (applied in a loop):
    1. Fetch children still in PENDING/RETRY with attempts < max_attempts.
    2. Process each one (idempotently).
    3. If no items were processed (no progress), circuit-break.
    4. Stop when no eligible children remain.
    5. Mark the parent SUCCESS or FAILURE via ``finalize_parent``.

Usage::

    from ml_platform.results.continuation import run_until_done
    from ml_platform.results import store

    parent_id = store.create_run("batch:score-fraud", triggered_by=triggered_by)
    store.create_children(parent_id, item_keys, name="batch:score-fraud", triggered_by=triggered_by)
    store.mark(parent_id, "STARTED")

    def process(child: dict) -> None:
        ...  # raises on transient error, raises BatchItemFailure on permanent error

    final = run_until_done(parent_id, process)
"""


import logging
from collections.abc import Callable
from typing import Any

from ml_platform.results import store

log = logging.getLogger(__name__)


class BatchItemFailure(Exception):
    """Raise inside a processor to mark the item FAILURE (permanent, not retried)."""


def run_until_done(
    parent_id: str,
    processor: Callable[[dict[str, Any]], None],
    *,
    max_attempts: int = 3,
    max_iterations: int = 10,
) -> str:
    """Apply the continuation rule and return the parent's final status.

    ``processor`` receives a child-row dict (``id``, ``name``, ``status``,
    ``attempts``) and must be idempotent — the same child may be presented
    again on retry.  It should:
    - Complete normally on success (the child is marked SUCCESS).
    - Raise ``BatchItemFailure`` for a permanent error (the child is marked FAILURE).
    - Raise any other exception for a transient error (the child is marked RETRY).
    """
    for iteration in range(1, max_iterations + 1):
        pending = store.pending_children(parent_id, max_attempts=max_attempts)
        if not pending:
            break

        progress = False
        for child in pending:
            child_id = child["id"]
            store.mark(child_id, "STARTED", increment_attempts=True)
            try:
                processor(child)
                store.mark(child_id, "SUCCESS")
                progress = True
            except BatchItemFailure as exc:
                store.mark(child_id, "FAILURE", error=str(exc))
                log.warning("Item %s permanently failed: %s", child_id, exc)
                progress = True  # progressed (settled a child)
            except Exception as exc:  # noqa: BLE001
                store.mark(child_id, "RETRY", error=str(exc))
                log.warning("Item %s transient failure (attempt %d): %s", child_id, child["attempts"] + 1, exc)

        if not progress:
            log.error(
                "Batch %s: no progress in iteration %d — circuit breaking.",
                parent_id,
                iteration,
            )
            store.mark(parent_id, "FAILURE", error="circuit-breaker: no progress")
            return "FAILURE"

        log.info("Batch %s: iteration %d complete.", parent_id, iteration)
    else:
        log.error("Batch %s: reached max_iterations=%d — circuit breaking.", parent_id, max_iterations)
        store.mark(parent_id, "FAILURE", error=f"circuit-breaker: max_iterations={max_iterations}")
        return "FAILURE"

    return store.finalize_parent(parent_id)
