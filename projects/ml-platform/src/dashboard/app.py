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

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_PGHOST = os.environ.get("PGHOST", "")
_PGUSER = os.environ.get("PGUSER", "")
_RESULTS_DB = os.environ.get("RESULTS_DB", "results")
_MLFLOW_URL = os.environ.get("MLFLOW_TRACKING_URI", "")
_GRAFANA_URL = os.environ.get("GRAFANA_URL", "")
_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")
_ACA_ENV_NAME = os.environ.get("ACA_ENV_NAME", "")
_OSSRDBMS_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

app = FastAPI(title="ml-platform dashboard")


# ---------------------------------------------------------------------------
# DB helpers (read-only; no-op if PGHOST unset)
# ---------------------------------------------------------------------------

def _db_connect():
    import psycopg
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token(_OSSRDBMS_SCOPE).token
    return psycopg.connect(
        host=_PGHOST,
        dbname=_RESULTS_DB,
        user=_PGUSER,
        password=token,
        sslmode="require",
    )


def _recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    if not _PGHOST:
        return []
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, parent_id, name, status, triggered_by,
                       attempts, created_at, updated_at,
                       output, error
                FROM results
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# ACA Jobs trigger helper
# ---------------------------------------------------------------------------

def _trigger_job(job_name: str, triggered_by: str) -> str:
    """Start an ACA Job execution; returns the execution name."""
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
    runs = _recent_runs(limit)
    # Serialize datetime objects to ISO strings for JSON.
    for r in runs:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
    return runs


@app.post("/api/runs/{job_name}/trigger")
async def trigger_run(job_name: str, request: Request) -> dict[str, str]:
    """Start a Job execution. triggered_by is the Easy Auth caller identity."""
    triggered_by = request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "unknown")
    log.info("Manual trigger: job=%s triggered_by=%s", job_name, triggered_by)
    try:
        execution_name = _trigger_job(job_name, triggered_by)
    except Exception as exc:
        log.exception("Failed to trigger job %s: %s", job_name, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"execution": execution_name, "triggered_by": triggered_by}


@app.get("/", response_class=HTMLResponse)
async def catalog() -> Response:
    """Lightweight HTML catalog — reads results DB and deep-links to Grafana/MLflow."""
    runs = _recent_runs(20)
    for r in runs:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()

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
