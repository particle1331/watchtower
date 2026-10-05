"""Planning workflows share state, readiness, relationship and outline contracts."""

import html
import json
import re

import nbformat
import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot

from watchtower.api import create_app
from watchtower.services.build import _Generator
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def token(response):
    return re.search(r'name="revision" value="([^"]+)"', response.text)[1]


def course(author, **extra):
    author.create({"id": "course/demo", "kind": "course", "title": "Demo course", "path": "content/notebooks/courses/demo", "contract": {"purpose": "Teach programming", "audience": "Python users", "planned": {"summary": "Build a tool", "chapters": []}}, **extra})


def chapter(author, name="first", **extra):
    author.create({"id": f"course/demo/{name}", "kind": "chapter", "title": name.title(), "parent": "course/demo", "section": "main", "toc_title": name.title(), "path": f"content/notebooks/courses/demo/{name}.ipynb", **extra})


@pytest.mark.parametrize("kind", ["post", "portfolio", "course"])
def test_private_partial_plan_reopens_with_guidance(author, kind):
    with TestClient(create_app(author.root)) as client:
        page = client.get(f"/cms/new?kind={kind}")
        response = client.post(f"/cms/new?kind={kind}", data={"revision": token(page), "name": "idea", "title": "An idea", "next_steps": "Investigate an example"}, follow_redirects=False)
        assert response.status_code == 303, response.text
        record = author.inspect(f"{kind}/idea")
        assert record["artifact"]["visibility"] == "private"
        assert record["missing_plan_fields"]
        assert "Investigate an example" in record["build_brief"]
        editor = client.get(response.headers["location"])
        assert 'data-editing="true"' in editor.text
        assert "Complete" in html.unescape(editor.text) or "complete:" in editor.text
        assert "Copy build brief" in editor.text and "Not on the live site" in editor.text
        assert "Investigate an example" in editor.text
        with pytest.raises(ServiceError, match="Complete the core plan"):
            author.start(f"{kind}/idea")
        assert not record["editor_url"]


def test_course_brief_atomic_save_and_legacy_recovery(author):
    course(author, planned={"content": "Recovered legacy summary", "old_note": "Keep this"})
    original = author.inspect("course/demo")
    contract = original["contract"]
    contract["planned"]["summary"] = ""
    contract["planned"]["extension"] = "Keep this too"
    author.update_data("course/demo", contract)
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/courses/demo")
        revision, snapshot = form_snapshot(page)
        assert "Recovered legacy summary" in json.loads(snapshot)["contract"]["planned"]["summary"]
        result = client.post("/cms/save/course/demo", data={"revision": revision, "snapshot": snapshot, 'field:["title"]': "Revised title", 'field:["contract", "planned", "outcomes"]': "Can build a tool"}, follow_redirects=False)
        assert result.status_code == 303, result.text
        record = author.inspect("course/demo")
        assert record["artifact"]["title"] == "Revised title"
        assert record["contract"]["planned"]["summary"] == "Recovered legacy summary"
        assert record["contract"]["planned"]["extension"] == "Keep this too"
        assert record["artifact"]["planned"]["old_note"] == "Keep this"
        assert record["contract"]["actualized"] == {"summary": ""}
        failed = client.post("/cms/save/course/demo", data={"revision": revision, "snapshot": snapshot, 'field:["contract", "planned", "outcomes"]': "Unsaved outcome"})
        assert failed.status_code == 412
        assert "Unsaved outcome" in failed.text
        assert token(failed) == revision
        assert author.inspect("course/demo")["contract"]["planned"]["outcomes"] == "Can build a tool"


def test_contextual_chapter_partial_save_then_ready_draft(author):
    course(author)
    with TestClient(create_app(author.root)) as client:
        path = "/cms/new?kind=chapter&parent=course/demo&section=main"
        page = client.get(path)
        assert 'value="course/demo" selected' in page.text
        result = client.post(path, data={"revision": token(page), "name": "first", "title": "First chapter", "parent": "course/demo", "section": "main", "summary": "A short summary"}, follow_redirects=False)
        assert result.status_code == 303, result.text
        assert result.headers["location"] == "/cms/courses/demo#outline"
        record = author.inspect("course/demo/first")
        assert record["chapter_plan"]["summary"] == "A short summary"
        assert record["missing_plan_fields"] == ["Planned content", "Planned lab and evidence"]
        page = client.get("/cms/artifact/course/demo/first")
        revision, snapshot = form_snapshot(page)
        result = client.post("/cms/save/course/demo/first", data={"revision": revision, "snapshot": snapshot, 'field:["plan", "content"]': "Explain the idea", 'field:["plan", "lab_and_evidence"]': "Build and check", 'field:["plan", "references"]': "A useful source"}, follow_redirects=False)
        assert result.status_code == 303
        record = author.inspect("course/demo/first")
        assert not record["missing_plan_fields"]
        author.start("course/demo/first", record["revision"])
        body = "\n".join(c.source for c in nbformat.read(author.root / record["source_path"], as_version=4).cells)
        assert body.count("# First chapter\n") == 1
        assert "A useful source" in body and "A short summary" in body
        brief = author.inspect("course/demo")["build_brief"]
        assert "First chapter" in brief and "A useful source" in brief
        assert "Python users" in author.inspect("course/demo/first")["build_brief"]


def test_outline_operations_are_atomic_and_preserve_ids(author):
    course(author)
    chapter(author)
    chapter(author, "second")
    def action(name, **values):
        return author.organize_course("course/demo", name, values, author.inspect("course/demo")["revision"])
    action("add-section", title="Next phase")
    action("rename-section", section="next-phase", title="Advanced")
    action("move-chapter", chapter="course/demo/first", section="next-phase")
    action("section-up", section="next-phase")
    record = author.inspect("course/demo")
    assert [s["id"] for s in record["contract"]["toc"]] == ["next-phase", "main"]
    assert [r["chapter"]["id"] for r in record["chapter_rows"]] == ["course/demo/first", "course/demo/second"]
    assert author.inspect("course/demo/first")["chapter_plan"]["section"] == "next-phase"
    before = author.snapshot().revision
    with pytest.raises(ServiceError, match="Move or delete"):
        action("remove-section", section="next-phase")
    assert author.snapshot().revision == before
    action("move-chapter", chapter="course/demo/first", section="main")
    action("chapter-up", chapter="course/demo/first")
    action("remove-section", section="next-phase")
    assert author.inspect("course/demo")["contract"]["toc"][0]["chapters"] == ["course/demo/first", "course/demo/second"]
    with pytest.raises(ServiceError) as failure:
        author.organize_course("course/demo", "add-section", {"title": "Stale"}, before)
    assert failure.value.status == 412
    with TestClient(create_app(author.root)) as client:
        failed = client.post("/cms/courses/demo/outline", data={"revision": before, "action": "add-section", "title": "My unsaved section"})
        assert failed.status_code == 412
        assert "My unsaved section" in failed.text and token(failed) == before


def test_lookup_selection_order_and_conflict_preservation(author):
    author.create_post("exact", {"title": "Duplicate title", "visibility": "private"})
    author.create_post("prefix", {"title": "Exact examples"})
    author.create_post("substring", {"title": "An exact example"})
    with TestClient(create_app(author.root)) as client:
        matches = client.get("/cms/lookup?q=EXACT").json()["artifacts"]
        assert [a["id"] for a in matches] == ["post/prefix", "post/substring", "post/exact"]
        assert client.get("/cms/lookup?q=POST/EXACT").json()["artifacts"][0]["id"] == "post/exact"
        page = client.get("/cms/new?kind=post")
        result = client.post("/cms/new?kind=post", data={"revision": token(page), "name": "linked", "title": "Linked post", "relationship:relations": "true", "relations": ["", "post/prefix", "post/exact", "post/prefix"]}, follow_redirects=False)
        assert result.status_code == 303
        page = client.get("/cms/artifact/post/linked")
        revision, snapshot = form_snapshot(page)
        assert author.inspect("post/linked")["artifact"]["relations"] == ["post/prefix", "post/exact"]
        assert page.text.index('value="post/prefix" selected') < page.text.index('value="post/exact" selected')
        fields = {"revision": revision, "snapshot": snapshot, 'relationship:field:["relations"]': "true", 'field:["relations"]': ["", "post/substring", "post/exact"]}
        author.update("post/linked", {"description": "Concurrent edit"})
        failed = client.post("/cms/save/post/linked", data=fields)
        assert failed.status_code == 412
        assert 'value="post/substring" selected' in failed.text
        assert token(failed) == revision
        fields["revision"] = author.inspect("post/linked")["revision"]
        saved = client.post("/cms/save/post/linked", data=fields)
        assert saved.status_code == 200
        assert author.inspect("post/linked")["artifact"]["relations"] == ["post/substring", "post/exact"]
        page = client.get("/cms/artifact/post/linked")
        revision, snapshot = form_snapshot(page)
        failed = client.post("/cms/save/post/linked", data={"revision": revision, "snapshot": snapshot, 'relationship:field:["relations"]': "true", 'field:["relations"]': ["", "post/deleted"]})
        assert failed.status_code == 422
        assert "post/deleted (missing" in html.unescape(failed.text)
        kanban = client.get("/cms/kanban?add=1")
        saved = client.post("/cms/kanban/create", data={"revision": token(kanban), "title": "Work", "column": "todo", "relationship:artifact_ids": "true", "artifact_ids": ["", "post/exact", "post/prefix"]})
        assert saved.status_code == 200
        assert client.app.state.kanban.read()["cards"][0]["artifact_ids"] == ["post/exact", "post/prefix"]


def test_course_table_updates_filters_and_escapes(author):
    course(author)
    chapter(author, plan={"summary": "Compare a | b\n<script>alert(1)</script>"})
    chapter(author, "private", visibility="private", plan={"summary": "Secret summary"})
    def rendered(mode):
        snapshot = author.snapshot()
        return _Generator(snapshot, author.root / ".tmp/table", mode).context(snapshot.state.courses and next(a for a in snapshot.state.artifacts if a.id == "course/demo"))
    preview = rendered("preview")
    assert "| Section | Chapter title | Summary |" in preview
    assert "Secret summary" in preview
    assert "a \\| b<br>" in preview and "<script>" not in preview
    production = rendered("production")
    assert "Secret summary" not in production
    author.organize_course("course/demo", "add-section", {"title": "New phase"}, author.inspect("course/demo")["revision"])
    author.organize_course("course/demo", "move-chapter", {"chapter": "course/demo/first", "section": "new-phase"}, author.inspect("course/demo")["revision"])
    author.update("course/demo/first", {"title": "New title", "plan": {"summary": "New summary"}})
    assert "| New phase | [New title]" in rendered("production")
    assert "New summary" in rendered("production")
    author.delete("course/demo/first")
    assert "New title" not in rendered("production")
    assert "No chapters to display yet." in rendered("production")


def test_long_draft_keeps_every_character_and_limits_cells(author):
    body = "## Outline\n\n" + "A detailed plan.\n\n" * 1800
    author.create_post("long", {"title": "Long", "planned": {"content": body, "references": "Source"}})
    record = author.inspect("post/long")
    author.start("post/long")
    notebook = nbformat.read(author.root / record["source_path"], as_version=4)
    assert all(len(cell.source) <= 20_000 for cell in notebook.cells)
    assert "".join(cell.source for cell in notebook.cells) == record["plan"]


def test_api_brief_patch_preserves_unknown_fields_and_toc(author):
    course(author)
    chapter(author)
    author.update("course/demo", {"contract": {"planned": {"extension": "Keep the research note"}}})
    with TestClient(create_app(author.root)) as client:
        record = author.inspect("course/demo")
        changed = client.patch("/api/artifacts/course/demo", headers={"If-Match": record["revision"]}, json={"title": "Changed title", "contract": {"planned": {"outcomes": "An outcome"}}})
        assert changed.status_code == 200, changed.text
        saved = author.inspect("course/demo")
        assert saved["artifact"]["title"] == "Changed title"
        assert saved["contract"]["planned"]["extension"] == "Keep the research note"
        assert saved["contract"]["planned"]["summary"] == "Build a tool"
        assert saved["contract"]["toc"][0]["chapters"] == ["course/demo/first"]
        before = saved["revision"]
        failed = client.patch("/api/artifacts/course/demo", headers={"If-Match": before}, json={"title": "Should not save", "contract": {"toc": []}})
        assert failed.status_code == 422
        assert author.inspect("course/demo")["revision"] == before
        assert author.inspect("course/demo")["artifact"]["title"] == "Changed title"
        assert client.get("/cms/lookup?kind=chapter&parent=course/demo").json()["artifacts"][0]["id"] == "course/demo/first"


def test_single_resume_relationship_native_select_can_clear(author):
    author.create_post("one", {"title": "A linked article"})
    profile = author.read_data("profile")["data"]
    profile["projects"] = [{"title": "Work", "bullets": [], "artifact_id": "post/one"}]
    author.update_data("profile", profile)
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/resume?edit=profile")
        assert 'value="post/one" selected' in page.text
        revision, snapshot = form_snapshot(page)
        cleared = client.post("/cms/data/profile", data={"revision": revision, "snapshot": snapshot, "profile_view": "resume", 'field:["projects", "0", "artifact_id"]': ""})
        assert cleared.status_code == 200
        assert not author.read_data("profile")["data"]["projects"][0]["artifact_id"]
