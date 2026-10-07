"""Portfolio starts and make project share a transactional uv package scaffold."""

import runpy
import tomllib
from pathlib import Path

import nbformat
import pytest
from test_content_service import content_service as content_service

from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


def planned_portfolio(service, name=None):
    return service.create({"id": "portfolio/future", "kind": "portfolio", "title": "Future project",
        "detail": {"project_name": name, "planned": {"introduction": "The problem.", "what_it_contains": "The implementation."}}})


@pytest.mark.parametrize("name", [None, "custom-package"])
def test_start_portfolio_creates_notebook_package_and_registration(content_service, name):
    service = content_service
    created = planned_portfolio(service, name)
    result = service.start("portfolio/future", expected_revision=created["revision"])
    name = name or "future"
    assert result["project_path"] == f"projects/{name}"
    assert result["artifact"]["lifecycle"] == "draft"
    config = tomllib.loads((service.root / f"projects/{name}/pyproject.toml").read_text())
    assert config["project"]["name"] == name
    assert (service.root / f"projects/{name}/src/{name.replace('-', '_')}/__init__.py").exists()
    assert (service.root / f"projects/{name}/README.md").exists()
    notebook = nbformat.read(service.root / "content/notebooks/portfolio/future.ipynb", as_version=4)
    assert notebook.cells[0].source == "# Future project\n"
    assert "The implementation." in service.inspect("portfolio/future")["build_brief"]
    assert f"projects/{name}" in service.inspect("portfolio/future")["build_brief"]
    record = service.inspect("portfolio/future")
    assert record["detail"]["project_name"] == name
    assert record["detail"]["notebook_path"] == "content/notebooks/portfolio/future.ipynb"
    assert service.inspect(f"project/{name}")["artifact"]["path"] == f"projects/{name}"
    assert not any(path.startswith("projects/") for path in service.snapshot().files)
    service.validate()
    with pytest.raises(ServiceError, match="requires a planned"):
        service.start("portfolio/future")


def test_start_reuses_existing_project_without_changing_code(content_service):
    service = content_service
    project = service.root / "projects/future"
    project.mkdir(parents=True)
    code = project / "custom.py"
    code.write_text("# Existing code\n")
    service.create({"id": "project/custom-id", "kind": "project", "title": "Existing", "path": "projects/future"})
    planned_portfolio(service)
    service.start("portfolio/future")
    assert code.read_text() == "# Existing code\n"
    assert list(project.iterdir()) == [code]
    projects = [artifact for artifact in service.list()["artifacts"] if artifact["kind"] == "project"]
    assert [artifact["id"] for artifact in projects] == ["project/custom-id"]


@pytest.mark.parametrize("stage", ["prepared", "installed"])
def test_project_and_notebook_recover_together_after_interruption(content_service, stage):
    service = content_service
    planned_portfolio(service)
    def crash(current_stage, index):
        if current_stage == stage and (stage == "prepared" or index == 0):
            raise OSError("injected interruption")
    service.store.fault = crash
    with pytest.raises((ServiceError, OSError)):
        service.start("portfolio/future")
    recovered = ContentService(service.root)
    state = recovered.snapshot().state
    artifact = next(artifact for artifact in state.artifacts if artifact.id == "portfolio/future")
    assert artifact.lifecycle == ("planned" if stage == "prepared" else "draft")
    assert (service.root / "projects/future/pyproject.toml").exists() == (stage != "prepared")
    assert (service.root / "content/notebooks/portfolio/future.ipynb").exists() == (stage != "prepared")
    recovered.validate()


def test_external_project_edit_blocks_recovery_without_overwriting_code(content_service):
    service = content_service
    planned_portfolio(service)
    def crash(stage, index):
        if stage == "installed" and index == 0:
            raise OSError("interrupted after first package file")
    service.store.fault = crash
    with pytest.raises(ServiceError):
        service.start("portfolio/future")
    written = next(path for path in (service.root / "projects/future").rglob("*") if path.is_file())
    written.write_bytes(b"External edit must survive")
    with pytest.raises(ServiceError, match="external edit"):
        ContentService(service.root).snapshot()
    assert written.read_bytes() == b"External edit must survive"
    assert not (service.root / "content/notebooks/portfolio/future.ipynb").exists()


def test_stale_start_and_failed_scaffold_write_no_project_or_notebook(content_service, monkeypatch):
    service = content_service
    old = planned_portfolio(service)["revision"]
    service.update("portfolio/future", {"description": "A newer saved change"}, expected_revision=old)
    with pytest.raises(ServiceError, match="stale workspace"):
        service.start("portfolio/future", expected_revision=old)
    original = service.snapshot().files
    def fail(*args):
        raise ServiceError("uv initialization failed")
    monkeypatch.setattr("watchtower.services.content.scaffold_project", fail)
    with pytest.raises(ServiceError, match="uv initialization failed"):
        service.start("portfolio/future", expected_revision=service.inspect("portfolio/future")["revision"])
    assert service.snapshot().files == original
    assert not (service.root / "projects/future").exists()
    assert not (service.root / "content/notebooks/portfolio/future.ipynb").exists()


def test_make_project_uses_the_shared_scaffold_and_refuses_existing_code(content_service, monkeypatch):
    function = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/project.py"))["new_project"]
    function.__globals__["ROOT_PATH"] = content_service.root
    monkeypatch.setenv("NAME", "make-example")
    path = function()
    assert path == content_service.root / "projects/make-example"
    assert (path / "pyproject.toml").exists()
    content_service.validate()
    original = {str(item.relative_to(path)): item.read_bytes() for item in path.rglob("*") if item.is_file()}
    with pytest.raises(ServiceError, match="refuses an existing"):
        function()
    assert {str(item.relative_to(path)): item.read_bytes() for item in path.rglob("*") if item.is_file()} == original
