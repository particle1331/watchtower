"""Planning workflows share state, readiness, relationship and outline contracts."""

import html
import json
import re
from datetime import UTC, datetime

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


@pytest.mark.parametrize("kind", ["post", "course"])
@pytest.mark.parametrize("htmx", [False, True])
def test_post_and_course_save_and_publish(author, kind, htmx):
    if kind == "course":
        course(author)
        identifier, url = "course/demo", "/cms/courses/demo"
        field = 'field:["contract", "planned", "outcomes"]'
    else:
        author.create({"id": "post/idea", "kind": "post", "title": "Idea", "path": "content/notebooks/posts/idea.ipynb", "planned": {"content": "Post content"}})
        identifier, url = "post/idea", "/cms/artifact/post/idea"
        field = 'field:["planned", "audience"]'
    author.start(identifier)
    with TestClient(create_app(author.root)) as client:
        editor = client.get(url)
        assert 'form="artifact-editor-form" name="save_action" value="publish" data-save data-save-publish>Publish</button>' in editor.text
        assert editor.text.count('>Publish</button>') == 1
        assert 'Save and publish</button>' not in editor.text
        assert 'id="artifact-publish-action"' not in editor.text
        revision, snapshot = form_snapshot(editor)
        result = client.post(f"/cms/save/{identifier}", data={"revision": revision, "snapshot": snapshot, "save_action": "publish", 'field:["title"]': "Finished title", field: "Finished outcome"}, headers={"HX-Request": "true"} if htmx else {}, follow_redirects=False)
        assert result.status_code == (303 if kind == "course" and not htmx else 200), result.text
        record = author.inspect(identifier)
        assert record["artifact"]["title"] == "Finished title"
        assert record["artifact"]["lifecycle"] == "published"
        assert record["artifact"]["visibility"] == "public"
        if kind == "course":
            assert result.headers["hx-redirect" if htmx else "location"] == f"{url}#course-brief"
            assert record["contract"]["planned"]["outcomes"] == "Finished outcome"
        else:
            assert record["artifact"]["planned"]["audience"] == "Finished outcome"
            assert 'Return to draft' in result.text


@pytest.mark.parametrize("kind", ["post", "course"])
@pytest.mark.parametrize("failure", ["stale", "content"])
def test_post_and_course_save_and_publish_fail_atomically(author, kind, failure):
    author.create({"id": f"{kind}/idea", "kind": kind, "title": "Idea", "path": "content/notebooks/posts/idea.ipynb" if kind == "post" else "content/notebooks/courses/idea", "planned": {"content": "Post content"} if kind == "post" and failure != "content" else {}, **({"contract": {"purpose": "Course purpose" if failure != "content" else ""}} if kind == "course" else {})})
    identifier = f"{kind}/idea"
    author.start(identifier)
    with TestClient(create_app(author.root)) as client:
        editor = client.get(f"/cms/artifact/{identifier}")
        revision, snapshot = form_snapshot(editor)
        if failure == "content":
            assert 'data-save data-save-publish>Publish</button>' in editor.text
            assert 'data-blocked' not in editor.text
            assert 'The notebook has no body content yet.' in editor.text
        else:
            author.update(identifier, {"title": "Concurrent title"})
        before = author.inspect(identifier)
        result = client.post(f"/cms/save/{identifier}", data={"revision": revision, "snapshot": snapshot, "save_action": "publish", 'field:["title"]': "Unsaved title"}, headers={"HX-Request": "true"})
        assert result.status_code == (412 if failure == "stale" else 422), result.text
        assert "Unsaved title" in result.text
        if failure == "content":
            assert "Cannot publish: the notebook has no body content." in result.text
        assert token(result) == revision
        assert author.inspect(identifier)["artifact"] == before["artifact"]
        assert author.inspect(identifier)["artifact"]["lifecycle"] == "draft"


@pytest.mark.parametrize("parent_published", [False, True])
def test_chapter_save_and_publish_requires_public_published_parent(author, parent_published):
    course(author)
    author.start("course/demo")
    if parent_published:
        author.publish("course/demo")
    chapter(author, plan={"content": "Chapter content"})
    author.start("course/demo/first")
    parent = author.inspect("course/demo")["artifact"]
    with TestClient(create_app(author.root)) as client:
        revision, snapshot = form_snapshot(client.get("/cms/artifact/course/demo/first"))
        result = client.post("/cms/save/course/demo/first", data={"revision": revision, "snapshot": snapshot, "save_action": "publish", 'field:["title"]': "Finished chapter"}, headers={"HX-Request": "true"})
        assert result.status_code == (200 if parent_published else 422), result.text
        record = author.inspect("course/demo/first")["artifact"]
        assert record["lifecycle"] == ("published" if parent_published else "draft")
        assert record["title"] == ("Finished chapter" if parent_published else "First")
        assert author.inspect("course/demo")["artifact"] == parent
        if parent_published:
            assert result.headers["hx-redirect"] == "/cms/courses/demo#outline"
        else:
            assert "publish the public parent course first" in result.text


@pytest.mark.parametrize("kind", ["post", "portfolio", "course"])
def test_private_partial_plan_reopens_with_task_action(author, kind):
    with TestClient(create_app(author.root)) as client:
        page = client.get(f"/cms/new?kind={kind}")
        response = client.post(f"/cms/new?kind={kind}", data={"revision": token(page), 'field:["name"]': "idea", 'field:["title"]': "An idea", 'field:["internal_notes"]': "Investigate an example"}, follow_redirects=False)
        assert response.status_code == 303, response.text
        record = author.inspect(f"{kind}/idea")
        assert record["artifact"]["visibility"] == "private"
        assert record["missing_plan_fields"]
        assert "Investigate an example" in record["build_brief"]
        editor = client.get(response.headers["location"])
        assert 'data-editing="true"' in editor.text
        assert "Planning help &amp; saved brief" not in editor.text
        assert "Create Kanban task" in editor.text and "Not on the live site" in editor.text
        assert "Copy build brief" not in editor.text and 'id="saved-build-brief"' not in editor.text
        assert "Investigate an example" in editor.text
        started = author.start(f"{kind}/idea")
        assert started["artifact"]["lifecycle"] == "draft"
        assert not author.inspect(f"{kind}/idea")["has_authored_content"]
        assert not record["editor_url"]


def test_course_save_is_atomic_and_keeps_unrelated_contract_fields(author):
    course(author)
    contract = author.inspect("course/demo")["contract"]
    contract["planned"]["extension"] = "Keep this too"
    author.update_data("course/demo", contract)
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/courses/demo")
        revision, snapshot = form_snapshot(page)
        result = client.post("/cms/save/course/demo", data={"revision": revision, "snapshot": snapshot, 'field:["title"]': "Revised title", 'field:["contract", "planned", "outcomes"]': "Can build a tool"}, follow_redirects=False)
        assert result.status_code == 303, result.text
        record = author.inspect("course/demo")
        assert record["artifact"]["title"] == "Revised title"
        assert record["contract"]["planned"]["outcomes"] == "Can build a tool"
        assert record["contract"]["planned"]["extension"] == "Keep this too"
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
        result = client.post(path, data={"revision": token(page), 'field:["name"]': "first", 'field:["title"]': "First chapter", 'field:["parent"]': "course/demo", 'field:["section"]': "main", 'field:["plan", "summary"]': "A short summary"}, follow_redirects=False)
        assert result.status_code == 303, result.text
        assert result.headers["location"] == "/cms/courses/demo#outline"
        record = author.inspect("course/demo/first")
        assert record["chapter_plan"]["summary"] == "A short summary"
        assert record["missing_plan_fields"] == ["Outline", "Practice and evidence"]
        page = client.get("/cms/artifact/course/demo/first")
        revision, snapshot = form_snapshot(page)
        result = client.post("/cms/save/course/demo/first", data={"revision": revision, "snapshot": snapshot, 'field:["plan", "content"]': "Explain the idea", 'field:["plan", "lab_and_evidence"]': "Build and check"}, follow_redirects=False)
        assert result.status_code == 303
        record = author.inspect("course/demo/first")
        assert not record["missing_plan_fields"]
        author.start("course/demo/first", record["revision"])
        body = "\n".join(c.source for c in nbformat.read(author.root / record["source_path"], as_version=4).cells)
        assert body.count("# First chapter\n") == 1
        assert "Explain the idea" in body and "Build and check" in body
        brief = author.inspect("course/demo")["build_brief"]
        assert "First chapter" in brief
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
        result = client.post("/cms/new?kind=post", data={"revision": token(page), 'field:["name"]': "linked", 'field:["title"]': "Linked post", 'relationship:field:["relations"]': "true", 'field:["relations"]': ["", "post/prefix", "post/exact", "post/prefix"]}, follow_redirects=False)
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
    author.start("course/demo")
    author.publish("course/demo")
    for identifier in ("course/demo/first", "course/demo/private"):
        author.update(identifier, {"plan": {"content": "Teach the topic"}})
        author.start(identifier)
    author.publish("course/demo/first")
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


def test_long_plan_seeds_bounded_cells_and_preserves_plan(author):
    body = "## Outline\n\n" + "A detailed plan.\n\n" * 1800
    author.create_post("long", {"title": "Long", "planned": {"content": body, "references": "Source"}})
    record = author.inspect("post/long")
    author.start("post/long")
    notebook = nbformat.read(author.root / record["source_path"], as_version=4)
    assert all(len(cell.source) <= 20_000 for cell in notebook.cells)
    seeded = "".join(cell.source for cell in notebook.cells)
    assert body.strip() in seeded
    assert "## References\n\nSource" in seeded
    assert author.inspect("post/long")["plan"] == record["plan"]
    assert body in author.inspect("post/long")["build_brief"]


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


@pytest.mark.parametrize('abstract', ['', 'A handwritten summary.'])
def test_portfolio_abstract_create_start_and_edit(author, abstract):
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/new?kind=portfolio')
        assert 'name="field:[&#34;detail&#34;, &#34;abstract&#34;]"' in page.text
        assert 'name="description"' not in page.text
        assert 'can fill a first draft from Problem and What it contains' in page.text
        assert 'Paste the finished abstract here before publishing; publishing requires it.' in page.text
        assert 'portfolio card and entry page' in page.text
        created = client.post('/cms/new?kind=portfolio', data={'revision': token(page), 'field:["name"]': 'abstract', 'field:["title"]': 'Abstract example', 'field:["detail", "abstract"]': abstract, 'field:["detail", "planned", "introduction"]': 'Compare models.', 'field:["detail", "planned", "what_it_contains"]': 'Reports and checks.'}, follow_redirects=False)
        assert created.status_code == 303, created.text
        saved = author.inspect('portfolio/abstract')
        assert saved['detail']['abstract'] == (abstract or None)
        assert not saved['artifact']['description']
        author.start('portfolio/abstract')
        assert author.inspect('portfolio/abstract')['detail']['abstract'] == (abstract or 'Compare models. Reports and checks.')
        page = client.get('/cms/artifact/portfolio/abstract')
        assert 'Public description' not in page.text
        assert html.unescape(page.text).count('name="field:["detail", "abstract"]"') == 1
        assert 'Shown on the portfolio card and entry page.' in page.text
        assert 'can fill a first draft from Problem and What it contains' in page.text
        assert 'Paste the finished abstract here before publishing; publishing requires it.' in page.text
        revision, snapshot = form_snapshot(page)
        edited = client.post('/cms/save/portfolio/abstract', data={'revision': revision, 'snapshot': snapshot, 'field:["detail", "abstract"]': 'Edited abstract.'}, follow_redirects=False)
        assert edited.status_code == 303, edited.text
        assert author.inspect('portfolio/abstract')['detail']['abstract'] == 'Edited abstract.'
        stale = client.post('/cms/save/portfolio/abstract', data={'revision': revision, 'snapshot': snapshot, 'field:["detail", "abstract"]': 'Unsaved abstract.'})
        assert stale.status_code == 412 and 'Unsaved abstract.' in stale.text


def test_portfolio_legacy_description_is_preserved_as_abstract_on_save(author):
    author.create({'id': 'portfolio/legacy', 'kind': 'portfolio', 'title': 'Legacy', 'description': 'Existing summary.'})
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/artifact/portfolio/legacy')
        revision, snapshot = form_snapshot(page)
        assert json.loads(snapshot)['detail']['abstract'] == 'Existing summary.'
        assert not author.inspect('portfolio/legacy')['detail']['abstract']
        response = client.post('/cms/save/portfolio/legacy', data={'revision': revision, 'snapshot': snapshot}, follow_redirects=False)
        assert response.status_code == 303
        assert author.inspect('portfolio/legacy')['detail']['abstract'] == 'Existing summary.'


def test_editor_sections_separate_public_summary_plan_and_internal_notes(author):
    course(author)
    chapter(author, plan={"summary": "Reader summary", "content": "Teaching plan"}, internal_notes="Author decisions")
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/artifact/course/demo/first')
        assert page.status_code == 200
        sections = {name: re.search(rf'<section id="{name}" class="author-section.*?</section>', page.text, re.S)[0] for name in ['basics', 'plan', 'page']}
        sections["notes"] = re.search(r'<dialog id="notes".*?</dialog>', page.text, re.S)[0]
        assert 'Reader summary' in sections['page']
        assert 'Teaching plan' in sections['plan']
        assert 'Author decisions' in sections['notes']
        assert 'Author decisions' not in sections['page'] and 'Author decisions' not in sections['plan']
        assert 'Teaching plan' not in sections['page']
        revision, snapshot = form_snapshot(page)
        saved = client.post('/cms/save/course/demo/first', data={
            'revision': revision, 'snapshot': snapshot,
            'field:["plan", "summary"]': 'New reader summary',
            'field:["plan", "content"]': 'New teaching plan',
            'field:["internal_notes"]': 'New author decisions',
        }, follow_redirects=False)
        assert saved.status_code == 303
        record = author.inspect('course/demo/first')
        assert record['chapter_plan']['summary'] == 'New reader summary'
        assert record['chapter_plan']['content'] == 'New teaching plan'
        assert record['artifact']['internal_notes'] == 'New author decisions'


def test_course_outline_compact_controls_keep_native_actions_and_revisions(author):
    course(author)
    chapter(author)
    chapter(author, 'second')
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/courses/demo')
        assert page.status_code == 200
        assert 'id="outline"' in page.text
        assert page.text.count('class="outline-chapter"') == 2
        assert 'aria-label="Move First down"' in page.text
        assert 'Move First down</button>' not in page.text
        assert '<details class="chapter-details">' in page.text
        revision = token(page)
        moved = client.post('/cms/courses/demo/outline', data={
            'revision': revision, 'action': 'chapter-down', 'chapter': 'course/demo/first',
        }, follow_redirects=False)
        assert moved.status_code == 303
        assert author.inspect('course/demo')['contract']['toc'][0]['chapters'] == ['course/demo/second', 'course/demo/first']


def test_new_portfolio_editor_shows_the_creation_date(author, monkeypatch):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 8, 21, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr('watchtower.services.content.datetime', FixedDatetime)
    with TestClient(create_app(author.root)) as client:
        new = client.get('/cms/new?kind=portfolio')
        created = client.post('/cms/new?kind=portfolio', data={
            'revision': token(new), 'field:["name"]': 'dated', 'field:["title"]': 'Dated portfolio',
        }, follow_redirects=False)
        assert created.status_code == 303
        editor = client.get(created.headers['location'])
        assert 'name="field:["date"]" value="2026-10-09"' in html.unescape(editor.text)
