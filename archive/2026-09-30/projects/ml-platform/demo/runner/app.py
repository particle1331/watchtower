"""Tiny local execution-plane stand-in for ACA Job manual triggers."""

import logging
import os
import subprocess
import threading
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_DATA_SOURCE = (
    "https://raw.githubusercontent.com/mlflow/mlflow/master/tests/datasets/winequality-white.csv"
)
_MODEL_NAME = os.environ.get("MODEL_NAME", "wine-quality")
_MODEL_VERSION = os.environ.get("MODEL_VERSION", "1")

_COMMANDS: dict[str, list[str]] = {
    "train": [
        "python",
        "train.py",
        "--data-source",
        _DATA_SOURCE,
        "--delimiter",
        ";",
    ],
    "eval": [
        "python",
        "evaluate.py",
        "--registered-name",
        _MODEL_NAME,
        "--version",
        _MODEL_VERSION,
        "--data-source",
        _DATA_SOURCE,
        "--delimiter",
        ";",
    ],
    "batch": [
        "python",
        "score.py",
        "--data-source",
        _DATA_SOURCE,
        "--delimiter",
        ";",
        "--model-name",
        _MODEL_NAME,
        "--model-version",
        _MODEL_VERSION,
    ],
}

_ALLOWED_PARAMETERS: dict[str, set[str]] = {
    "train": {
        "data_source",
        "delimiter",
        "experiment",
        "registered_name",
        "dataset_name",
        "target",
        "alpha",
        "l1_ratio",
        "test_size",
        "random_state",
    },
    "eval": {
        "registered_name",
        "version",
        "data_source",
        "delimiter",
        "experiment",
        "target",
        "max_rmse",
        "test_size",
        "random_state",
    },
    "batch": {
        "data_source",
        "delimiter",
        "target",
        "model_name",
        "model_version",
        "experiment",
        "chunk_size",
        "max_attempts",
    },
}

app = FastAPI(title="ml-platform local execution plane")
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "alive"}


def _command_for(job_name: str, parameters: dict[str, Any]) -> list[str]:
    unknown = set(parameters) - _ALLOWED_PARAMETERS[job_name]
    if unknown:
        names = ", ".join(sorted(unknown))
        raise HTTPException(status_code=422, detail=f"Unsupported parameters: {names}")

    command = list(_COMMANDS[job_name])
    for name, value in parameters.items():
        if isinstance(value, (dict, list)):
            raise HTTPException(
                status_code=422,
                detail=f"Parameter {name!r} must be a scalar value",
            )
        flag = f"--{name.replace('_', '-')}"
        if flag in command:
            command[command.index(flag) + 1] = str(value)
        else:
            command.extend([flag, str(value)])
    return command


def _execute(
    execution: str,
    job_name: str,
    triggered_by: str,
    parameters: dict[str, Any],
) -> None:
    env = os.environ.copy()
    env["TRIGGERED_BY"] = triggered_by
    # Keep the local execution identifier aligned with the parent results row.
    # This gives the caller one ID to poll after POST /api/runs/{job}/trigger.
    env["RESULTS_RUN_ID"] = execution
    command = _command_for(job_name, parameters)
    log.info("Starting %s (%s): %s", execution, triggered_by, " ".join(command))
    process = subprocess.Popen(
        command,
        cwd="/app",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    output, _ = process.communicate()
    with _lock:
        _jobs[execution].update(
            status="SUCCESS" if process.returncode == 0 else "FAILURE",
            exit_code=process.returncode,
            output=output[-4000:],
        )
    log.info("Finished %s with exit code %s", execution, process.returncode)


@app.post("/api/jobs/{job_name}/run")
def run_job(job_name: str, body: dict[str, Any] | None = None) -> dict[str, str]:
    if job_name not in _COMMANDS:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_name}")
    body = body or {}
    triggered_by = body.get("triggered_by", "demo-user")
    parameters = body.get("parameters", {})
    if not isinstance(parameters, dict):
        raise HTTPException(status_code=422, detail="parameters must be an object")
    # Validate before accepting the execution so bad requests do not leave a
    # misleading RUNNING entry in the in-memory execution catalog.
    _command_for(job_name, parameters)
    with _lock:
        execution = f"local-{job_name}-{uuid.uuid4().hex[:8]}"
        _jobs[execution] = {
            "execution": execution,
            "job_name": job_name,
            "status": "RUNNING",
            "triggered_by": triggered_by,
            "parameters": dict(parameters),
        }
    threading.Thread(
        target=_execute,
        args=(execution, job_name, triggered_by, parameters),
        daemon=True,
    ).start()
    return {"execution": execution, "triggered_by": triggered_by}


@app.get("/api/jobs")
def jobs() -> list[dict[str, Any]]:
    with _lock:
        return list(_jobs.values())


@app.get("/api/jobs/{execution}")
def job(execution: str) -> dict[str, Any]:
    with _lock:
        details = _jobs.get(execution)
        if details is None:
            raise HTTPException(status_code=404, detail=f"Unknown execution: {execution}")
        return dict(details)
