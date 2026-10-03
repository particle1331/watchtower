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
    assert card["links"][0]["frontend_url"].endswith("/nb/posts/task.html")
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
    assert not (stage / "content/data/kanban.yaml").exists()
    assert "Edit article" not in (stage / "posts.qmd").read_text()
    service.remove("edit-article")
    assert service.read()["cards"] == []
    assert source.read_bytes() == before


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
    assert not (content.root / "content/data/kanban.yaml").exists()


def test_stale_revision_duplicates_and_malformed_data_preserve_bytes(board):
    content, service = board
    first = service.create({"id": "one", "title": "One"})
    service.update("one", {"description": "Saved update"}, first["revision"])
    source = content.root / "content/data/kanban.yaml"
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
        created = client.post("/api/kanban", headers={"If-Match": token}, json={"id": "one", "title": "Review article", "artifact_ids": ["post/task"]})
        assert created.status_code == 201
        card_page = client.get("/cms/kanban")
        assert "Open frontend" in card_page.text and "Linked article" in card_page.text
        current = client.get("/api/kanban").headers["etag"]
        moved = client.patch("/api/kanban/one", headers={"If-Match": current}, json={"column": "review"})
        assert moved.status_code == 200
        failed = client.post("/cms/kanban/update", data={"revision": current.strip('"'), "card_id": "one", "title": "My unsaved title", "description": "Preserve me", "column": "done", "artifact_ids": "post/task"})
        assert failed.status_code == 412
        assert "My unsaved title" in failed.text and "Preserve me" in failed.text
        assert service.read()["cards"][0]["title"] == "Review article"
        bad = client.post("/cms/kanban/create", data={"revision": service.read()["revision"], "title": "Unknown link", "column": "todo", "artifact_ids": "post/unknown"})
        assert bad.status_code == 422 and "Unknown link" in bad.text
        revision = service.read()["revision"]
        saved = client.post("/cms/kanban/update", data={"revision": revision, "card_id": "one", "title": "CMS update", "column": "done", "artifact_ids": "post/task"}, follow_redirects=False)
        assert saved.status_code == 303
        assert service.read()["cards"][0]["title"] == "CMS update"
        token = client.get("/api/kanban").headers["etag"]
        assert client.delete("/api/kanban/one", headers={"If-Match": token}).status_code == 200


def test_cli_shares_cards_revisions_and_validated_columns(board, monkeypatch):
    content, service = board
    monkeypatch.chdir(content.root)
    runner = CliRunner()
    created = runner.invoke(app, ["kanban", "add", "--id", "one", "--title", "CLI task", "--link", "post/task"])
    assert created.exit_code == 0, created.output
    read = runner.invoke(app, ["kanban", "ls"])
    assert read.exit_code == 0, read.output
    payload = json.loads(read.output)
    assert payload["cards"][0]["title"] == "CLI task"
    revision = payload["revision"]
    moved = runner.invoke(app, ["kanban", "move", "one", "review", "--expected-revision", revision])
    assert moved.exit_code == 0, moved.output
    assert json.loads(moved.output)["card"]["column"] == "review"
    stale = runner.invoke(app, ["kanban", "update", "one", "--title", "Stale", "--expected-revision", revision])
    assert stale.exit_code == 1
    assert isinstance(stale.exception, ServiceError)
    assert stale.exception.status == 412
    assert service.read()["cards"][0]["title"] == "CLI task"
    invalid = runner.invoke(app, ["kanban", "move", "one", "published"])
    assert invalid.exit_code == 1
    assert isinstance(invalid.exception, ServiceError)
    assert service.read()["cards"][0]["column"] == "review"
    listed = runner.invoke(app, ["kanban", "ls", "--query", "CLI task", "--column", "review"])
    assert listed.exit_code == 0
    assert json.loads(listed.output)["cards"][0]["id"] == "one"
    assert runner.invoke(app, ["kanban", "move", "one", "done"]).exit_code == 0
    assert runner.invoke(app, ["kanban", "update", "one", "--clear-links"]).exit_code == 0
    assert service.read()["cards"][0]["artifact_ids"] == []
    assert runner.invoke(app, ["kanban", "rm", "one"]).exit_code == 0


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
    content.create({"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "content/data/photos.yaml"})
    service.create({"title": "Check supporting sources", "artifact_ids": [project["id"], "gallery/photos"]})
    project_link, gallery_link = service.read()["cards"][0]["links"]
    assert project_link["frontend_url"] is None
    assert project_link["editor_url"].endswith("projects/kanban-test")
    assert gallery_link["frontend_url"].endswith("gallery.html")
    assert gallery_link["editor_url"].endswith("content/data/photos.yaml")
