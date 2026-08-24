from demo.promote import _parse_args


def test_tracking_uri_can_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://cloud.example/mlflow")
    args = _parse_args(["--version", "3"])
    assert args.tracking_uri == "https://cloud.example/mlflow"


def test_explicit_tracking_uri_overrides_environment(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://cloud.example/mlflow")
    args = _parse_args(["--tracking-uri", "http://localhost:15000", "--version", "3"])
    assert args.tracking_uri == "http://localhost:15000"
