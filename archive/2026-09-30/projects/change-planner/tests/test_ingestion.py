from pathlib import Path

from change_planner.ingestion import ingest_repository


def test_ingestion_extracts_python_symbols_and_revision_metadata(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "service.py").write_text(
        "def deploy():\n    return True\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_service.py").write_text(
        "from service import deploy\n\ndef test_deploy():\n    assert deploy()\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("Deployment service.\n", encoding="utf-8")

    indexed = ingest_repository(tmp_path, repository="fixture/service", revision="abc123")

    service = indexed.catalog.get("fixture/service:src/service.py")
    test = indexed.catalog.get("fixture/service:tests/test_service.py")
    assert service.source_kind == "code"
    assert service.symbols == ["deploy"]
    assert test.source_kind == "test"
    assert test.id in service.related_tests
    assert indexed.snapshot.revision == "abc123"
    assert indexed.snapshot.source_fingerprint.startswith("sha256:")


def test_ingestion_excludes_build_artifacts_and_is_content_sensitive(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("ignored = True\n", encoding="utf-8")

    first = ingest_repository(tmp_path, repository="fixture/app", revision="abc123")
    (tmp_path / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    second = ingest_repository(tmp_path, repository="fixture/app", revision="abc123")

    assert [source.path for source in first.catalog.sources.values()] == ["app.py"]
    assert first.snapshot.source_fingerprint != second.snapshot.source_fingerprint
