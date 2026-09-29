"""Golden-path suite for the local Compose ML platform.

Drives the whole path over plain HTTP (stdlib urllib only):

  1. trigger training via the dashboard and poll it to a terminal status
  2. resolve the newest registered model version from the MLflow REST API
  3. evaluate that exact version and require a passing result
  4. promote it through demo/promote.py in a subprocess (the real path)
  5. poll serving /readyz until it reports exactly the promoted version
  6. trigger batch scoring pinned to that version and poll to terminal
  7. assert the batch parent row shows SUCCESS in the results API

Requires a running demo stack: from projects/ml-platform/demo run
``docker compose up --build``. The ACA backend is out of scope here; use
deploy/smoke-tests.ps1 until Part II unifies the two suites.
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

PROMOTE_SCRIPT = Path(__file__).resolve().parent / "promote.py"

# REVOKED is included alongside FAILURE: a revoked execution never recovers,
# so waiting for it would only burn the timeout budget.
TERMINAL_STATUSES = frozenset({"SUCCESS", "FAILURE", "REVOKED"})
POLL_INTERVAL_SECONDS = 5.0
HTTP_TIMEOUT_SECONDS = 30


@dataclass
class _RunState:
    """Values handed from one step to the next."""

    args: argparse.Namespace
    model_version: int = 0
    batch_execution: str = ""


def _get_json(url: str) -> Any:
    with urlopen(Request(url), timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 - demo URLs
        return json.loads(response.read())


def _post_json(url: str, payload: dict[str, Any]) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310 - demo URLs
        return json.loads(response.read())


T = TypeVar("T")


def _wait_until(check: Callable[[], T | None], description: str, timeout: float) -> T:  # noqa: UP047
    """Poll ``check`` until it returns non-None or the timeout elapses.

    The check function signals transient unavailability by returning None and
    reports hard failure by raising.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result is not None:
            return result
        if time.monotonic() >= deadline:
            msg = f"{description}: timed out after {timeout:.0f}s"
            raise TimeoutError(msg)
        time.sleep(POLL_INTERVAL_SECONDS)


def _result_url(dashboard_url: str, response: dict[str, Any]) -> str:
    """Absolute URL to poll: the trigger's result_url, or the canonical fallback."""
    relative = response.get("result_url")
    if relative:
        return urljoin(f"{dashboard_url}/", relative)
    return f"{dashboard_url}/api/results/{quote(str(response['execution']), safe='')}"


def _wait_for_terminal(result_url: str, label: str, timeout: float) -> dict[str, Any]:
    def check() -> dict[str, Any] | None:
        try:
            row = _get_json(result_url)
        except HTTPError, URLError:
            return None  # results row not visible yet; keep polling
        status = str(row.get("status", "")).upper()
        if status == "SUCCESS":
            return row
        if status in TERMINAL_STATUSES:
            error = row.get("error") or "(no error detail)"
            msg = f"{label} ended with status {status}: {error}"
            raise RuntimeError(msg)
        return None

    print(f"    polling {result_url} (timeout {timeout:.0f}s)")
    return _wait_until(check, f"{label} reaching a terminal status", timeout)


def _tail(text: str, limit: int = 500) -> str:
    cleaned = text.strip()
    return cleaned[-limit:] if len(cleaned) > limit else cleaned


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _step_train(state: _RunState) -> tuple[bool, str]:
    payload = {"parameters": {"alpha": 0.25, "l1_ratio": 0.8, "random_state": 7}}
    url = f"{state.args.dashboard_url}/api/runs/train/trigger"
    response = _post_json(url, payload)
    execution = response["execution"]
    result_url = _result_url(state.args.dashboard_url, response)
    _wait_for_terminal(result_url, f"train {execution}", state.args.timeout)
    return True, f"train execution {execution} finished SUCCESS"


def _step_newest_version(state: _RunState) -> tuple[bool, str]:
    name = state.args.model_name
    query = urlencode({"name": name})
    url = f"{state.args.mlflow_uri}/api/2.0/mlflow/registered-models/get-latest-versions?{query}"
    body = _get_json(url)
    versions = [int(entry["version"]) for entry in body.get("model_versions", [])]
    if not versions:
        msg = f"no registered versions found for model '{name}'"
        raise RuntimeError(msg)
    state.model_version = max(versions)
    return True, f"newest version of '{name}' is {state.model_version}"


def _step_evaluate(state: _RunState) -> tuple[bool, str]:
    payload = {
        "parameters": {
            "registered_name": state.args.model_name,
            "version": str(state.model_version),
            "data_source": state.args.eval_data_source,
            "experiment": state.args.evaluation_experiment,
            "max_rmse": state.args.eval_max_rmse,
        }
    }
    url = f"{state.args.dashboard_url}/api/runs/eval/trigger"
    response = _post_json(url, payload)
    execution = response["execution"]
    result_url = _result_url(state.args.dashboard_url, response)
    _wait_for_terminal(result_url, f"eval {execution}", state.args.timeout)
    return True, (
        f"evaluation {execution} passed for version {state.model_version} "
        f"(max_rmse={state.args.eval_max_rmse})"
    )


def _step_promote(state: _RunState) -> tuple[bool, str]:
    command = [
        sys.executable,
        str(PROMOTE_SCRIPT),
        "--backend",
        state.args.backend,
        "--model-name",
        state.args.model_name,
        "--version",
        str(state.model_version),
        "--evaluation-experiment",
        state.args.evaluation_experiment,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        output = _tail(completed.stdout + completed.stderr)
        return False, f"promote.py exited {completed.returncode}: {output}"
    return True, (
        f"promoted '{state.args.model_name}' version {state.model_version} "
        f"(backend={state.args.backend})"
    )


def _step_serving_ready(state: _RunState) -> tuple[bool, str]:
    expected_version = str(state.model_version)

    def check() -> dict[str, Any] | None:
        try:
            body = _get_json(f"{state.args.serving_url}/readyz")
        except HTTPError as exc:
            if exc.code == 503:
                return None  # still loading the model
            raise
        except URLError:
            return None  # container restarting after redeploy
        if body.get("status") != "ready":
            return None
        return body

    description = f"serving /readyz reporting version {expected_version}"
    body = _wait_until(check, description, state.args.timeout)
    reported_version = body.get("model_version")
    if reported_version != expected_version:
        msg = f"/readyz reports model_version={reported_version!r}, expected {expected_version!r}"
        raise RuntimeError(msg)
    reported_name = body.get("model_name")
    if reported_name != state.args.model_name:
        msg = f"/readyz reports model_name={reported_name!r}, expected {state.args.model_name!r}"
        raise RuntimeError(msg)
    return True, f"serving is ready on version {expected_version}"


def _step_prediction(state: _RunState) -> tuple[bool, str]:
    body = _post_json(
        f"{state.args.serving_url}/v1/predictions",
        {"instances": [[7.0, 0.27, 0.36, 20.7, 0.045, 45.0, 170.0, 1.001, 3.0, 0.45, 8.8]]},
    )
    predictions = body.get("predictions")
    if not isinstance(predictions, list) or len(predictions) != 1:
        return False, f"prediction response has unexpected predictions={predictions!r}"
    if body.get("model_version") != str(state.model_version):
        return False, (
            f"prediction response reports model_version={body.get('model_version')!r}, "
            f"expected {state.model_version!r}"
        )
    return True, "serving prediction endpoint returned one result for the promoted version"


def _step_batch(state: _RunState) -> tuple[bool, str]:
    payload = {"parameters": {"model_version": str(state.model_version)}}
    url = f"{state.args.dashboard_url}/api/runs/batch/trigger"
    response = _post_json(url, payload)
    execution = response["execution"]
    state.batch_execution = execution
    result_url = _result_url(state.args.dashboard_url, response)
    _wait_for_terminal(result_url, f"batch {execution}", state.args.timeout)
    return True, f"batch execution {execution} finished SUCCESS"


def _step_results_parent(state: _RunState) -> tuple[bool, str]:
    rows = _get_json(f"{state.args.dashboard_url}/api/results?limit=50")
    parent = next((row for row in rows if row.get("id") == state.batch_execution), None)
    if parent is None:
        detail = f"no results row for batch execution {state.batch_execution} in last 50"
        return False, detail
    if parent.get("status") != "SUCCESS":
        detail = f"parent row status is {parent.get('status')!r}, expected SUCCESS"
        return False, detail
    return True, f"results API shows parent row {parent['id']} as SUCCESS"


_STEPS: list[tuple[str, Callable[[_RunState], tuple[bool, str]]]] = [
    ("train: trigger and reach terminal status", _step_train),
    ("registry: resolve newest model version", _step_newest_version),
    ("evaluate: exact candidate passes threshold", _step_evaluate),
    ("promote: flip alias and redeploy serving", _step_promote),
    ("serving: readyz reports promoted version", _step_serving_ready),
    ("serving: prediction returns the promoted version", _step_prediction),
    ("batch: score pinned version to terminal", _step_batch),
    ("results API: parent row is SUCCESS", _step_results_parent),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dashboard-url",
        default="http://localhost:18000",
        help="dashboard base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--serving-url",
        default="http://localhost:18080",
        help="serving base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--mlflow-uri",
        default="http://localhost:15000",
        help="MLflow base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--backend",
        choices=("local", "aca"),
        default="local",
        help="promotion backend passed to promote.py (default: %(default)s)",
    )
    parser.add_argument(
        "--model-name", default="wine-quality", help="registered model name (default: %(default)s)"
    )
    parser.add_argument(
        "--eval-data-source",
        default=(
            "https://raw.githubusercontent.com/mlflow/mlflow/master/"
            "tests/datasets/winequality-white.csv"
        ),
        help="held-out CSV used by evaluation",
    )
    parser.add_argument(
        "--evaluation-experiment",
        default="wine-quality-eval",
        help="MLflow experiment containing evaluation evidence",
    )
    parser.add_argument(
        "--eval-max-rmse",
        type=float,
        default=0.8,
        help="maximum RMSE accepted by the promotion gate",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="per-phase wait budget in seconds (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.backend == "aca":
        raise SystemExit(
            "golden_path.py drives the local Compose stack only. For Azure, run "
            "deploy/smoke-tests.sh or deploy/smoke-tests.ps1; those adapters use "
            "the same terminal-status, readiness, prediction, and results checks."
        )

    state = _RunState(args=args)
    outcomes: list[tuple[str, str, str]] = []
    failed = False
    for label, step in _STEPS:
        if failed:
            outcomes.append((label, "SKIP", ""))
            continue
        print(f"\n==> {label}")
        # Broad catch on purpose: the suite must always reach its summary.
        try:
            ok, detail = step(state)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        status = "PASS" if ok else "FAIL"
        outcomes.append((label, status, detail))
        print(f"[{status}] {detail}")
        failed = not ok

    print("\n=== golden path summary ===")
    for label, status, detail in outcomes:
        line = f"  [{status:^4}] {label}"
        if detail and status != "SKIP":
            line += f": {detail}"
        print(line)
    all_passed = all(status == "PASS" for _, status, _ in outcomes)
    print("GOLDEN PATH: PASS" if all_passed else "GOLDEN PATH: FAIL")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
