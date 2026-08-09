"""Write an operational run record to the generic results DB (docs/02, docs/04).

Every job — training, eval, batch — writes a uniform results-DB record so the
dashboard sees all workflows the same way, while MLflow holds the ML-specific
lineage. This is the shared writer used from Chapter 03 onward; the ``results``
table's DDL and the parent/child batch model are defined in Chapter 04
(``ml_platform/results/``). The record shape here is intentionally the columns
that DDL formalizes: ``name, status, triggered_by, started_at, finished_at,
output(jsonb)``.

Auth mirrors the MLflow app: no passwords — an Entra access token for the
``ossrdbms-aad`` scope is used as the Postgres password via the job's managed
identity. If the results DB is not configured (``PGHOST`` unset), recording is a
no-op so the training logic still runs locally before Phase 2 exists.
"""


import contextlib
import datetime as dt
import json
import os
from collections.abc import Iterator
from typing import Any

_OSSRDBMS_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def _configured() -> bool:
    return bool(os.environ.get("PGHOST"))


def _connect():
    import psycopg
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token(_OSSRDBMS_SCOPE).token
    return psycopg.connect(
        host=os.environ["PGHOST"],
        dbname=os.environ.get("RESULTS_DB", "results"),
        user=os.environ["PGUSER"],
        password=token,
        sslmode="require",
    )


@contextlib.contextmanager
def record_run(
    name: str,
    *,
    triggered_by: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Record a run as ``RUNNING``, then mark ``SUCCESS``/``FAILURE`` on exit.

    Yields a mutable ``dict`` the caller fills with an ``output`` payload (e.g.
    the MLflow run id and registered version). On an exception the record is
    closed as ``FAILURE`` and the exception re-raised, so a schema violation or
    training error leaves an honest operational trail.
    """
    payload: dict[str, Any] = {}
    triggered_by = triggered_by or os.environ.get("TRIGGERED_BY")

    if not _configured():
        # Local/dev before Phase 2: run the work, skip persistence.
        yield payload
        return

    started = dt.datetime.now(dt.UTC)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO results (name, status, triggered_by, started_at) "
                "VALUES (%s, 'RUNNING', %s, %s) RETURNING id",
                (name, triggered_by, started),
            )
            run_id = cur.fetchone()[0]
        conn.commit()

        try:
            yield payload
        except Exception:
            _finish(conn, run_id, "FAILURE", payload)
            raise
        else:
            _finish(conn, run_id, "SUCCESS", payload)
    finally:
        conn.close()


def _finish(conn, run_id: int, status: str, payload: dict[str, Any]) -> None:
    finished = dt.datetime.now(dt.UTC)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE results SET status = %s, finished_at = %s, output = %s WHERE id = %s",
            (status, finished, json.dumps(payload), run_id),
        )
    conn.commit()
