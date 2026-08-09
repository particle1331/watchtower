"""Configure the MLflow client to talk to the self-hosted tracking/registry server.

The training and batch job images call :func:`configure_mlflow` at startup. The
tracking URI is the self-hosted MLflow App's HTTPS ingress (Phase 0); the same
server serves the model registry and proxies artifact access, so a single URI is
enough. MLflow is self-hosted at a pinned version, so this lineage path is under
our control and not subject to a managed provider's version lag (docs/00, docs/02).
"""


import os

import mlflow

TRACKING_URI_ENV = "MLFLOW_TRACKING_URI"


def configure_mlflow(experiment: str | None = None) -> str:
    """Point MLflow at the self-hosted server and (optionally) set the experiment.

    Returns the resolved tracking URI. Raises if it is not configured, since a
    job that silently logs to a local `mlruns/` dir would produce lineage that
    never reaches the registry.
    """
    uri = os.environ.get(TRACKING_URI_ENV)
    if not uri:
        raise RuntimeError(
            f"{TRACKING_URI_ENV} is required — set it to the self-hosted MLflow App URL."
        )
    mlflow.set_tracking_uri(uri)
    # The same self-hosted server backs the model registry.
    mlflow.set_registry_uri(uri)
    if experiment:
        mlflow.set_experiment(experiment)
    return uri
