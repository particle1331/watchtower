import pytest

runner = pytest.importorskip("demo.runner.app")


def test_runner_overrides_shared_batch_arguments() -> None:
    command = runner._command_for(
        "batch", {"data_source": "fixture.csv", "model_version": "7"}
    )
    assert command[command.index("--data-source") + 1] == "fixture.csv"
    assert command[command.index("--model-version") + 1] == "7"


def test_runner_rejects_unknown_parameters() -> None:
    with pytest.raises(runner.HTTPException, match="Unsupported parameters"):
        runner._command_for("train", {"shell": "echo unsafe"})


def test_runner_rejects_non_scalar_parameters() -> None:
    with pytest.raises(runner.HTTPException, match="must be a scalar"):
        runner._command_for("batch", {"chunk_size": [100]})
