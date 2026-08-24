"""Results DB store — insert/update rows with parent/child helpers (docs/04).

All writes go through this module; the connection uses the same Entra managed-
identity token as ``common/results.py``.  A no-op guard (``PGHOST`` unset) keeps
every caller runnable locally before the database exists.

Status vocabulary (matches schema.sql):
    PENDING   Created, not yet started.
    STARTED   Currently executing.
    SUCCESS   Completed successfully.
    RETRY     Failed transiently; eligible for retry.
    FAILURE   Failed permanently (validation error / retries exhausted).
    REVOKED   Cancelled.
"""


import datetime as dt
import hashlib
import json
import os
import uuid
from typing import Any

_OSSRDBMS_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _configured() -> bool:
    return bool(os.environ.get("PGHOST"))


def _connect():
    import psycopg

    # Deployed jobs use Entra tokens. The local Compose POC uses ordinary
    # Postgres password auth instead, selected by PGPASSWORD.
    if os.environ.get("PGPASSWORD"):
        return psycopg.connect(
            host=os.environ["PGHOST"],
            port=os.environ.get("PGPORT", "5432"),
            dbname=os.environ.get("RESULTS_DB", "results"),
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            sslmode=os.environ.get("PGSSLMODE", "prefer"),
        )

    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token(_OSSRDBMS_SCOPE).token
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("RESULTS_DB", "results"),
        user=os.environ["PGUSER"],
        password=token,
        sslmode="require",
    )


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------------------------------------------------------------------------
# Public API — individual rows
# ---------------------------------------------------------------------------

def create_run(
    name: str,
    *,
    triggered_by: str,
    run_id: str | None = None,
) -> str:
    """Insert a top-level (parent_id IS NULL) row in PENDING status.

    Returns the ``id`` so the caller can pass it to ``create_children`` or
    ``mark``.  No-op (returns a random id) when the DB is not configured.
    """
    rid = run_id or str(uuid.uuid4())
    if not _configured():
        return rid
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO results (id, parent_id, name, status, triggered_by, created_at, updated_at)
                VALUES (%s, NULL, %s, 'PENDING', %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (rid, name, triggered_by, _now(), _now()),
            )
        conn.commit()
    finally:
        conn.close()
    return rid


def create_children(
    parent_id: str,
    items: list[str],
    *,
    name: str,
    triggered_by: str,
) -> list[str]:
    """Insert one child row per item key, using a deterministic id for idempotency.

    The child id is ``SHA-256(name + item_key)[:32]`` so re-inserting an already
    completed item is a no-op (ON CONFLICT DO NOTHING).  Returns the list of ids
    in the same order as ``items``.
    """
    ids = [_item_id(name, key) for key in items]
    if not _configured():
        return ids
    now = _now()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            for rid, key in zip(ids, items, strict=True):
                cur.execute(
                    """
                    INSERT INTO results (id, parent_id, name, status, triggered_by, created_at, updated_at)
                    VALUES (%s, %s, %s, 'PENDING', %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (rid, parent_id, f"{name}:{key}", triggered_by, now, now),
                )
        conn.commit()
    finally:
        conn.close()
    return ids


def mark(
    run_id: str,
    status: str,
    *,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    increment_attempts: bool = False,
) -> None:
    """Update status, output/error, and updated_at for a row.

    Pass ``increment_attempts=True`` when recording a RETRY or FAILURE after
    an attempt so the continuation rule can enforce the ``max_attempts`` cap.
    """
    if not _configured():
        return
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE results
                SET status   = %s,
                    output   = COALESCE(%s::jsonb, output),
                    error    = COALESCE(%s, error),
                    attempts = attempts + %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    status,
                    json.dumps(output) if output is not None else None,
                    error,
                    1 if increment_attempts else 0,
                    _now(),
                    run_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def pending_children(
    parent_id: str,
    *,
    max_attempts: int = 3,
) -> list[dict[str, Any]]:
    """Return children with status PENDING or RETRY and attempts < max_attempts.

    Each element is a dict with keys ``id``, ``name``, ``status``, ``attempts``.
    Returns an empty list when the DB is not configured.
    """
    if not _configured():
        return []
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, status, attempts
                FROM results
                WHERE parent_id = %s
                  AND status IN ('PENDING', 'RETRY')
                  AND attempts < %s
                ORDER BY created_at
                """,
                (parent_id, max_attempts),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "name": r[1], "status": r[2], "attempts": r[3]}
        for r in rows
    ]


def finalize_parent(parent_id: str, *, max_attempts: int = 3) -> str:
    """Mark the parent SUCCESS if no children are eligible, else FAILURE.

    A RETRY child is still active only while it has attempts remaining. An
    exhausted RETRY is treated as a permanent failure so a batch cannot remain
    stuck in STARTED after the continuation loop has given up on it.
    Returns the final status string.
    """
    if not _configured():
        return "SUCCESS"
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status IN ('PENDING', 'STARTED')
                           OR (status = 'RETRY' AND attempts < %s)
                    ) AS still_running,
                    COUNT(*) FILTER (
                        WHERE status = 'FAILURE'
                           OR (status IN ('PENDING', 'RETRY') AND attempts >= %s)
                    ) AS failures
                FROM results
                WHERE parent_id = %s
                """,
                (max_attempts, max_attempts, parent_id),
            )
            row = cur.fetchone()
        still_running, failures = row[0], row[1]
        if still_running > 0:
            final = "STARTED"  # not done yet
        elif failures > 0:
            final = "FAILURE"
        else:
            final = "SUCCESS"
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE results SET status = %s, updated_at = %s WHERE id = %s",
                (final, _now(), parent_id),
            )
        conn.commit()
    finally:
        conn.close()
    return final


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _item_id(batch_name: str, item_key: str) -> str:
    """Deterministic id — SHA-256(name + item_key), hex[:32]."""
    digest = hashlib.sha256(f"{batch_name}:{item_key}".encode()).hexdigest()
    return digest[:32]
