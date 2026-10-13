"""Starting consumes authoring intent; notebooks and draft notes then own the work."""
import html
import json

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.services.build import _Generator
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def entry(author, kind, **extra):
    identifier = f"{kind}/authority"
    data = {"id": identifier, "kind": kind, "title": "Authority", **extra}
    if kind == "course":
        data.update(path="content/notebooks/courses/authority", contract={"planned": {"description": "INITIAL-INTENT", "prerequisites": "Readers"}})
    elif kind == "chapter":
        author.create({"id": "course/parent", "kind": "course", "title": "Parent", "path": "content/notebooks/courses/parent", "contract": {"purpose": "PARENT-INTENT"}})
        author.start("course/parent")  # Chapters may leave Planned only after their course has started.
        identifier = "course/parent/authority"
        data.update(id=identifier, parent="course/parent", section="main", toc_title="Authority",
                    path="content/notebooks/courses/parent/authority.ipynb", plan={"content": "INITIAL-INTENT", "summary": "Public summary"})
    elif kind == "portfolio":
        data["detail"] = {"abstract": "Public summary", "planned": {"introduction": "INITIAL-INTENT"}}
    else:
        data.update(path=f"content/notebooks/{kind}/authority.ipynb", planned={"content": "INITIAL-INTENT"})
    return identifier, data


def test_planned_course_keeps_notes_and_todos_while_refining_the_home(author):
    identifier, data = entry(author, "course", internal_notes="Refine the outcome", internal_todos=[{"text": "Check the prerequisites", "done": False}])
    author.create(data)
    assert author.read_plan(identifier)["internal_notes"] == "Refine the outcome"
    author.update(identifier, {"internal_notes": "Later decision", "internal_todos": [{"text": "Check the prerequisites", "done": True}]})
    assert author.read_plan(identifier)["internal_notes"] == "Later decision"
    assert author.read_plan(identifier)["internal_todos"] == [{"text": "Check the prerequisites", "done": True}]


@pytest.mark.parametrize("kind", ["post", "personal", "portfolio", "chapter"])
@pytest.mark.parametrize("notes", [None, "", "An unfinished decision"])
def test_planned_notes_are_empty_or_rejected_atomically(author, kind, notes):
    identifier, data = entry(author, kind, internal_notes=notes)
    before = author.store.inputs()
    if notes:
        with pytest.raises(ServiceError, match="planned entries cannot have internal notes"):
            author.create(data)
        assert author.store.inputs() == before
    else:
        author.create(data)
        assert author.read_plan(identifier)["internal_notes"] == ""
        with pytest.raises(ServiceError, match="planned entries cannot have internal notes"):
            author.update(identifier, {"internal_notes": "A question"})
        assert author.read_plan(identifier)["internal_notes"] == ""


@pytest.mark.parametrize("kind", ["post", "personal", "portfolio", "course", "chapter"])
def test_started_context_and_cms_hide_consumed_intent(author, monkeypatch, kind):
    identifier, data = entry(author, kind)
    author.create(data)
    assert "INITIAL-INTENT" in author.read_plan(identifier)["build_brief"]
    author.start(identifier)
    notes = "## Notes\n\nCheck the example.\n\n## To-dos\n\n- [ ] Add evidence\n- [x] Choose the audience"
    source = author.root / (author.inspect(identifier)["source_path"] or f"backend/data/courses/{identifier.split('/')[-1]}.yaml")
    before = source.read_bytes()
    author.update(identifier, {"internal_notes": notes})
    assert source.read_bytes() == before
    context = author.read_plan(identifier)
    assert context["plan"] == {}
    assert context["internal_notes"] == notes
    assert all(field["section"] != "plan" for field in context["fields"])
    assert ("INITIAL-INTENT" in context["build_brief"]) == (kind == "course")
    assert f".venv/bin/wt {'context' if kind == 'course' else 'cat'} {identifier}" in context["build_brief"]
    assert author.inspect(identifier)["plan"] == ""
    with TestClient(create_app(author.root)) as client:
        page = client.get(f"/cms/artifact/{identifier}")
        assert page.status_code == 200
        assert 'id="plan" class="author-section' not in page.text
        assert ("INITIAL-INTENT" in html.unescape(page.text)) == (kind == "course")
        assert 'name="field:[&#34;internal_notes&#34;]"' in page.text
        assert "To-dos" in page.text
        if kind == "course":
            advanced = client.get("/cms/data/course/authority", follow_redirects=False)
            assert advanced.status_code == 303
        if kind == "portfolio":
            assert "INITIAL-INTENT" not in client.get("/cms/data/portfolio").text
        revision, snapshot = form_snapshot(page)
        rejected = client.post(f"/cms/save/{identifier}", data={"revision": revision, "snapshot": snapshot,
                              'field:["internal_notes"]': "Edited", 'field:["lifecycle"]': "planned"})
        assert rejected.status_code == 422
        assert author.read_plan(identifier)["internal_notes"] == notes
    monkeypatch.chdir(author.root)
    result = CliRunner().invoke(app, ["context", identifier])
    assert result.exit_code == 0, result.exception
    assert ("INITIAL-INTENT" in result.output) == (kind == "course")
    context_result = json.loads(result.output)
    assert context_result["lifecycle"] == "draft"
    assert "plan" not in context_result
    assert source.read_bytes() == before


@pytest.mark.parametrize("surface", ["service", "api", "cli", "batch"])
def test_consumed_plan_writes_are_rejected_through_every_surface(author, monkeypatch, surface):
    author.create_post("authority", {"title": "Authority", "planned": {"content": "Initial"}})
    author.start("post/authority")
    before = author.store.inputs()
    patch = {"planned": {"content": "Later"}}
    if surface == "service":
        with pytest.raises(ServiceError, match="plan has been consumed"):
            author.update("post/authority", patch)
    elif surface == "batch":
        with pytest.raises(ServiceError, match="plan has been consumed"):
            author.batch([{"id": "post/authority", "patch": patch}], {})
    elif surface == "api":
        with TestClient(create_app(author.root)) as client:
            result = client.patch("/api/artifacts/post/authority", headers={"If-Match": author.inspect("post/authority")["revision"]}, json=patch)
            assert result.status_code == 422
            assert "plan has been consumed" in result.text
    else:
        monkeypatch.chdir(author.root)
        result = CliRunner().invoke(app, ["update", "post/authority", "--planned-content", "Later"])
        assert result.exit_code == 1
        assert isinstance(result.exception, ServiceError)
    assert author.store.inputs() == before


@pytest.mark.parametrize("kind", ["portfolio", "course", "chapter"])
def test_structured_data_cannot_change_consumed_intent(author, kind):
    identifier, data = entry(author, kind)
    author.create(data)
    author.start(identifier)
    name = "portfolio" if kind == "portfolio" else "course/authority" if kind == "course" else "course/parent"
    record = author.read_data(name)
    if kind == "portfolio":
        record["data"]["entries"][0]["planned"] = {"introduction": "Changed"}
    elif kind == "course":
        record["data"]["planned"]["description"] = "Changed"
    else:
        record["data"]["planned"]["chapters"][0]["content"] = "Changed"
    before = author.store.inputs()
    with pytest.raises(ServiceError, match="plan has been consumed"):
        author.update_data(name, record["data"], record["revision"])
    assert author.store.inputs() == before
    patch = {"detail": {"abstract": "Public sentence"}} if kind == "portfolio" else {"plan": {"summary": "Public sentence"}} if kind == "chapter" else {"description": "Public sentence"}
    author.update(identifier, patch)
    assert author.read_plan(identifier)["summary"] == "Public sentence"


def test_started_course_hides_parent_intent_and_actualized_while_preserving_navigation(author):
    identifier, data = entry(author, "chapter")
    author.create(data)
    author.update("course/parent", {"contract": {"actualized": {"summary": "LEGACY-COMPLETION"}}})
    author.start(identifier)
    snapshot = author.snapshot()
    course = next(a for a in snapshot.state.artifacts if a.id == "course/parent")
    generated = _Generator(snapshot, author.root / ".tmp/generation", "preview").context(course)
    assert "Actualized" not in generated and "LEGACY-COMPLETION" not in generated
    assert "Course path" in generated and "Public summary" in generated
    assert "PARENT-INTENT" not in author.read_plan(identifier)["build_brief"]
    assert "actualized" not in author.inspect("course/parent")["contract"]
    author.organize_course("course/parent", "rename-section", {"section": "main", "title": "New section"}, snapshot.revision)
    assert author.inspect("course/parent")["contract"]["toc"][0]["title"] == "New section"


def test_cms_creation_rejects_hidden_notes_even_with_start_draft(author):
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/new?kind=post")
        assert 'name="field:[&#34;internal_notes&#34;]"' not in page.text
        import re
        token = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        before = author.store.inputs()
        result = client.post("/cms/new?kind=post", data={"revision": token, 'field:["title"]': "Forged",
                             'field:["internal_notes"]': "Hidden note", "start_draft": "1"})
        assert result.status_code == 422
        assert author.store.inputs() == before


def test_portfolio_data_saves_keep_consumed_plan_out_of_response_and_snapshot(author):
    identifier, data = entry(author, "portfolio")
    author.create(data)
    author.start(identifier)
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/data/portfolio")
        revision, snapshot = form_snapshot(page)
        assert "INITIAL-INTENT" not in snapshot
        saved = client.post("/cms/data/portfolio", data={"revision": revision, "snapshot": snapshot,
                            'field:["entries", 0, "abstract"]': "Revised public summary"})
        assert saved.status_code == 200, saved.text
        assert "INITIAL-INTENT" not in saved.text
        assert author.read_plan(identifier)["summary"] == "Revised public summary"
        assert "planned" not in author.read_data("portfolio")["data"]["entries"][0]
        stale = client.post("/cms/data/portfolio", data={"revision": revision, "snapshot": snapshot,
                            'field:["entries", 0, "abstract"]': "Unsaved public summary"})
        assert stale.status_code == 412
        assert "INITIAL-INTENT" not in stale.text
        assert "Unsaved public summary" in stale.text


def test_published_context_keeps_notes_and_never_restores_the_plan(author, monkeypatch):
    author.create_post("authority", {"title": "Authority", "planned": {"content": "Initial intent"}})
    author.start("post/authority")
    author.update("post/authority", {"internal_notes": "## To-dos\n\n- [ ] A later revision"})
    author.publish("post/authority")
    monkeypatch.chdir(author.root)
    result = CliRunner().invoke(app, ["context", "post/authority"])
    assert result.exit_code == 0
    context = json.loads(result.output)
    assert context["lifecycle"] == "published"
    assert "plan" not in context
    assert "Initial intent" not in result.output
    assert context["artifact"]["internal_notes"].endswith("- [ ] A later revision")
