"""Ownership, transport, recovery and safe pruning of private context files."""
import io
import json
import re
import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_api import author_workspace, form_snapshot
from test_content_service import author_body
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.services.attachments import AttachmentService, AttachmentUpload
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def content(tmp_path):
    return ContentService(author_workspace(tmp_path))


def post(content, name="context", uploads=None):
    return content.create({"id": f"post/{name}", "kind": "post", "title": name, "path": f"content/notebooks/posts/{name}.ipynb", "internal_notes": "Private decision"}, attachment_uploads=uploads)


def png():
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(stream, "PNG")
    return stream.getvalue()


def test_shared_ownership_last_reference_archive_and_manual_pruning(content, monkeypatch):
    upload = AttachmentUpload("diagram.png", png())
    created = post(content, uploads=[upload])
    item = created["artifact"]["attachments"][0]
    files = AttachmentService(content.root)
    board = KanbanService(content.root)
    card = board.create({"title": "Do work", "artifact_ids": ["post/context"]}, attachment_uploads=[upload])["card"]
    active = content.root / f"backend/attachments/{item['id']}"
    assert len(files.read()["attachments"]) == 1
    assert len(files.read()["attachments"][0]["owners"]) == 2
    context = board.context(card["ref"])
    assert context["artifacts"][0]["internal_notes"] == "Private decision"
    assert item["id"] in context["artifacts"][0]["build_brief"]
    assert context["card"]["attachments"][0]["path"] == str(active.relative_to(content.root))
    assert content.deletion_plan("post/context")["attachment_actions"][0]["action"] == "keep shared file"
    deletion = content.delete("post/context")
    assert active.read_bytes() == upload.content
    assert not list((content.root / deletion["archive_path"]).rglob(item["id"]))
    removed = board.remove(card["ref"])
    archive = content.root / removed["archive_path"]
    assert not active.exists()
    assert (archive / f"backend/attachments/{item['id']}").read_bytes() == upload.content
    assert card["id"] in (archive / "attachments.json").read_text()
    with pytest.raises(ServiceError):
        files.file(item["id"])
    revision = content.validate()["revision"]
    shutil.rmtree(content.root / "archive/deleted")
    assert content.validate()["revision"] == revision
    post(content, "after-pruning")
    board.create({"title": "Still works"})
    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    BuildService(content.root).generate()
    # Completed recovery journals carry no hidden blob copies.
    for path in (content.root / "backend/runtime/transactions").rglob("*"):
        if path.is_file() and path.name.startswith(("candidate-", "preimage-")):
            assert path.read_bytes() != upload.content


def test_detach_reuse_stale_writes_and_whole_board_removal(content):
    created = post(content, uploads=[AttachmentUpload("facts.txt", b"facts")])
    item = created["artifact"]["attachments"][0]
    post(content, "other")
    service = AttachmentService(content.root)
    read = service.read("post/context")
    service.change("post/other", link=item["id"], expected_revision=read["revision"])
    before = service.read()["revision"]
    with pytest.raises(ServiceError) as stale:
        service.change("post/context", uploads=[AttachmentUpload("stale.txt", b"stale")], expected_revision=read["revision"])
    assert stale.value.status == 412
    assert service.read()["revision"] == before
    assert len(list((content.root / "backend/attachments").iterdir())) == 1
    assert "archive_path" not in service.change("post/context", remove=[item["id"]])
    result = service.change("post/other", remove=[item["id"]])
    assert result["archived_attachments"] == [item["id"]]
    board = KanbanService(content.root)
    card = board.create({"title": "Only owner"}, attachment_uploads=[AttachmentUpload("new.txt", b"new")])["card"]
    saved = content.read_data("kanban")
    saved["data"]["cards"] = []
    result = content.update_data("kanban", saved["data"], saved["revision"])
    assert result["archived_attachments"] == [card["attachments"][0]["id"]]


def test_recovery_completes_attachment_archival_before_pruning(content):
    created = post(content, uploads=[AttachmentUpload("facts.txt", b"recover these bytes")])
    identifier = created["artifact"]["attachments"][0]["id"]
    service = AttachmentService(content.root)
    def fault(stage, index):
        if stage == "installed" and index == 1:
            raise RuntimeError("interrupted save")
    service.content.store.fault = fault
    with pytest.raises(ServiceError) as pending:
        service.change("post/context", remove=[identifier])
    assert pending.value.code == "pending_transaction"
    assert AttachmentService(content.root).read("post/context")["attachments"] == []
    archived = list((content.root / "archive/deleted").rglob(identifier))
    assert len(archived) == 1 and archived[0].read_bytes() == b"recover these bytes"
    shutil.rmtree(archived[0].parents[2])
    content.validate()
    content.update("post/context", {"internal_notes": "Next note"})


@pytest.mark.parametrize("kind", ["post", "course", "chapter", "portfolio"])
def test_creation_and_edit_notes_uploads_share_one_form(content, kind):
    if kind == "chapter":
        content.create({"id": "course/parent", "kind": "course", "title": "Parent", "path": "content/notebooks/courses/parent"})
    with TestClient(create_app(content.root)) as client:
        page = client.get(f"/cms/new?kind={kind}")
        assert 'data-dialog-open="notes"' in page.text
        assert 'class="cms-dialog notes-dialog"' in page.text
        assert 'data-inline-dialog' in page.text  # readable no-JS fallback
        assert page.text.count('<form id="new-editor-form"') == 1
        token = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        data = {"revision": token, 'field:["title"]': "Attached", 'field:["internal_notes"]': "Unsaved context"}
        if kind == "chapter":
            data.update({'field:["parent"]': "course/parent", 'field:["section"]': "main"})
        saved = client.post(f"/cms/new?kind={kind}", data=data, files={"context_files": ("diagram.png", png(), "image/png")}, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        identifier = "course/parent/attached" if kind == "chapter" else f"{kind}/attached"
        plan = content.read_plan(identifier)
        assert plan["internal_notes"] == "Unsaved context"
        assert plan["attachments"][0]["name"] == "diagram.png"
        if kind == "course":
            workspace = client.get("/cms/courses/attached")
            assert workspace.status_code == 200
            assert 'class="course-heading"' in workspace.text
            assert 'data-dialog-open="notes"' in workspace.text
            assert 'id="notes" class="cms-dialog notes-dialog"' in workspace.text
        editor = client.get("/cms/artifact/" + identifier)
        assert 'class="cms-dialog notes-dialog"' in editor.text
        assert 'data-dialog-open="notes"' in editor.text
        token, baseline = form_snapshot(editor)
        updated = client.post("/cms/save/" + identifier, data={"revision": token, "snapshot": baseline, 'field:["internal_notes"]': "Edited context"}, files={"context_files": ("spec.pdf", b"%PDF-test", "application/pdf")})
        assert updated.status_code == 200, updated.text
        plan = content.read_plan(identifier)
        assert len(plan["attachments"]) == 2 and plan["internal_notes"] == "Edited context"
        assert "spec.pdf" in plan["build_brief"]
        token, baseline = form_snapshot(client.get("/cms/artifact/" + identifier))
        detached = client.post("/cms/save/" + identifier, data={"revision": token, "snapshot": baseline, "remove_attachments": plan["attachments"][0]["id"]})
        assert detached.status_code == 200, detached.text
        assert [a["name"] for a in content.read_plan(identifier)["attachments"]] == ["spec.pdf"]


def test_api_download_preview_context_and_conflict(content):
    post(content)
    with TestClient(create_app(content.root)) as client:
        read = client.get("/api/context-attachments/post/context")
        assert client.post("/api/context-attachments/post/context", files={"context_files": ("facts.txt", b"private")}).status_code == 428
        saved = client.post("/api/context-attachments/post/context", headers={"If-Match": read.headers["etag"]}, files={"context_files": ("facts.txt", b"private")})
        assert saved.status_code == 200, saved.text
        item = saved.json()["attachments"][0]
        download = client.get(f"/api/attachments/{item['id']}?inline=true")
        assert download.content == b"private" and download.headers["content-disposition"].startswith("attachment;")
        assert client.delete("/api/context-attachments/post/context", params={"attachment_id": item["id"]}, headers={"If-Match": read.headers["etag"]}).status_code == 412
        image = client.post("/api/context-attachments/post/context", headers={"If-Match": saved.headers["etag"]}, files={"context_files": ("picture.png", png())})
        image_id = image.json()["attachments"][-1]["id"]
        assert client.get(f"/api/attachments/{image_id}?inline=true").headers["content-disposition"].startswith("inline;")
        assert client.get("/api/attachments/" + "a" * 64).status_code == 404


def test_kanban_upload_edit_context_and_cli(content, monkeypatch):
    post(content, uploads=[AttachmentUpload("entity.txt", b"entity context")])
    with TestClient(create_app(content.root)) as client:
        board = client.get("/api/kanban").json()
        saved = client.post("/cms/kanban/create", data={"revision": board["board_revision"], "title": "Task", "description": "Card-specific context", "column": "todo", "artifact_ids": "post/context"}, files={"context_files": ("card.txt", b"card context")}, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        card = KanbanService(content.root).read()["cards"][0]
        kanban = client.get("/cms/kanban").text
        assert "card.txt" in kanban
        assert 'class="button notes-button"' in kanban
        assert 'class="cms-dialog notes-dialog"' in kanban
        assert "Private decision" in kanban and "entity.txt" in kanban
        context = client.get("/api/kanban/" + card["id"]).json()
        assert context["artifacts"][0]["internal_notes"] == "Private decision"
        assert context["card"]["attachments"][0]["name"] == "card.txt"
        token = context["board_revision"]
        updated = client.post("/cms/kanban/update", data={"revision": token, "card_id": card["id"], "title": "Edited task", "description": "More context", "column": "review", "artifact_ids": "post/context", "remove_attachments": card["attachments"][0]["id"]}, files={"context_files": ("replacement.txt", b"replacement")}, follow_redirects=False)
        assert updated.status_code == 303, updated.text
    monkeypatch.chdir(content.root)
    runner = CliRunner()
    result = runner.invoke(app, ["kanban", "show", card["ref"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["artifacts"][0]["internal_notes"] == "Private decision"
    listed = runner.invoke(app, ["attachments", "ls", card["ref"]])
    item = json.loads(listed.output)["attachments"][0]
    assert item["name"] == "replacement.txt"
    linked = runner.invoke(app, ["attachments", "link", "post/context", item["id"], "--expected-revision", json.loads(listed.output)["revision"]])
    assert linked.exit_code == 0, linked.output
    path = content.root / ".tmp/new.txt"
    path.parent.mkdir()
    path.write_text("new context")
    added = runner.invoke(app, ["attachments", "add", "post/context", "--file", str(path)])
    assert added.exit_code == 0, added.output
    last = json.loads(added.output)["attachments"][-1]
    removed = runner.invoke(app, ["attachments", "rm", "post/context", last["id"]])
    assert removed.exit_code == 0 and "archive_path" in json.loads(removed.output)


def test_publish_keeps_private_files_out_of_generated_site(content, monkeypatch):
    post(content, uploads=[AttachmentUpload("private.txt", b"PRIVATE-ATTACHMENT-CONTENT")])
    content.start("post/context")
    author_body(content, "post/context")
    content.publish("post/context", attachment_uploads=[AttachmentUpload("other.txt", b"OTHER-PRIVATE-CONTEXT")])
    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    for mode in ["preview", "production"]:
        stage = BuildService(content.root).generate(mode=mode)
        for path in stage.rglob("*"):
            if path.is_file():
                assert b"PRIVATE-ATTACHMENT-CONTENT" not in path.read_bytes()
                assert b"OTHER-PRIVATE-CONTEXT" not in path.read_bytes()
                assert b"backend/attachments/" not in path.read_bytes()


def test_course_cascade_archives_parent_and_chapter_files_together(content):
    parent = content.create({"id": "course/attached", "kind": "course", "title": "Course", "path": "content/notebooks/courses/attached"}, attachment_uploads=[AttachmentUpload("course.txt", b"course context")])
    child = content.create({"id": "course/attached/chapter", "kind": "chapter", "title": "Chapter", "path": "content/notebooks/courses/attached/chapter.ipynb", "parent": "course/attached", "section": "main", "toc_title": "Chapter"}, attachment_uploads=[AttachmentUpload("chapter.txt", b"chapter context")])
    plan = content.deletion_plan("course/attached")
    assert [a["action"] for a in plan["attachment_actions"]] == ["archive", "archive"]
    result = content.delete("course/attached", plan["revision"], cascade=True)
    for record in [parent["artifact"], child["artifact"]]:
        identifier = record["attachments"][0]["id"]
        assert not (content.root / f"backend/attachments/{identifier}").exists()
        assert (content.root / result["archive_path"] / f"backend/attachments/{identifier}").exists()
    shutil.rmtree(content.root / result["archive_path"])
    assert content.validate()["valid"]


def test_cms_conflicts_keep_notes_removals_and_attachment_metadata(content):
    created = post(content, uploads=[AttachmentUpload("facts.txt", b"facts")])
    item = created["artifact"]["attachments"][0]
    board = KanbanService(content.root)
    card = board.create({"title": "Card"}, attachment_uploads=[AttachmentUpload("card.txt", b"card")])["card"]
    with TestClient(create_app(content.root)) as client:
        editor = client.get("/cms/artifact/post/context")
        token, baseline = form_snapshot(editor)
        content.update("post/context", {"title": "Concurrent edit"})
        failed = client.post("/cms/save/post/context", data={"revision": token, "snapshot": baseline, 'field:["internal_notes"]': "Preserve unsaved notes", "remove_attachments": item["id"]}, files={"context_files": ("retry.txt", b"retry")}, headers={"HX-Request": "true"})
        assert failed.status_code == 412
        assert 'Preserve unsaved notes' in failed.text
        assert re.search(rf'name="remove_attachments" value="{item["id"]}" checked', failed.text)
        token = board.read()["board_revision"]
        board.update(card["id"], {"title": "Concurrent card edit"})
        failed = client.post("/cms/kanban/update", data={"revision": token, "card_id": card["id"], "title": "Unsaved title", "description": "Unsaved card notes", "column": "todo", "attachment_snapshot": json.dumps(card["attachments"]), "remove_attachments": card["attachments"][0]["id"]}, files={"context_files": ("retry.txt", b"retry")}, headers={"HX-Request": "true"})
        assert failed.status_code == 412
        assert 'Unsaved title' in failed.text and 'Unsaved card notes' in failed.text
        assert 'card.txt' in failed.text
    assert len(list((content.root / "backend/attachments").iterdir())) == 2


def test_explicit_malformed_board_repair_preserves_shared_files(content):
    created = post(content, uploads=[AttachmentUpload("shared.txt", b"shared")])
    board = KanbanService(content.root)
    board.create({"title": "Card", "attachments": created["artifact"]["attachments"]}, attachment_uploads=[AttachmentUpload("orphan.txt", b"orphan")])
    saved = content.read_data("kanban")["data"]
    path = content.root / "backend/data/kanban.yaml"
    malformed = path.read_bytes() + b"\ncards: []\n"
    path.write_bytes(malformed)
    saved["cards"] = []
    repaired = content.update_data("kanban", saved)
    assert len(AttachmentService(content.root).read()["attachments"]) == 1
    assert len(repaired["archived_attachments"]) == 1
    archive = content.root / repaired["archive_path"]
    assert (archive / "malformed-kanban.yaml").read_bytes() == malformed
    shutil.rmtree(archive)
    assert content.validate()["valid"]


@pytest.mark.parametrize("upload", [AttachmentUpload("empty.txt", b""), AttachmentUpload("bad.png", b"not an image"), AttachmentUpload("big.txt", b"x" * (20 * 1024 * 1024 + 1))])
def test_invalid_uploads_leave_no_files_or_owner(content, upload):
    before = content.validate()["revision"]
    with pytest.raises(ServiceError):
        post(content, uploads=[upload])
    assert content.validate()["revision"] == before
    assert not (content.root / "backend/attachments").exists()
