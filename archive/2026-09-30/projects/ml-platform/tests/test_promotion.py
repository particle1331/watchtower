from types import SimpleNamespace

import pytest
from demo.promote import _parse_args, _require_passing_evaluation, _restore_alias


def test_tracking_uri_can_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://cloud.example/mlflow")
    args = _parse_args(["--version", "3"])
    assert args.tracking_uri == "https://cloud.example/mlflow"


def test_explicit_tracking_uri_overrides_environment(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://cloud.example/mlflow")
    args = _parse_args(["--tracking-uri", "http://localhost:15000", "--version", "3"])
    assert args.tracking_uri == "http://localhost:15000"


class _FakeClient:
    def __init__(self, runs: list[object], *, experiment_exists: bool = True):
        self.runs = runs
        self.experiment_exists = experiment_exists
        self.search_kwargs: dict[str, object] = {}
        self.alias_updates: list[tuple[str, str, str]] = []
        self.alias_deletes: list[tuple[str, str]] = []

    def get_experiment_by_name(self, _name: str):
        if not self.experiment_exists:
            return None
        return SimpleNamespace(experiment_id="eval-experiment-id")

    def search_runs(self, **kwargs):
        self.search_kwargs = kwargs
        return self.runs

    def set_registered_model_alias(self, name: str, alias: str, version: str) -> None:
        self.alias_updates.append((name, alias, version))

    def delete_registered_model_alias(self, name: str, alias: str) -> None:
        self.alias_deletes.append((name, alias))


def test_promotion_gate_requires_a_passing_eval_for_exact_version() -> None:
    client = _FakeClient([SimpleNamespace(info=SimpleNamespace(run_id="eval-run"))])

    _require_passing_evaluation(client, "wine-quality", 7, "wine-quality-eval")

    assert "models:/wine-quality/7" in str(client.search_kwargs["filter_string"])
    assert "eval.passed" in str(client.search_kwargs["filter_string"])


def test_promotion_gate_rejects_unevaluated_version() -> None:
    client = _FakeClient([])

    with pytest.raises(RuntimeError, match="No passing evaluation"):
        _require_passing_evaluation(client, "wine-quality", 8, "wine-quality-eval")


def test_failed_deploy_can_restore_previous_alias() -> None:
    client = _FakeClient([])

    _restore_alias(client, "wine-quality", "6")

    assert client.alias_updates == [("wine-quality", "production", "6")]


def test_failed_first_deploy_removes_new_alias() -> None:
    client = _FakeClient([])

    _restore_alias(client, "wine-quality", None)

    assert client.alias_deletes == [("wine-quality", "production")]
