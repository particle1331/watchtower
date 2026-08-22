"""Write an operational run record to the generic results DB (docs/02, docs/04).

Every job — training, eval, batch — writes a uniform results-DB record so the
dashboard sees all workflows the same way, while MLflow holds the ML-specific
lineage. This is the shared writer used from Chapter 03 onward; the ``results``
table's DDL and the parent/child batch model are defined in Chapter 04
(``ml_platform/results/``). The record shape here is intentionally the columns
that DDL formalizes: ``id, name, status, triggered_by, created_at, updated_at,
output(jsonb), error``.

Auth mirrors the MLflow app: no passwords — an Entra access token for the
``ossrdbms-aad`` scope is used as the Postgres password via the job's managed
identity. If the results DB is not configured (``PGHOST`` unset), recording is a
no-op so the training logic still runs locally before Phase 2 exists.
"""


import contextlib
import os
from collections.abc import Iterator
from typing import Any

from ml_platform.results import store


@contextlib.contextmanager
def record_run(
    name: str,
    *,
    triggered_by: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Record a run as ``STARTED``, then mark ``SUCCESS``/``FAILURE`` on exit.

    Yields a mutable ``dict`` the caller fills with an ``output`` payload (e.g.
    the MLflow run id and registered version). On an exception the record is
    closed as ``FAILURE`` and the exception re-raised, so a schema violation or
    training error leaves an honest operational trail.
    """
    payload: dict[str, Any] = {}
    triggered_by = triggered_by or os.environ.get("TRIGGERED_BY") or "schedule"

    if not os.environ.get("PGHOST"):
        # Local/dev before Phase 2: run the work, skip persistence.
        yield payload
        return

    # The local execution-plane supplies its execution name here so callers can
    # follow one identifier from trigger response to the results API. Deployed
    # ACA jobs do not set this variable and keep the existing UUID behavior.
    run_id = store.create_run(
        name,
        triggered_by=triggered_by,
        run_id=os.environ.get("RESULTS_RUN_ID"),
    )
    store.mark(run_id, "STARTED")
    try:
        yield payload
    except Exception as exc:
        store.mark(run_id, "FAILURE", output=payload, error=str(exc))
        raise
    else:
        store.mark(run_id, "SUCCESS", output=payload)
