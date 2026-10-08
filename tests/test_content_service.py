"""Domain, stale-write, and crash-recovery acceptance checks."""

from datetime import UTC, datetime

import nbformat
import pytest
import yaml

from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError, load_yaml


@pytest.fixture
def content_service(tmp_path):
    records = {
        "content/data/catalog.yaml": {"version": 1, "artifacts": []},
        "content/data/portfolio.yaml": {"version": 1, "entries": []},
        "content/data/photos.yaml": {"version": 1, "photos": []},
        "content/data/profile.yaml": {"version": 1, "name": "Test Author", "contact": {"phone": "123", "email": "a@example.org", "github": "example", "linkedin": "example"}, "summary": "Profile", "homepage_intro": [], "employment": [], "skills": [], "education": []},
        "frontend/site.yaml": {"version": 1},
    }
    for name, value in records.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value))
    return ContentService(tmp_path)


def post(service, **extra):
    return service.create({"id": "post/example", "kind": "post", "path": "content/notebooks/posts/example.ipynb", "title": "Example", "planned": {"content": "## Question\n\nInvestigate a question."}, **extra})


@pytest.mark.parametrize("kind", ["post", "personal", "portfolio", "course", "chapter"])
@pytest.mark.parametrize("timezone, expected_date", [("Asia/Manila", "2026-10-09"), ("UTC", "2026-10-08")])
def test_creation_date_uses_the_site_timezone(content_service, monkeypatch, kind, timezone, expected_date):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 8, 21, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("watchtower.services.content.datetime", FixedDatetime)
    settings = content_service.read_data("settings")["data"]
    content_service.update_data("settings", {**settings, "timezone": timezone})
    payload = {"id": f"{kind}/dated", "kind": kind, "title": "Dated"}
    if kind == "course":
        payload["path"] = "content/notebooks/courses/dated"
    elif kind == "chapter":
        content_service.create({"id": "course/parent", "kind": "course", "title": "Parent", "path": "content/notebooks/courses/parent"})
        payload.update(id="course/parent/dated", parent="course/parent", section="main", toc_title="Dated", path="content/notebooks/courses/parent/dated.ipynb")
    elif kind != "portfolio":
        payload["path"] = f"content/notebooks/{kind}/dated.ipynb"
    created = content_service.create(payload)
    assert created["artifact"]["date"] == expected_date
    content_service.update(payload["id"], {"description": "Updated later"})
    assert content_service.inspect(payload["id"])["artifact"]["date"] == expected_date


def test_creation_preserves_an_explicit_date(content_service):
    created = content_service.create({"id": "portfolio/dated", "kind": "portfolio", "title": "Dated", "date": "2025-12-31"})
    assert created["artifact"]["date"] == "2025-12-31"


def author_body(service, identifier):
    record = service.inspect(identifier)
    path = service.root / record["source_path"]
    notebook = nbformat.read(path, as_version=4)
    notebook.cells.append(nbformat.v4.new_markdown_cell("An authored explanation with an example."))
    nbformat.write(notebook, path)


def test_complete_post_workflow_preserves_outputs_and_tags(content_service):
    service = content_service
    created = post(service, tags=[" Test ", "test", "Science"])
    assert created["artifact"]["tags"] == ["Test", "Science"]
    path = service.root / "content/notebooks/posts/example.ipynb"
    assert not path.exists()
    assert service.snapshot().state.artifacts[0].lifecycle == "planned"
    service.start("post/example")
    notebook = nbformat.read(path, as_version=4)
    assert "---" not in notebook.cells[0].source
    notebook.cells.append(nbformat.v4.new_code_cell("#| echo: false\nprint(1)", outputs=[nbformat.v4.new_output("stream", name="stdout", text="1\n")], execution_count=1))
    nbformat.write(notebook, path)
    source = path.read_bytes()
    service.publish("post/example")
    service.draft("post/example")
    assert path.read_bytes() == source
    assert service.inspect("post/example")["artifact"]["tags"] == ["Test", "Science"]


def test_stale_clients_do_not_erase_fields(content_service):
    service = content_service
    token = post(service)["revision"]
    service.update("post/example", {"description": "First"}, token)
    with pytest.raises(ServiceError) as conflict:
        service.update("post/example", {"title": "Second"}, token)
    assert conflict.value.status == 412
    assert service.inspect("post/example")["artifact"]["description"] == "First"


def test_manual_planned_content_can_be_repaired(content_service):
    service = content_service
    post(service)
    path = service.root / "content/notebooks/posts/example.ipynb"
    path.parent.mkdir(parents=True)
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("Manual body")]), path)
    before = path.read_bytes()
    with pytest.raises(ServiceError):
        service.validate()
    service.update("post/example", {"lifecycle": "draft"})
    service.publish("post/example")
    assert path.read_bytes() == before


def test_invalid_final_state_never_writes(content_service):
    service = content_service
    post(service)
    before = (service.root / "content/data/catalog.yaml").read_bytes()
    with pytest.raises(ServiceError):
        service.publish("post/example")
    assert (service.root / "content/data/catalog.yaml").read_bytes() == before
    with pytest.raises(ServiceError):
        service.update("post/example", {"tags": [123]})
    assert (service.root / "content/data/catalog.yaml").read_bytes() == before


@pytest.mark.parametrize("stage,index", [("prepared", -1), ("installed", 0), ("installed", 1), ("recorded", 0), ("recorded", 1)])
def test_crash_recovery_is_idempotent(content_service, stage, index):
    service = content_service
    post(service)
    def crash(current_stage, current_index):
        if current_stage == stage and current_index == index:
            raise OSError("injected crash")
    service.store.fault = crash
    with pytest.raises((OSError, ServiceError)):
        service.start("post/example")
    recovered = ContentService(service.root)
    first = recovered.snapshot()
    second = recovered.snapshot()
    assert first.revision == second.revision
    assert first.state.artifacts[0].lifecycle == ("planned" if stage == "prepared" else "draft")


def test_external_change_blocks_recovery_and_preserves_versions(content_service):
    service = content_service
    post(service)
    def crash(stage, index):
        if stage == "installed" and index == 0:
            raise OSError("crash after catalog installation")
    service.store.fault = crash
    with pytest.raises(ServiceError):
        service.start("post/example")
    path = service.root / "content/data/catalog.yaml"
    path.write_text("External edit preserved\n")
    with pytest.raises(ServiceError) as error:
        ContentService(service.root).snapshot()
    assert error.value.code == "recovery_conflict"
    assert path.read_text() == "External edit preserved\n"
    assert list((service.root / "backend/runtime/transactions").glob("*/preimage-0"))
    assert list((service.root / "backend/runtime/transactions").glob("*/candidate-0"))


def test_ide_created_notebook_defeats_start(content_service):
    service = content_service
    post(service)
    source = service.root / "content/notebooks/posts/example.ipynb"
    def create_externally(stage, index):
        if stage == "prepared":
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"IDE content")
    service.store.fault = create_externally
    with pytest.raises(ServiceError):
        service.start("post/example")
    assert source.read_bytes() == b"IDE content"
    assert service.list()["artifacts"][0]["lifecycle"] == "planned"


def test_duplicate_yaml_and_wrong_version_are_actionable():
    with pytest.raises(ServiceError, match="parse YAML"):
        load_yaml(b"version: 1\nversion: 1\n", "test.yaml")
    with pytest.raises(ServiceError, match="unsupported"):
        load_yaml(b"version: true\n", "test.yaml")


def test_plan_file_is_persisted_and_confined(content_service):
    service = content_service
    plan = service.root / ".tmp/plan.md"
    plan.parent.mkdir()
    plan.write_text("## Arbitrary heading\n\nBody.")
    body = service.plan_file(".tmp/plan.md")
    post(service, planned={"content": body})
    plan.unlink()
    service.start("post/example")
    assert body == service.inspect("post/example")["artifact"]["planned"]["content"]
    assert nbformat.read(service.root / "content/notebooks/posts/example.ipynb", as_version=4).cells[0].source == "# Example\n"
    with pytest.raises(ServiceError):
        service.plan_file("frontend/site.yaml")


def test_course_parent_withdrawal_preserves_children(content_service):
    service = content_service
    service.create({"id": "course/example", "kind": "course", "title": "Example course", "path": "content/notebooks/courses/example", "contract": {"purpose": "Teach", "audience": "Learners", "planned": {"summary": "Build a working example.", "chapters": []}}})
    service.start("course/example")
    author_body(service, "course/example")
    service.publish("course/example")
    service.create({"id": "course/example/01", "kind": "chapter", "title": "Chapter", "toc_title": "01. Chapter", "section": "main", "parent": "course/example", "path": "content/notebooks/courses/example/01.ipynb", "planned_content": "Topic", "planned_lab_and_evidence": "Check"})
    service.start("course/example/01")
    author_body(service, "course/example/01")
    service.publish("course/example/01")
    body = (service.root / "content/notebooks/courses/example/01.ipynb").read_bytes()
    result = service.draft("course/example")
    assert result["affected_children"] == [{"id": "course/example/01", "eligible": False}]
    assert service.inspect("course/example/01")["artifact"]["lifecycle"] == "published"
    assert (service.root / "content/notebooks/courses/example/01.ipynb").read_bytes() == body
    service.validate()


def test_chapter_move_and_title_update_preserve_outputs(content_service):
    service = content_service
    service.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example", "contract": {"toc": [{"id": "a", "title": "A", "chapters": []}, {"id": "b", "title": "B", "chapters": []}]}})
    service.create({"id": "course/example/01", "kind": "chapter", "title": "Chapter", "toc_title": "01", "section": "a", "parent": "course/example", "path": "content/notebooks/courses/example/01.ipynb", "planned_content": "Body", "planned_lab_and_evidence": "Check"})
    service.start("course/example/01")
    service.update("course/example/01", {"section": "b", "title": "New title"})
    result = service.read_data("course/example")["data"]
    assert result["toc"][0]["chapters"] == []
    assert result["toc"][1]["chapters"] == ["course/example/01"]
    assert result["planned"]["chapters"][0]["section"] == "b"
    assert nbformat.read(service.root / "content/notebooks/courses/example/01.ipynb", as_version=4).cells[0].source.startswith("# New title")
