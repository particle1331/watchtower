"""Stable-ID plan reads expose saved authoring context without changing content."""
import json

import pytest
from test_content_service import author_body
from test_content_service import content_service as content_service
from typer.testing import CliRunner

from watchtower.cli import app
from watchtower.services.workspace import ServiceError


def read_plan(monkeypatch, service, identifier):
    monkeypatch.chdir(service.root)
    before = service.store.inputs()
    result = CliRunner().invoke(app, ["plan", identifier])
    assert result.exit_code == 0, (result.output, result.exception)
    assert service.store.inputs() == before
    return json.loads(result.output)


@pytest.mark.parametrize("kind", ["post", "personal", "course", "chapter", "portfolio"])
def test_plan_reads_effective_record_and_internal_notes(content_service, monkeypatch, kind):
    service = content_service
    identifier = f"{kind}/example"
    fields = {"content": "## Research\n\nKeep **Markdown** and λ.", "extension": "Preserve legacy details"}
    payload = {"id": identifier, "kind": kind, "title": "Example", "internal_notes": "A question\n\n- Investigate"}
    if kind in {"course", "chapter"}:
        service.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example", "internal_notes": "Parent notes", "contract": {"purpose": "Teach", "audience": "Readers", "planned": {**fields, "summary": "Course plan", "chapters": []}}})
        if kind == "course":
            service.update(identifier, {"internal_notes": payload["internal_notes"]})
            fields = {**fields, "summary": "Course plan", "chapters": [], "purpose": "Teach", "audience": "Readers"}
        else:
            identifier = "course/example/first"
            payload.update(id=identifier, path="content/notebooks/courses/example/first.ipynb", parent="course/example", section="main", toc_title="First", plan=fields)
            service.create(payload)
            fields = {**fields, "chapter_id": identifier, "section": "main", "lab_and_evidence": ""}
    elif kind == "portfolio":
        service.create({**payload, "detail": {"planned": fields}})
    else:
        service.create({**payload, "path": f"content/notebooks/{kind}/example.ipynb", "planned": fields})
    result = read_plan(monkeypatch, service, identifier)
    assert result["id"] == identifier
    assert result["kind"] == kind
    assert result["plan"] == fields
    assert result["internal_notes"] == payload["internal_notes"]
    inspected = service.inspect(identifier)
    assert result["build_brief"] == inspected["build_brief"]
    assert result["revision"] == inspected["revision"]
    assert not inspected["has_source"]
    if kind == "chapter":
        assert "Parent notes" in result["build_brief"]


def test_plan_remains_available_after_start_and_publish(content_service, monkeypatch):
    service = content_service
    service.create_post("example", {"title": "Example", "internal_notes": "Research"})
    planned = read_plan(monkeypatch, service, "post/example")
    assert planned["plan"] == {}
    assert planned["lifecycle"] == "planned"
    service.start("post/example")
    draft = read_plan(monkeypatch, service, "post/example")
    assert draft["lifecycle"] == "draft"
    author_body(service, "post/example")
    service.publish("post/example")
    published = read_plan(monkeypatch, service, "post/example")
    assert published["lifecycle"] == "published"
    assert published["plan"] == planned["plan"]
    assert published["internal_notes"] == "Research"
    assert "An authored explanation" not in published["build_brief"]


def test_course_plan_brief_follows_toc_order(content_service, monkeypatch):
    service = content_service
    service.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example"})
    for name in ["second", "first"]:
        service.create({"id": f"course/example/{name}", "kind": "chapter", "title": name.title(), "path": f"content/notebooks/courses/example/{name}.ipynb", "parent": "course/example", "section": "main", "toc_title": name, "planned_content": f"Plan for {name}", "internal_notes": f"Notes for {name}"})
    service.organize_course("course/example", "chapter-up", {"chapter": "course/example/first"}, service.inspect("course/example")["revision"])
    result = read_plan(monkeypatch, service, "course/example")
    assert result["build_brief"].index("# First") < result["build_brief"].index("# Second")
    assert "Notes for first" in result["build_brief"]
    assert "Plan for second" in result["build_brief"]


@pytest.mark.parametrize("identifier", ["post/missing", "example", "Example", "content/notebooks/posts/example.ipynb"])
def test_plan_requires_an_exact_registered_id(content_service, monkeypatch, identifier):
    service = content_service
    service.create_post("example", {"title": "Example"})
    monkeypatch.chdir(service.root)
    before = service.store.inputs()
    result = CliRunner().invoke(app, ["plan", identifier])
    assert result.exit_code == 1
    assert isinstance(result.exception, ServiceError)
    assert result.exception.code == "not_found"
    assert identifier in str(result.exception)
    assert service.store.inputs() == before
