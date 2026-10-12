"""Entity checklists share the editor save without affecting notebooks or task memory."""
import json

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot
from test_plan_authority import entry
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


@pytest.mark.parametrize("kind", ["post", "portfolio", "course", "chapter", "personal"])
def test_editor_saves_notes_and_checklist_add_check_remove_together(author, kind):
    identifier, data = entry(author, kind)
    author.create(data)
    author.start(identifier)
    source = author.root / (author.inspect(identifier)["source_path"] or f"backend/data/courses/{identifier.split('/')[-1]}.yaml")
    notebook = source.read_bytes()
    with TestClient(create_app(author.root)) as client:
        editor = client.get(f"/cms/artifact/{identifier}")
        assert 'data-todo-editor' in editor.text
        assert 'name="todo_new"' in editor.text
        revision, snapshot = form_snapshot(editor)
        result = client.post(f"/cms/save/{identifier}", data={
            "revision": revision, "snapshot": snapshot,
            'field:["internal_notes"]': "Questions and decisions stay here.",
            "todos_present": "1", "todo_text": [f"Item {i}" for i in range(7)],
            "todo_done": [str(i) for i in range(7)], "todo_new": "  Last item  ",
        }, follow_redirects=False)
        assert result.status_code in {200, 303}, result.text
        record = author.read_plan(identifier)
        assert record["internal_notes"] == "Questions and decisions stay here."
        assert record["internal_todos"] == [*({"text": f"Item {i}", "done": True} for i in range(7)), {"text": "Last item", "done": False}]
        assert "Internal to-dos (7/8)" in record["build_brief"]
        editor = client.get(f"/cms/artifact/{identifier}")
        assert '>7/8</span>' in editor.text
        revision, snapshot = form_snapshot(editor)
        # This is also the native form path: remove on save and absent checkboxes mean unchecked.
        result = client.post(f"/cms/save/{identifier}", data={
            "revision": revision, "snapshot": snapshot, "todos_present": "1",
            "todo_text": [f"Item {i}" for i in range(7)] + ["Last item"],
            "todo_done": ["0", "1", "3", "4", "6"], "todo_remove": "2",
        }, follow_redirects=False)
        assert result.status_code in {200, 303}
        items = author.read_plan(identifier)["internal_todos"]
        assert len(items) == 7 and sum(item["done"] for item in items) == 5
        assert all(item["text"] != "Item 2" for item in items)
        assert author.read_plan(identifier)["internal_notes"] == record["internal_notes"]
        assert '>5/7</span>' in client.get(f"/cms/artifact/{identifier}").text
        revision, snapshot = form_snapshot(client.get(f"/cms/artifact/{identifier}"))
        cleared = client.post(f"/cms/save/{identifier}", data={"revision": revision, "snapshot": snapshot, "todos_present": "1"}, follow_redirects=False)
        assert cleared.status_code in {200, 303}
        assert author.read_plan(identifier)["internal_todos"] == []
        assert '>0/0</span>' in client.get(f"/cms/artifact/{identifier}").text
    assert source.read_bytes() == notebook


@pytest.mark.parametrize("failure", ["stale", "invalid"])
def test_failed_save_preserves_submitted_checklist_and_original_revision(author, failure):
    author.create_post("notes", {"title": "Notes", "planned": {"content": "Public body"}})
    author.start("post/notes")
    author.update("post/notes", {"internal_todos": [{"text": "Saved item", "done": False}]})
    with TestClient(create_app(author.root)) as client:
        revision, snapshot = form_snapshot(client.get("/cms/artifact/post/notes"))
        if failure == "stale":
            author.update("post/notes", {"internal_notes": "Concurrent decision"})
        before = author.store.inputs()
        response = client.post("/cms/save/post/notes", headers={"HX-Request": "true"}, data={
            "revision": revision, "snapshot": snapshot, "todos_present": "1",
            "todo_text": ["Unsaved <item>", "" if failure == "invalid" else "Another item"],
            "todo_done": "0", 'field:["internal_notes"]': "Unsaved notes",
        })
        assert response.status_code == (412 if failure == "stale" else 422)
        assert "Unsaved &lt;item&gt;" in response.text and "Unsaved notes" in response.text
        assert '>1/2</span>' in response.text
        assert form_snapshot(response)[0] == revision
        assert author.store.inputs() == before


@pytest.mark.parametrize("kind", ["post", "portfolio", "chapter", "personal"])
def test_planned_checklists_are_empty_and_nonempty_writes_are_rejected(author, kind):
    identifier, data = entry(author, kind)
    data["internal_todos"] = None
    author.create(data)
    assert author.read_plan(identifier)["internal_todos"] == []
    before = author.store.inputs()
    with pytest.raises(ServiceError, match="planned entries cannot have internal notes or to-dos"):
        author.update(identifier, {"internal_todos": [{"text": "Too early", "done": False}]})
    assert author.store.inputs() == before
    with TestClient(create_app(author.root)) as client:
        editor = client.get(f"/cms/artifact/{identifier}")
        assert 'data-todo-editor' not in editor.text
        token, snapshot = form_snapshot(editor)
        response = client.post(f"/cms/save/{identifier}", data={"revision": token, "snapshot": snapshot, "todos_present": "1", "todo_new": "Forged"})
        assert response.status_code == 422
        assert author.store.inputs() == before


def test_api_cli_and_task_context_share_current_entity_checklist(author, monkeypatch):
    author.create_post("notes", {"title": "Notes", "planned": {"content": "Public body"}})
    author.start("post/notes")
    with TestClient(create_app(author.root)) as client:
        token = author.inspect("post/notes")["revision"]
        response = client.patch("/api/artifacts/post/notes", headers={"If-Match": token}, json={"internal_todos": [{"text": "  Check the result  ", "done": True}]})
        assert response.status_code == 200
        assert response.json()["artifact"]["internal_todos"] == [{"text": "Check the result", "done": True}]
    board = KanbanService(author.root)
    card = board.create({"title": "Execute", "artifact_ids": ["post/notes"]})["card"]
    board.update(card["ref"], {"column": "done"})
    assert board.context(card["ref"])["artifacts"][0]["internal_todos"][0]["done"] is True
    monkeypatch.chdir(author.root)
    payload = author.root / ".tmp/todos.json"
    payload.parent.mkdir(exist_ok=True)
    payload.write_text(json.dumps({"internal_todos": [{"text": "Next check", "done": False}]}))
    result = CliRunner().invoke(app, ["update", "post/notes", "--patch-file", ".tmp/todos.json"])
    assert result.exit_code == 0, result.exception
    context = board.context(card["ref"])
    assert context["card"]["column"] == "done"
    assert context["artifacts"][0]["internal_todos"] == [{"text": "Next check", "done": False}]
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/kanban")
        assert "Next check" in page.text and '>0/1</span>' in page.text


def test_checklist_stays_out_of_rendered_pages(author, monkeypatch):
    author.create_post("notes", {"title": "Notes", "planned": {"content": "Public body"}})
    author.start("post/notes")
    author.update("post/notes", {"internal_todos": [{"text": "PRIVATE-TODO-SENTINEL", "done": False}]})
    author.publish("post/notes")
    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    for mode in ("preview", "production"):
        stage = BuildService(author.root).generate(mode)
        assert all("PRIVATE-TODO-SENTINEL" not in path.read_text() for path in stage.rglob("*")
                   if path.is_file() and path.suffix in {".ipynb", ".qmd", ".md", ".yaml", ".yml", ".json"})
