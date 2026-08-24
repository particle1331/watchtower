import pytest

score = pytest.importorskip("batch_job.score")


def test_data_source_environment_fallback(monkeypatch) -> None:
    monkeypatch.setattr(score, "_DATA_SOURCE", "env.csv")
    args = score.parse_args([])
    assert args.data_source == "env.csv"


def test_cli_data_source_wins_over_environment(monkeypatch) -> None:
    monkeypatch.setattr(score, "_DATA_SOURCE", "env.csv")
    args = score.parse_args(["--data-source", "cli.csv"])
    assert args.data_source == "cli.csv"


def test_production_is_the_default_alias(monkeypatch) -> None:
    monkeypatch.setattr(score.mlflow.pyfunc, "load_model", lambda uri: uri)
    assert score._load_model("wine-quality", None) == "models:/wine-quality@production"
