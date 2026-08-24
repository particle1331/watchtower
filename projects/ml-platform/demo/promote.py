"""Promote a trained model version to production: one entrypoint, two backends.

The promotion flow always flips the MLflow registry alias ``production`` to
``--version N`` against ``MLFLOW_TRACKING_URI`` (default
http://localhost:15000), then redeploys the long-running serving consumer
pinned to that exact version:

- ``--backend local`` (default): writes ``DEMO_MODEL_VERSION=N`` into
  ``demo/.env`` (created or merged; unrelated lines are preserved) and runs
  ``docker compose up -d serving`` in the demo directory. The Compose file
  interpolates the serving service's ``MODEL_VERSION`` from that variable.
- ``--backend aca``: requires ``--resource-group`` and ``--app-name``, then
  prints the ``az containerapp update`` command that repins ``MODEL_VERSION``
  on the serving App. The command runs only with ``--execute``; the default is
  a dry run because no Azure environment exists yet.

Examples:
    python demo/promote.py --version 3
    python demo/promote.py --tracking-uri https://mlflow.example --version 3
    python demo/promote.py --backend aca --version 3 --resource-group rg-mlp --app-name app-serving
    python demo/promote.py --backend aca --version 3 --resource-group rg-mlp --app-name app-serving --execute
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("promote")

DEMO_DIR = Path(__file__).resolve().parent
ENV_FILE = DEMO_DIR / ".env"

DEFAULT_TRACKING_URI = "http://localhost:15000"
DEFAULT_MODEL_NAME = "wine-quality"
PRODUCTION_ALIAS = "production"
VERSION_ENV_VAR = "DEMO_MODEL_VERSION"


def _flip_alias(model_name: str, version: int, tracking_uri: str) -> None:
    """Point the registry alias ``production`` at ``version``."""
    log.info(
        "Setting MLflow alias '%s' on model '%s' to version %d (%s)",
        PRODUCTION_ALIAS,
        model_name,
        version,
        tracking_uri,
    )
    try:
        # The installed mlflow package wins over the local demo/mlflow/ dir at
        # runtime (regular packages beat namespace portions), but pyright
        # resolves that directory and cannot see MlflowClient in it.
        from mlflow import MlflowClient  # pyright: ignore[reportAttributeAccessIssue]
    except ImportError as exc:
        msg = (
            "mlflow is required to flip the registry alias but is not installed "
            "in this Python environment. Install it (e.g. `uv pip install mlflow`) "
            "or run this script where mlflow is available."
        )
        raise RuntimeError(msg) from exc
    client = MlflowClient(tracking_uri=tracking_uri)
    client.set_registered_model_alias(model_name, PRODUCTION_ALIAS, str(version))
    log.info("Alias '%s' now points at version %d", PRODUCTION_ALIAS, version)


def _write_demo_env(version: int) -> None:
    """Create or merge ``demo/.env`` so Compose interpolation pins the version."""
    marker = f"{VERSION_ENV_VAR}="
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    kept = [line for line in lines if not line.strip().startswith(marker)]
    kept.append(f"{marker}{version}")
    ENV_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
    log.info("Wrote %s%d into %s", marker, version, ENV_FILE)


def _redeploy_compose_serving() -> None:
    """Recreate the Compose serving service with the new pinned version."""
    command = ["docker", "compose", "up", "-d", "serving"]
    log.info("Redeploying serving service (%s)", " ".join(command))
    completed = subprocess.run(command, cwd=DEMO_DIR, check=False)
    if completed.returncode != 0:
        msg = f"{' '.join(command)} failed with exit code {completed.returncode}"
        raise RuntimeError(msg)


def _redeploy_aca_serving(
    resource_group: str, app_name: str, version: int, execute: bool
) -> None:
    """Print (and optionally run) the ACA update that repins MODEL_VERSION."""
    command = [
        "az",
        "containerapp",
        "update",
        "--resource-group",
        resource_group,
        "--name",
        app_name,
        "--set-env-vars",
        f"MODEL_VERSION={version}",
    ]
    printable = " ".join(command)
    if not execute:
        log.info("Dry run: pass --execute to apply. Command:\n  %s", printable)
        return
    log.info("Executing: %s", printable)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        msg = f"az containerapp update failed with exit code {completed.returncode}"
        raise RuntimeError(msg)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", type=int, required=True, metavar="N",
                        help="model version to promote")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME,
                        help="registered model name (default: %(default)s)")
    parser.add_argument("--backend", choices=("local", "aca"), default="local",
                        help="redeployment target (default: %(default)s)")
    parser.add_argument(
        "--tracking-uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI),
        help="MLflow tracking/registry URL (default: MLFLOW_TRACKING_URI or %(default)s)",
    )
    parser.add_argument("--resource-group",
                        help="Azure resource group (required for --backend aca)")
    parser.add_argument("--app-name",
                        help="serving Container App name (required for --backend aca)")
    parser.add_argument("--execute", action="store_true",
                        help="actually run the az command (aca backend only)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.version < 1:
        log.error("--version must be a positive integer")
        return 1

    try:
        _flip_alias(args.model_name, args.version, args.tracking_uri)
        if args.backend == "local":
            _write_demo_env(args.version)
            _redeploy_compose_serving()
        else:
            if not args.resource_group or not args.app_name:
                log.error("--backend aca requires --resource-group and --app-name")
                return 1
            _redeploy_aca_serving(
                args.resource_group, args.app_name, args.version, args.execute
            )
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        log.error("%s", exc)
        return 1

    log.info("Promotion of '%s' version %d complete", args.model_name, args.version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
