"""Task persistence, validated links, conflict handling and transport parity."""
import json
import re
from pathlib import Path

import pytest
from test_api import author_workspace
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def board(tmp_path):
    root = author_workspace(tmp_path)
    content = ContentService(root)
    content.create({"id": "post/task", "kind": "post", "title": "Linked article", "path": "content/notebooks/posts/task.ipynb", "planned": {"content": "Write this article."}})
    return content, KanbanService(root)


def test_task_links_follow_content_without_changing_publication(board):
    content, service = board
    assert service.read()["cards"] == []
    created = service.create({"id": "edit-article", "title": "Edit article", "artifact_ids": ["post/task", "post/task"]})
    card = service.read()["cards"][0]
    assert card["artifact_ids"] == ["post/task"]
    assert card["links"][0]["frontend_url"] is None
    assert card["links"][0]["editor_url"] is None
    content.start("post/task")
    card = service.read()["cards"][0]
    assert card["links"][0]["editor_url"].startswith("vscode://file/")
    source = Path(card["links"][0]["source_path"])
    before = source.read_bytes()
    service.update(created["card"]["id"], {"column": "done"})
    assert content.inspect("post/task")["artifact"]["lifecycle"] == "draft"
    assert source.read_bytes() == before
    assert KanbanService(content.root).read(column="done")["cards"][0]["id"] == "edit-article"
    stage = BuildService(content.root).generate()
    assert not (stage / "backend/data/kanban.yaml").exists()
    assert "Edit article" not in (stage / "posts.qmd").read_text()
    service.remove("edit-article")
    assert service.read()["cards"] == []
    assert source.read_bytes() == before


def test_task_notes_and_todos_are_task_scoped_and_searchable(board):
    content, service = board
    created = service.create({
        "id": "execution-memory", "title": "Run the comparison", "artifact_ids": ["post/task"],
        "notes": "Keep this result with the execution.",
        "todos": [{"text": "Run the baseline", "done": True}, {"text": "Record latency", "done": False}],
    })
    card = service.context(created["card"]["ref"])["card"]
    assert card["notes"] == "Keep this result with the execution."
    assert card["todos"] == [{"text": "Run the baseline", "done": True}, {"text": "Record latency", "done": False}]
    assert service.read(query="Record latency")["cards"][0]["id"] == "execution-memory"
    linked = content.inspect("post/task")["artifact"]
    assert linked["internal_notes"] == "" and linked["internal_todos"] == []


@pytest.mark.parametrize("data", [
    {"id": "bad", "title": "Bad link", "artifact_ids": ["post/missing"]},
    {"id": "bad", "title": "Source is not an ID", "artifact_ids": ["content/notebooks/posts/task.ipynb"]},
    {"id": "bad", "title": "Invalid column", "column": "published"},
    {"id": "../bad", "title": "Invalid card ID"},
    {"id": "bad", "title": "   "},
])
def test_invalid_cards_never_write(board, data):
    content, service = board
    before = content.list()["revision"]
    with pytest.raises(ServiceError):
        service.create(data)
    assert content.list()["revision"] == before
    assert not (content.root / "backend/data/kanban.yaml").exists()


def test_stale_revision_duplicates_and_malformed_data_preserve_bytes(board):
    content, service = board
    first = service.create({"id": "one", "title": "One"})
    service.update("one", {"description": "Saved update"}, first["revision"])
    source = content.root / "backend/data/kanban.yaml"
    saved = source.read_bytes()
    with pytest.raises(ServiceError) as stale:
        service.update("one", {"title": "Stale update"}, first["revision"])
    assert stale.value.status == 412
    with pytest.raises(ServiceError):
        service.create({"id": "one", "title": "Duplicate"})
    assert source.read_bytes() == saved
    source.write_text("version: 1\ncards: []\ncards: []\n")
    malformed = source.read_bytes()
    with pytest.raises(ServiceError):
        service.create({"title": "No overwrite"})
    assert source.read_bytes() == malformed
    content.update_data("kanban", {"version": 1, "cards": []})
    assert service.read()["cards"] == []


def test_http_and_cms_use_same_board_and_revisions(board):
    from fastapi.testclient import TestClient

    content, service = board
    with TestClient(create_app(content.root)) as client:
        page = client.get("/cms/kanban")
        assert page.status_code == 200
        assert page.text.index('href="/cms/personal"') < page.text.index('href="/cms/kanban"')
        token = client.get("/api/kanban").headers["etag"]
        assert client.post("/api/kanban", json={"title": "No token"}).status_code == 428
        created = client.post("/api/kanban", headers={"If-Match": token}, json={"id": "one", "title": "Review article", "artifact_ids": ["post/task"], "notes": "Initial task notes", "todos": [{"text": "Inspect example", "done": False}, {"text": "Record result", "done": True}]})
        assert created.status_code == 201
        card_page = client.get("/cms/kanban")
        assert "Open frontend" not in card_page.text and "Linked article" in card_page.text
        assert "Initial task notes" in card_page.text and "1/2 to-dos" in card_page.text
        assert "Inspect example" in card_page.text and "Record result" in card_page.text
        current = client.get("/api/kanban").headers["etag"]
        moved = client.patch("/api/kanban/one", headers={"If-Match": current}, json={"column": "review", "notes": "Updated through API", "todos": [{"text": "Confirm API save", "done": True}]})
        assert moved.status_code == 200
        assert service.read()["cards"][0]["notes"] == "Updated through API"
        failed = client.post("/cms/kanban/update", data={"revision": current.strip('"'), "card_id": "one", "title": "My unsaved title", "description": "Preserve me", "notes": "Unsubmitted task note", "todos_present": "1", "todo_text": "Preserve this task item", "column": "done", "artifact_ids": "post/task"})
        assert failed.status_code == 412
        assert "My unsaved title" in failed.text and "Preserve me" in failed.text
        assert "Unsubmitted task note" in failed.text and "Preserve this task item" in failed.text
        assert service.read()["cards"][0]["title"] == "Review article"
        bad = client.post("/cms/kanban/create", data={"revision": service.read()["revision"], "title": "Unknown link", "column": "todo", "artifact_ids": "post/unknown"})
        assert bad.status_code == 422 and "Unknown link" in bad.text
        revision = service.read()["board_revision"]
        saved = client.post("/cms/kanban/update", data={"revision": revision, "card_id": "one", "title": "CMS update", "description": "Task objective", "notes": "Saved in the CMS", "column": "done", "artifact_ids": "post/task", "todos_present": "1", "todo_text": "Finish the check", "todo_done": "0"}, follow_redirects=False)
        assert saved.status_code == 303
        saved_card = service.read()["cards"][0]
        assert saved_card["title"] == "CMS update"
        assert saved_card["notes"] == "Saved in the CMS"
        assert saved_card["todos"] == [{"text": "Finish the check", "done": True}]
        token = client.get("/api/kanban").headers["etag"]
        assert client.delete("/api/kanban/one", headers={"If-Match": token}).status_code == 200


def test_cli_shares_cards_revisions_and_validated_columns(board, monkeypatch):
    content, service = board
    monkeypatch.chdir(content.root)
    runner = CliRunner()
    todos_file = content.root / ".tmp" / "task-todos.json"
    todos_file.parent.mkdir(parents=True)
    todos_file.write_text(json.dumps([{"text": "Check the CLI path", "done": False}, {"text": "Record evidence", "done": True}]))
    created = runner.invoke(app, ["kanban", "add", "--title", "CLI task", "--notes", "CLI task notes", "--todos-file", str(todos_file), "--link", "post/task"])
    assert created.exit_code == 0, created.output
    card = json.loads(created.output)["card"]
    assert re.fullmatch(r"[0-9a-f]{32}", card["id"])
    assert card["ref"] == "card#1"
    assert card["notes"] == "CLI task notes"
    assert card["todos"][1]["done"] is True
    read = runner.invoke(app, ["kanban", "ls"])
    assert read.exit_code == 0, read.output
    payload = json.loads(read.output)
    assert payload["cards"][0]["title"] == "CLI task"
    assert payload["cards"][0]["todos"][0]["text"] == "Check the CLI path"
    revision = payload["board_revision"]
    todos_file.write_text(json.dumps([{"text": "CLI checklist replaced", "done": True}]))
    updated = runner.invoke(app, ["kanban", "update", card["ref"], "--notes", "Updated task notes", "--todos-file", str(todos_file), "--expected-revision", revision])
    assert updated.exit_code == 0, updated.output
    shown = runner.invoke(app, ["kanban", "show", card["ref"]])
    assert shown.exit_code == 0, shown.output
    shown_card = json.loads(shown.output)["card"]
    assert shown_card["notes"] == "Updated task notes"
    assert shown_card["todos"] == [{"text": "CLI checklist replaced", "done": True}]
    todos_file.write_text("[]")
    cleared = runner.invoke(app, ["kanban", "update", card["ref"], "--clear-notes", "--todos-file", str(todos_file), "--expected-revision", service.read()["board_revision"]])
    assert cleared.exit_code == 0, cleared.output
    assert service.read()["cards"][0]["notes"] == ""
    assert service.read()["cards"][0]["todos"] == []
    revision = service.read()["board_revision"]
    moved = runner.invoke(app, ["kanban", "move", card["ref"], "review", "--expected-revision", revision])
    assert moved.exit_code == 0, moved.output
    assert json.loads(moved.output)["card"]["column"] == "review"
    stale = runner.invoke(app, ["kanban", "update", card["ref"], "--title", "Stale", "--expected-revision", revision])
    assert stale.exit_code == 1
    assert isinstance(stale.exception, ServiceError)
    assert stale.exception.status == 412
    assert service.read()["cards"][0]["title"] == "CLI task"
    invalid = runner.invoke(app, ["kanban", "move", card["ref"], "published"])
    assert invalid.exit_code == 1
    assert isinstance(invalid.exception, ServiceError)
    assert service.read()["cards"][0]["column"] == "review"
    listed = runner.invoke(app, ["kanban", "ls", "--query", "CLI task", "--column", "review"])
    assert listed.exit_code == 0
    assert json.loads(listed.output)["cards"][0]["id"] == card["id"]
    assert runner.invoke(app, ["kanban", "move", card["ref"], "done"]).exit_code == 0
    assert runner.invoke(app, ["kanban", "update", card["ref"], "--clear-links"]).exit_code == 0
    assert service.read()["cards"][0]["artifact_ids"] == []
    assert runner.invoke(app, ["kanban", "rm", card["ref"]]).exit_code == 0


def test_cli_rejects_custom_card_id_without_writing(board, monkeypatch):
    content, service = board
    monkeypatch.chdir(content.root)
    before = service.read()
    result = CliRunner().invoke(app, ["kanban", "add", "--title", "Task", "--id", "chosen"])
    assert result.exit_code == 2
    assert "No such option: --id" in result.output
    assert service.read() == before


def test_editor_order_folding_and_contacts(board):
    from fastapi.testclient import TestClient

    content, _ = board
    with TestClient(create_app(content.root)) as client:
        overview = client.get("/cms/home")
        assert 'href="https://github.com/example"' in overview.text
        assert 'href="https://linkedin.com/in/example"' in overview.text
        editor = client.get("/cms/data/profile")
        headings = re.findall(r'<legend(?:\s[^>]*)?>(.*?)</legend>', editor.text, re.S)
        assert headings[0] == "General"
        assert headings[1] == "Contact"
        assert not re.search(r'<details class="entity-group"[^>]*\bopen\b', editor.text)
        assert 'data-client-list' in editor.text


def test_task_changes_do_not_trigger_public_preview_rebuilds(board):
    content, service = board
    builds = BuildService(content.root)
    before = builds._preview_signature()
    card = service.create({"title": "Author task"})["card"]
    service.update(card["id"], {"column": "review"})
    assert builds._preview_signature() == before
    content.start("post/task")
    assert builds._preview_signature() != before


def test_project_and_gallery_links_use_their_canonical_sources(board):
    content, service = board
    content.create_project("kanban-test")
    project = content.inspect("project/kanban-test")["artifact"]
    content.create({"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "backend/data/photos.yaml"})
    service.create({"title": "Check supporting sources", "artifact_ids": [project["id"], "gallery/photos"]})
    project_link, gallery_link = service.read()["cards"][0]["links"]
    assert project_link["frontend_url"] is None
    assert project_link["editor_url"].endswith("projects/kanban-test")
    assert gallery_link["frontend_url"].endswith("gallery.html")
    assert gallery_link["editor_url"].endswith("backend/data/photos.yaml")
