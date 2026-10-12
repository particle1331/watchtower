"""The context command exposes an active plan only while an artifact is Planned."""
import json

import pytest
from test_content_service import author_body
from test_content_service import content_service as content_service
from typer.testing import CliRunner

from watchtower.cli import app


def read_context(monkeypatch, service, identifier):
    monkeypatch.chdir(service.root)
    before = service.store.inputs()
    result = CliRunner().invoke(app, ["context", identifier])
    assert result.exit_code == 0, (result.output, result.exception)
    assert service.store.inputs() == before
    return json.loads(result.output)


@pytest.mark.parametrize("kind", ["post", "personal", "course", "chapter", "portfolio"])
def test_context_reads_lifecycle_and_effective_plan(content_service, monkeypatch, kind):
    service = content_service
    identifier = f"{kind}/example"
    fields = {"content": "## Research\n\nKeep **Markdown** and λ.", "extension": "Preserve legacy details"}
    payload = {"id": identifier, "kind": kind, "title": "Example", "internal_notes": ""}
    if kind in {"course", "chapter"}:
        service.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example", "contract": {"purpose": "Teach", "audience": "Readers", "planned": {**fields, "summary": "Course plan", "chapters": []}}})
        if kind == "course":
            service.update(identifier, {"internal_notes": payload["internal_notes"]})
        else:
            identifier = "course/example/first"
            payload.update(id=identifier, path="content/notebooks/courses/example/first.ipynb", parent="course/example", section="main", toc_title="First", plan=fields)
            service.create(payload)
    elif kind == "portfolio":
        service.create({**payload, "detail": {"planned": fields}})
    else:
        service.create({**payload, "path": f"content/notebooks/{kind}/example.ipynb", "planned": fields})

    result = read_context(monkeypatch, service, identifier)
    assert result["artifact"]["id"] == identifier
    assert result["artifact"]["kind"] == kind
    assert result["lifecycle"] == "planned"
    assert result["revision"] == service.inspect(identifier)["revision"]
    assert all(result["plan"].get(key) == value for key, value in fields.items())
    assert result["artifact"]["internal_notes"] == ""
    assert result["plan_fields"]
    assert all(field["section"] != "internal" for field in result["plan_fields"])
    assert not service.inspect(identifier)["has_source"]


def test_context_hides_consumed_plan_after_start_and_publish(content_service, monkeypatch):
    service = content_service
    service.create_post("example", {"title": "Example", "planned": {"content": "Initial outline"}})
    planned = read_context(monkeypatch, service, "post/example")
    assert planned["plan"] == {"content": "Initial outline"}
    assert planned["lifecycle"] == "planned"
    service.start("post/example")
    service.update("post/example", {"internal_notes": "Research"})
    draft = read_context(monkeypatch, service, "post/example")
    assert draft["lifecycle"] == "draft"
    assert "plan" not in draft and "plan_fields" not in draft
    assert draft["artifact"]["internal_notes"] == "Research"
    author_body(service, "post/example")
    service.publish("post/example")
    published = read_context(monkeypatch, service, "post/example")
    assert published["lifecycle"] == "published"
    assert "plan" not in published
    assert "Initial outline" not in json.dumps(published)
    assert published["artifact"]["internal_notes"] == "Research"


def test_course_context_plan_follows_toc_order(content_service, monkeypatch):
    service = content_service
    service.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example"})
    for name in ["second", "first"]:
        service.create({"id": f"course/example/{name}", "kind": "chapter", "title": name.title(), "path": f"content/notebooks/courses/example/{name}.ipynb", "parent": "course/example", "section": "main", "toc_title": name, "planned_content": f"Plan for {name}"})
    service.organize_course("course/example", "chapter-up", {"chapter": "course/example/first"}, service.inspect("course/example")["revision"])
    result = read_context(monkeypatch, service, "course/example")
    assert [chapter["chapter_id"] for chapter in result["plan"]["chapters"]] == ["course/example/first", "course/example/second"]


def test_plan_command_is_retired(content_service, monkeypatch):
    service = content_service
    service.create_post("example", {"title": "Example", "planned": {"content": "Initial outline"}})
    monkeypatch.chdir(service.root)
    result = CliRunner().invoke(app, ["plan", "post/example"])
    assert result.exit_code != 0
    assert "No such command 'plan'" in result.output
