import pytest

runner = pytest.importorskip("demo.runner.app")


def test_runner_overrides_shared_batch_arguments() -> None:
    command = runner._command_for("batch", {"data_source": "fixture.csv", "model_version": "7"})
    assert command[command.index("--data-source") + 1] == "fixture.csv"
    assert command[command.index("--model-version") + 1] == "7"


def test_runner_builds_evaluation_command_for_exact_version() -> None:
    command = runner._command_for(
        "eval", {"registered_name": "wine-quality", "version": "7", "max_rmse": 0.7}
    )
    assert command[command.index("--version") + 1] == "7"
    assert command[command.index("--max-rmse") + 1] == "0.7"


def test_runner_rejects_unknown_parameters() -> None:
    with pytest.raises(runner.HTTPException, match="Unsupported parameters"):
        runner._command_for("train", {"shell": "echo unsafe"})


def test_runner_rejects_non_scalar_parameters() -> None:
    with pytest.raises(runner.HTTPException, match="must be a scalar"):
        runner._command_for("batch", {"chunk_size": [100]})


def test_runner_accepts_concurrent_parameterized_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple[str, str, dict[str, object]]] = []

    def record_start(
        execution: str,
        job_name: str,
        triggered_by: str,
        parameters: dict[str, object],
    ) -> None:
        started.append((execution, job_name, parameters))

    monkeypatch.setattr(runner, "_execute", record_start)
    runner._jobs.clear()

    try:
        first = runner.run_job("train", {"alpha": 0.1})
        second = runner.run_job("train", {"alpha": 0.9})

        assert first["execution"] != second["execution"]
        assert len(runner._jobs) == 2
        assert runner._jobs[first["execution"]]["parameters"] == {"alpha": 0.1}
        assert runner._jobs[second["execution"]]["parameters"] == {"alpha": 0.9}
    finally:
        runner._jobs.clear()
