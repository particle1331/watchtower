"""SETNX-based idempotency guard for at-least-once delivery safety.

Celery + Redis provide at-least-once delivery. This module converts that into
exactly-once side effects by using a Redis key as an idempotency sentinel.

Mechanism:
1. Generate a stable idempotency key from the document's immutable identifier.
2. Before processing, atomically SET-if-Not-eXists a sentinel key in Redis.
3. If the key already exists → duplicate delivery → skip processing.
4. If the key doesn't exist → proceed, write the sentinel, process.
5. Sentinel TTL matches result_expires and reconciliation window (7 days).

Why SETNX instead of broker-level acknowledgements:
- Redis at-least-once means duplicates are inevitable.
- SETNX is a single atomic operation — no race condition between check and write.
- 7-day TTL keeps Redis compact (~210 MB for 30k docs/day with 1 KB payloads).

See: learning/mlops/07-idempotency.ipynb for the full deep dive.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

import redis

logger = logging.getLogger(__name__)

IDEMPOTENCY_TTL = 604800  # 7 days in seconds


def _get_redis_client() -> redis.Redis:
    """Return a Redis client. Create on demand to avoid startup coupling."""
    return redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)


@contextmanager
def idempotency_guard(idempotency_key: str, ttl: int = IDEMPOTENCY_TTL) -> Generator[bool]:
    """Context manager that skips duplicate work via atomic SETNX.

    Args:
        idempotency_key: Stable key derived from the immutable document identifier.
        ttl: Time-to-live for the sentinel key in seconds (default 7 days).

    Yields:
        True if this is the first execution (proceed with work).
        False if this is a duplicate (skip processing).

    Example:
        with idempotency_guard(f"doc:{doc_id}:v{task_contract}") as should_process:
            if not should_process:
                logger.info("Duplicate delivery — skipping")
                return
            result = do_expensive_work()
            store_result(result)
        # Celery acknowledges here — if worker dies before this line,
        # task_reject_on_worker_lost triggers redelivery and the guard
        # prevents double execution.
    """
    client = _get_redis_client()
    acquired = client.set(idempotency_key, "1", nx=True, ex=ttl)

    if acquired:
        logger.debug("Idempotency guard: acquired key=%s", idempotency_key)
    else:
        logger.info("Idempotency guard: duplicate key=%s — skipping", idempotency_key)

    try:
        yield bool(acquired)
    finally:
        pass  # Sentinel stays until TTL expires — do NOT delete on success


def is_duplicate(idempotency_key: str) -> bool:
    """Check whether an idempotency key has already been used (non-blocking)."""
    client = _get_redis_client()
    return bool(client.exists(idempotency_key))


def make_idempotency_key(doc_id: str, task_contract_version: int) -> str:
    """Derive a stable idempotency key from a document's immutable identifier.

    The contract version is included so that re-processing the same document
    under a new task contract creates a different key — the old result was
    produced under different rules.
    """
    return f"idem:doc:{doc_id}:v{task_contract_version}"
