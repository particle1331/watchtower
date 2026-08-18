"""Workflow catalog + launcher dashboard (docs/06).

A lightweight FastAPI app that is the human surface over the ML platform.
It is a **catalog + launcher**, not a new source of truth:

  - GET  /         — HTML catalog of all workflows with recent run status,
                     deep-links to Grafana and MLflow.
  - GET  /api/runs — JSON: recent rows from the results DB (read-only).
  - POST /api/runs/{job_name}/trigger
                   — Start an ACA Job execution; records triggered_by from
                     the Entra Easy Auth header.
  - GET  /healthz  — Liveness probe.

Auth: Entra ID Easy Auth sits in front (configured in the ACA App definition).
The signed-in user's UPN is injected as X-MS-CLIENT-PRINCIPAL-NAME; the app
records it as triggered_by on every manual launch.

Identity: id-dashboard — read-only on results DB + ACA execution-start (scoped).
No write access to the registry or training data.
"""


import json
import logging
import os
from typing import Any
from urllib.parse import quote
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PGHOST = os.environ.get("PGHOST", "")
_PGUSER = os.environ.get("PGUSER", "")
_RESULTS_DB = os.environ.get("RESULTS_DB", "results")
# The tracking URI is used by workloads inside the platform.  The dashboard
# link is opened by a browser, so deployments may need a different,
# browser-reachable URL (for example, localhost instead of the Compose DNS
# name).  Keep the old fallback for existing deployments.
_MLFLOW_URL = os.environ.get("MLFLOW_UI_URL") or os.environ.get(
    "MLFLOW_TRACKING_URI", ""
)
_GRAFANA_URL = os.environ.get("GRAFANA_URL", "")
_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")
_ACA_ENV_NAME = os.environ.get("ACA_ENV_NAME", "")
_TRIGGER_BACKEND = os.environ.get("TRIGGER_BACKEND", "aca")
_RUNNER_URL = os.environ.get("RUNNER_URL", "http://runner:8090")
_OSSRDBMS_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

app = FastAPI(title="ml-platform dashboard")


_DEFAULT_DATA_SOURCE = (
    "https://raw.githubusercontent.com/mlflow/mlflow/master/"
    "tests/datasets/winequality-white.csv"
)


class TrainParameters(BaseModel):
    """Optional train-job overrides, with the entrypoint's defaults documented."""

    model_config = ConfigDict(extra="forbid")

    data_source: str = Field(default=_DEFAULT_DATA_SOURCE, description="CSV URL or path")
    delimiter: str = Field(default=";", description="CSV delimiter")
    experiment: str = Field(default="wine-quality", description="MLflow experiment name")
    registered_name: str = Field(default="wine-quality", description="Registered model name")
    dataset_name: str = Field(default="wine-quality-white", description="Tracked dataset name")
    target: str = Field(default="quality", description="Target column")
    alpha: float = Field(default=0.5, description="ElasticNet alpha")
    l1_ratio: float = Field(default=0.5, description="ElasticNet l1 ratio")
    test_size: float = Field(default=0.25, description="Held-out test fraction")
    random_state: int = Field(default=42, description="Split/training seed")


class BatchParameters(BaseModel):
    """Optional batch-job overrides, with the entrypoint's defaults documented."""

    model_config = ConfigDict(extra="forbid")

    data_source: str = Field(default=_DEFAULT_DATA_SOURCE, description="CSV URL or path")
    delimiter: str = Field(default=";", description="CSV delimiter")
    target: str = Field(default="quality", description="Optional label column to drop")
    model_name: str = Field(default="wine-quality", description="Registered model name")
    model_version: str = Field(default="1", description="Pinned model version in the local POC")
    experiment: str = Field(default="wine-quality", description="MLflow experiment context")
    chunk_size: int = Field(default=100, ge=1, description="Rows per scoring chunk")
    max_attempts: int = Field(default=3, ge=1, description="Maximum attempts per chunk")


class JobTrigger(BaseModel):
    """Optional command-line parameters for a local job execution."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"parameters": {"alpha": 0.25, "l1_ratio": 0.8, "random_state": 7}}
            ]
        }
    )

    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Scalar command-line overrides. See GET /api/jobs for the catalog.",
    )


class TrainTrigger(BaseModel):
    """Train trigger payload. All fields show their runtime defaults in Swagger."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"parameters": {"alpha": 0.25, "l1_ratio": 0.8, "random_state": 7}}
            ]
        }
    )

    parameters: TrainParameters = Field(
        default_factory=TrainParameters,
        description="Train-job parameters. Omit fields to use the defaults below.",
    )


class BatchTrigger(BaseModel):
    """Batch trigger payload. All fields show their runtime defaults in Swagger."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"parameters": {"model_version": "1", "chunk_size": 500}}
            ]
        }
    )

    parameters: BatchParameters = Field(
        default_factory=BatchParameters,
        description="Batch-job parameters. Omit fields to use the defaults below.",
    )


class TriggerResponse(BaseModel):
    """Accepted execution returned by a job trigger."""

    execution: str
    job_name: str
    triggered_by: str
    parameters: dict[str, Any]
    result_id: str | None = Field(
        default=None,
        description="Results DB id. In the local POC this is the execution id.",
    )
    result_url: str | None = Field(
        default=None,
        description="Relative URL for polling the final operational result.",
    )
    status_url: str | None = Field(
        default=None,
        description="Relative URL for the local execution-plane status.",
    )


_JOB_CATALOG: list[dict[str, Any]] = [
    {
        "job_name": "train",
        "description": "Train ElasticNet on a CSV and register a new MLflow model version.",
        "endpoint": "/api/runs/train/trigger",
        "parameters": {
            "data_source": "CSV URL or path",
            "delimiter": "CSV delimiter, default ';'",
            "experiment": "MLflow experiment name, default 'wine-quality'",
            "registered_name": "Registered model name, default 'wine-quality'",
            "dataset_name": "Tracked dataset name, default 'wine-quality-white'",
            "target": "Target column, default 'quality'",
            "alpha": "ElasticNet alpha, default 0.5",
            "l1_ratio": "ElasticNet l1 ratio, default 0.5",
            "test_size": "Test split fraction, default 0.25",
            "random_state": "Integer split/training seed, default 42",
        },
        "example": {"alpha": 0.25, "l1_ratio": 0.8, "random_state": 7},
    },
    {
        "job_name": "batch",
        "description": "Load a registered MLflow model and score a CSV in chunks.",
        "endpoint": "/api/runs/batch/trigger",
        "parameters": {
            "data_source": "CSV URL or path",
            "delimiter": "CSV delimiter, default ';'",
            "target": "Optional label column to drop, default 'quality'",
            "model_name": "Registered model name, default 'wine-quality'",
            "model_version": "Pinned model version, default '1' in this POC",
            "experiment": "MLflow experiment context, default 'wine-quality'",
            "chunk_size": "Rows per chunk, default 100",
            "max_attempts": "Maximum attempts per chunk, default 3",
        },
        "example": {"model_version": "1", "chunk_size": 500, "max_attempts": 2},
    },
]


# ---------------------------------------------------------------------------
# DB helpers (read-only; no-op if PGHOST unset)
# ---------------------------------------------------------------------------

def _db_connect():
    import psycopg

    if os.environ.get("PGPASSWORD"):
        return psycopg.connect(
            host=_PGHOST,
            port=os.environ.get("PGPORT", "5432"),
            dbname=_RESULTS_DB,
            user=_PGUSER,
            password=os.environ["PGPASSWORD"],
            sslmode=os.environ.get("PGSSLMODE", "prefer"),
        )

    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token(_OSSRDBMS_SCOPE).token
    return psycopg.connect(
        host=_PGHOST,
        port=os.environ.get("PGPORT", "5432"),
        dbname=_RESULTS_DB,
        user=_PGUSER,
        password=token,
        sslmode="require",
    )


def _query_results(
    limit: int = 50,
    *,
    status: str | None = None,
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    if not _PGHOST:
        return []
    conn = _db_connect()
    try:
        filters: list[str] = []
        values: list[Any] = []
        if status:
            filters.append("status = %s")
            values.append(status)
        if parent_id:
            filters.append("parent_id = %s")
            values.append(parent_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, parent_id, name, status, triggered_by,
                       attempts, created_at, updated_at,
                       output, error
                FROM results
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (*values, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        conn.close()


def _result_by_id(result_id: str) -> dict[str, Any] | None:
    if not _PGHOST:
        return None
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, parent_id, name, status, triggered_by,
                       attempts, created_at, updated_at,
                       output, error
                FROM results
                WHERE id = %s
                """,
                (result_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row, strict=True))
    finally:
        conn.close()


def _serialize_result(result: dict[str, Any]) -> dict[str, Any]:
    for key, value in result.items():
        if hasattr(value, "isoformat"):
            result[key] = value.isoformat()
    return result


# ---------------------------------------------------------------------------
# ACA Jobs trigger helper
# ---------------------------------------------------------------------------

def _trigger_job(
    job_name: str,
    triggered_by: str,
    parameters: dict[str, Any] | None = None,
) -> str:
    """Start an ACA Job execution; returns the execution name."""
    parameters = parameters or {}
    if _TRIGGER_BACKEND == "local":
        payload = json.dumps(
            {"triggered_by": triggered_by, "parameters": parameters}
        ).encode()
        request = UrlRequest(
            f"{_RUNNER_URL}/api/jobs/{job_name}/run",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=15) as response:  # noqa: S310 - configured demo URL
            result = json.loads(response.read())
        return result["execution"]

    if parameters:
        raise RuntimeError(
            "Parameterized triggers require TRIGGER_BACKEND=local in this POC"
        )

    from azure.identity import DefaultAzureCredential
    from azure.mgmt.appcontainers import ContainerAppsAPIClient
    from azure.mgmt.appcontainers.models import JobExecutionTemplate, JobStartConfiguration

    if not _SUBSCRIPTION_ID or not _RESOURCE_GROUP:
        raise RuntimeError("AZURE_SUBSCRIPTION_ID and AZURE_RESOURCE_GROUP must be set")

    credential = DefaultAzureCredential()
    client = ContainerAppsAPIClient(credential, _SUBSCRIPTION_ID)

    # Pass triggered_by as an env override so it lands in the results DB record.
    start_config = JobStartConfiguration(
        template=JobExecutionTemplate(
            containers=[
                {
                    "name": job_name,
                    "env": [{"name": "TRIGGERED_BY", "value": triggered_by}],
                }
            ]
        )
    )
    poller = client.jobs.begin_start(
        resource_group_name=_RESOURCE_GROUP,
        job_name=job_name,
        template=start_config,
    )
    result = poller.result()
    return result.name if result else "started"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/healthz", status_code=200)
def healthz() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/api/runs")
def api_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Recent run rows from the results DB (dashboard read)."""
    return [_serialize_result(result) for result in _query_results(limit)]


@app.get("/api/jobs", tags=["Jobs"])
def api_jobs() -> list[dict[str, Any]]:
    """Describe triggerable jobs, accepted parameters, and example payloads."""
    return _JOB_CATALOG


@app.get("/api/results", tags=["Results"])
def api_results(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = None,
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    """List operational task results, optionally filtered by status or parent."""
    results = _query_results(limit, status=status, parent_id=parent_id)
    return [_serialize_result(result) for result in results]


@app.get("/api/results/{result_id}", tags=["Results"])
def api_result(result_id: str) -> dict[str, Any]:
    """Return one operational task result by id."""
    result = _result_by_id(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result {result_id!r} not found")
    return _serialize_result(result)


def _submit_trigger(
    job_name: str,
    request: Request,
    parameters: dict[str, Any],
) -> TriggerResponse:
    """Submit a job while keeping all trigger routes on one implementation."""
    triggered_by = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "unknown")
    log.info("Manual trigger: job=%s triggered_by=%s", job_name, triggered_by)
    try:
        execution_name = _trigger_job(job_name, triggered_by, parameters)
    except Exception as exc:
        log.exception("Failed to trigger job %s: %s", job_name, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return TriggerResponse(
        execution=execution_name,
        job_name=job_name,
        triggered_by=triggered_by,
        parameters=parameters,
        result_id=execution_name if _TRIGGER_BACKEND == "local" else None,
        result_url=(
            f"/api/results/{quote(execution_name, safe='')}"
            if _TRIGGER_BACKEND == "local"
            else None
        ),
        status_url=(
            f"/api/executions/{quote(execution_name, safe='')}"
            if _TRIGGER_BACKEND == "local"
            else None
        ),
    )


@app.post(
    "/api/runs/train/trigger",
    response_model=TriggerResponse,
    tags=["Jobs"],
    summary="Trigger training",
    description=(
        "Train and register a model. The request body is optional; use the "
        "defaults shown in `TrainTrigger` or override selected fields."
    ),
)
async def trigger_train(
    request: Request,
    body: TrainTrigger | None = None,
) -> TriggerResponse:
    parameters = body.parameters.model_dump(exclude_unset=True) if body else {}
    return _submit_trigger("train", request, parameters)


@app.post(
    "/api/runs/batch/trigger",
    response_model=TriggerResponse,
    tags=["Jobs"],
    summary="Trigger batch scoring",
    description=(
        "Score the CSV with a registered model. The request body is optional; "
        "use the defaults shown in `BatchTrigger` or override selected fields."
    ),
)
async def trigger_batch(
    request: Request,
    body: BatchTrigger | None = None,
) -> TriggerResponse:
    parameters = body.parameters.model_dump(exclude_unset=True) if body else {}
    return _submit_trigger("batch", request, parameters)


@app.get("/api/executions/{execution}", tags=["Jobs"])
def api_execution(execution: str) -> dict[str, Any]:
    """Return local runner status plus its results row when available."""
    if _TRIGGER_BACKEND != "local":
        raise HTTPException(
            status_code=501,
            detail="Execution status is only available with TRIGGER_BACKEND=local",
        )
    request = UrlRequest(f"{_RUNNER_URL}/api/jobs/{quote(execution, safe='')}")
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - configured demo URL
            runner_status = json.loads(response.read())
    except Exception as exc:
        log.exception("Failed to read execution %s: %s", execution, exc)
        raise HTTPException(status_code=404, detail=f"Unknown execution: {execution}") from exc

    result = _result_by_id(execution)
    return {
        "execution": execution,
        "runner": runner_status,
        "result": _serialize_result(result) if result else None,
    }


@app.post(
    "/api/runs/{job_name}/trigger",
    response_model=TriggerResponse,
    tags=["Jobs"],
    summary="Trigger a named job",
    description=(
        "Generic trigger for ACA-compatible job names. For the local POC, "
        "prefer the explicit train or batch routes above because they document "
        "their parameters and defaults."
    ),
)
async def trigger_run(
    job_name: str,
    request: Request,
    body: JobTrigger | None = None,
) -> TriggerResponse:
    """Start a Job execution. triggered_by is the Easy Auth caller identity."""
    parameters = body.parameters if body else {}
    return _submit_trigger(job_name, request, parameters)


@app.get("/", response_class=HTMLResponse)
async def catalog() -> Response:
    """Lightweight HTML catalog — reads results DB and deep-links to Grafana/MLflow."""
    runs = [_serialize_result(result) for result in _query_results(20)]

    rows_html = "\n".join(
        f"<tr>"
        f"<td>{r['name']}</td>"
        f"<td><span class='status-{r['status'].lower()}'>{r['status']}</span></td>"
        f"<td>{r.get('triggered_by', '')}</td>"
        f"<td>{str(r.get('created_at', ''))[:19]}</td>"
        f"<td>{r.get('error') or ''}</td>"
        f"</tr>"
        for r in runs
    )

    demo_controls = ""
    if _TRIGGER_BACKEND == "local":
        demo_controls = """<section style='margin:1rem 0;padding:1rem;background:#e9f2ff;border:1px solid #b6d4fe;border-radius:6px'>
  <strong>Local POC controls</strong>
  <button onclick=\"triggerJob('train')\" style='margin-left:1rem'>Run training</button>
  <button onclick=\"triggerJob('batch')\" style='margin-left:.5rem'>Run batch scoring</button>
  <span id='trigger-result' style='margin-left:1rem'></span>
</section>
<script>
async function triggerJob(job) {
  const result = document.getElementById('trigger-result');
  result.textContent = 'Starting ' + job + '...';
  const response = await fetch('/api/runs/' + job + '/trigger', {method: 'POST'});
  const body = await response.json();
  result.textContent = response.ok ? 'Started ' + body.execution : 'Error: ' + body.detail;
  if (response.ok) setTimeout(() => window.location.reload(), 1500);
}
</script>"""

    grafana_link = f'<a href="{_GRAFANA_URL}" target="_blank">Grafana</a>' if _GRAFANA_URL else "—"
    mlflow_link = f'<a href="{_MLFLOW_URL}" target="_blank">MLflow</a>' if _MLFLOW_URL else "—"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ML Platform — Workflow Dashboard</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f8f9fa; }}
    h1 {{ color: #212529; }}
    nav a {{ margin-right: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
    th, td {{ padding: .6rem 1rem; text-align: left; border-bottom: 1px solid #dee2e6; }}
    th {{ background: #343a40; color: white; }}
    .status-success {{ color: #198754; font-weight: bold; }}
    .status-failure {{ color: #dc3545; font-weight: bold; }}
    .status-retry {{ color: #fd7e14; }}
    .status-started, .status-pending {{ color: #0d6efd; }}
    .status-revoked {{ color: #6c757d; }}
  </style>
</head>
<body>
  <h1>ML Platform — Workflow Dashboard</h1>
  <nav>Deep links: {grafana_link} &nbsp; {mlflow_link}</nav>
  {demo_controls}
  <h2>Recent runs</h2>
  <table>
    <thead><tr><th>Workflow</th><th>Status</th><th>Triggered by</th><th>Started</th><th>Error</th></tr></thead>
    <tbody>{rows_html or "<tr><td colspan='5'>No runs recorded (results DB empty or not configured).</td></tr>"}</tbody>
  </table>
  <p style="color:#6c757d;font-size:.85rem;margin-top:1rem">
    Showing last 20 runs. Use <code>POST /api/runs/{{job_name}}/trigger</code> to launch a workflow.
    Execution state is authoritative in the results DB; this page is a read-only view.
  </p>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
