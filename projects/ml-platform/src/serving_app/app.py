"""Online serving ACA App — loads an exact MLflow model version (docs/05).

Startup:
  1. Load ``models:/<MODEL_NAME>/<MODEL_VERSION>`` from the self-hosted registry.
  2. Run a canary prediction to confirm the loaded artefact is callable.
  3. Mark the app ready; ``/readyz`` reports the resolved version.

Endpoints:
  GET  /healthz       — liveness probe (always 200 once the process is alive).
  GET  /readyz        — readiness probe; 503 until the model is loaded and the
                        canary passes; 200 with {model_name, model_version, status}.
  POST /v1/predictions — inference; body: {"instances": [[f1, f2, ...]]}
                         response: {"predictions": [v1, v2, ...], "model_version": "..."}

Identity: ``id-serving`` (read-only MLflow artefacts; no write access to the
registry or training data).  All config is env; no secrets in the image.
"""


import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from ml_platform.common.model_adapter import frame_for_instances, model_kind, prediction_values
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (all from env, no secrets)
# ---------------------------------------------------------------------------

_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "")
_MODEL_NAME = os.environ.get("MODEL_NAME", "wine-quality")
_MODEL_VERSION = os.environ.get("MODEL_VERSION", "")  # must be set in the App definition
_PORT = int(os.environ.get("PORT", "8080"))


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

class _State:
    model: Any = None
    model_version: str = ""
    ready: bool = False
    error: str = ""


_state = _State()


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Load the pinned model version and run a canary prediction."""
    if not _TRACKING_URI:
        _state.error = "MLFLOW_TRACKING_URI is not set"
        log.error(_state.error)
        yield
        return

    if not _MODEL_VERSION:
        _state.error = "MODEL_VERSION is not set — refusing to serve a floating alias"
        log.error(_state.error)
        yield
        return

    mlflow.set_tracking_uri(_TRACKING_URI)
    model_uri = f"models:/{_MODEL_NAME}/{_MODEL_VERSION}"
    log.info("Loading model from %s", model_uri)

    try:
        _state.model = mlflow.pyfunc.load_model(model_uri)
        _state.model_version = _MODEL_VERSION

        # Canary: run one prediction to confirm the model is callable.
        if model_kind(_state.model) == "text":
            canary = pd.DataFrame({"input": ["health check"]})
        else:
            canary = pd.DataFrame(
                [[7.0, 0.27, 0.36, 20.7, 0.045, 45.0, 170.0, 1.001, 3.0, 0.45, 8.8]]
            )
        _state.model.predict(canary)

        _state.ready = True
        log.info("Model %s version %s loaded and canary passed", _MODEL_NAME, _MODEL_VERSION)
    except Exception as exc:  # noqa: BLE001
        _state.error = str(exc)
        log.exception("Model load failed: %s", exc)

    yield
    # Shutdown — nothing to clean up for a stateless model.


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="ml-platform serving", lifespan=_lifespan)


class _PredictRequest(BaseModel):
    instances: list[Any]


class _PredictResponse(BaseModel):
    predictions: list[Any]
    model_name: str
    model_version: str


@app.get("/healthz", status_code=200)
def healthz() -> dict[str, str]:
    """Liveness probe — always 200 once the process is running."""
    return {"status": "alive"}


@app.get("/readyz")
def readyz(response: Response) -> dict[str, str]:
    """Readiness probe — 503 until the model is loaded and the canary passes."""
    if _state.ready:
        return {
            "status": "ready",
            "model_name": _MODEL_NAME,
            "model_version": _state.model_version,
        }
    response.status_code = 503
    return {"status": "not_ready", "error": _state.error or "loading"}


@app.post("/v1/predictions", response_model=_PredictResponse)
def predict(req: _PredictRequest) -> _PredictResponse:
    """Synchronous inference endpoint."""
    if not _state.ready:
        raise HTTPException(status_code=503, detail="Model not ready")
    if not req.instances:
        raise HTTPException(status_code=422, detail="instances must be non-empty")

    try:
        df = frame_for_instances(_state.model, req.instances)
        preds = _state.model.predict(df)
    except Exception as exc:
        status_code = 422 if isinstance(exc, ValueError) else 500
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return _PredictResponse(
        predictions=prediction_values(preds),
        model_name=_MODEL_NAME,
        model_version=_state.model_version,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=_PORT)
