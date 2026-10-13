"""Chapter editing preserves its entry point across native and HTMX requests."""

import html
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot

from watchtower.api import create_app
from watchtower.services.content import ContentService


@pytest.fixture
def author(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    content.create({"id": "course/demo", "kind": "course", "title": "Demo course", "path": "content/notebooks/courses/demo",
                    "contract": {"planned": {"description": "Course home content."}}})
    content.start("course/demo")
    content.create({"id": "course/demo/first", "kind": "chapter", "title": "First chapter", "toc_title": "01. First",
                    "parent": "course/demo", "section": "main", "path": "content/notebooks/courses/demo/first.ipynb",
                    "plan": {"content": "Chapter content."}})
    return content


def form_action(page, identity):
    return html.unescape(re.search(r'<form id="' + identity + r'"[^>]* action="([^"]+)"', page.text)[1])


def chapter_link(page):
    return html.unescape(re.search(r'href="([^"]+)">01\. First</a>', page.text)[1])


@pytest.mark.parametrize("htmx", [False, True])
@pytest.mark.parametrize("publish", [False, True])
def test_listing_back_cancel_and_save_restore_filters_and_expanded_course(author, htmx, publish):
    author.start("course/demo/first")
    if publish:
        author.publish("course/demo")
    headers = {"HX-Request": "true"} if htmx else {}
    with TestClient(create_app(author.root)) as client:
        listing = client.get("/cms/courses?q=Demo+course&lifecycle=draft&visibility=private&page=1&page_size=25")
        # A published parent needs the corresponding listing filters.
        if publish:
            listing = client.get("/cms/courses?q=Demo+course&lifecycle=published&visibility=public&page=1&page_size=25")
        link = chapter_link(listing)
        editor = client.get(link)
        back = html.unescape(re.search(r'href="([^"]+)">← Back to Courses</a>', editor.text)[1])
        query = parse_qs(urlsplit(back).query)
        assert query == {"q": ["Demo course"], "lifecycle": ["published" if publish else "draft"],
                         "visibility": ["public" if publish else "private"], "page": ["1"], "page_size": ["25"],
                         "open_course": ["course/demo"]}
        assert urlsplit(back).fragment == "course-demo"
        assert f'data-cancel href="{html.escape(back, quote=True)}"' in editor.text
        revision, snapshot = form_snapshot(editor)
        payload = {"revision": revision, "snapshot": snapshot, 'field:["plan", "summary"]': "New table summary."}
        if publish:
            payload["save_action"] = "publish"
        result = client.post(form_action(editor, "artifact-editor-form"), headers=headers, data=payload, follow_redirects=False)
        assert result.status_code == (200 if htmx else 303), result.text
        assert result.headers["hx-redirect" if htmx else "location"] == back
        restored = client.get(back)
        assert '<details class="data-record course-chapters" open>' in restored.text
        assert '<input type="search" name="q" value="Demo course"' in restored.text
        assert author.inspect("course/demo/first")["chapter_plan"]["summary"] == "New table summary."
        if publish:
            assert author.inspect("course/demo/first")["artifact"]["lifecycle"] == "published"


@pytest.mark.parametrize("htmx", [False, True])
def test_outline_back_cancel_and_save_return_to_named_course(author, htmx):
    with TestClient(create_app(author.root)) as client:
        outline = client.get("/cms/courses/demo")
        link = html.unescape(re.search(r'href="([^"]+)">Edit</a>', outline.text)[1])
        editor = client.get(link)
        assert 'href="/cms/courses/demo#outline">← Back to Demo course</a>' in editor.text
        assert 'data-cancel href="/cms/courses/demo#outline"' in editor.text
        revision, snapshot = form_snapshot(editor)
        result = client.post(form_action(editor, "artifact-editor-form"),
                             data={"revision": revision, "snapshot": snapshot},
                             headers={"HX-Request": "true"} if htmx else {}, follow_redirects=False)
        assert result.headers["hx-redirect" if htmx else "location"] == "/cms/courses/demo#outline"


@pytest.mark.parametrize("failure", ["stale", "invalid"])
@pytest.mark.parametrize("htmx", [False, True])
def test_failed_save_keeps_origin_submitted_values_and_original_revision(author, failure, htmx):
    with TestClient(create_app(author.root)) as client:
        editor = client.get(chapter_link(client.get("/cms/courses?q=Demo&page_size=25")))
        revision, snapshot = form_snapshot(editor)
        if failure == "stale":
            author.update("course/demo", {"title": "Updated course"})
        payload = {"revision": revision, "snapshot": snapshot, 'field:["title"]': "Unsaved chapter title"}
        if failure == "invalid":
            payload['field:["relations"]'] = "post/missing"
        result = client.post(form_action(editor, "artifact-editor-form"), data=payload,
                             headers={"HX-Request": "true"} if htmx else {})
        assert result.status_code == (412 if failure == "stale" else 422), result.text
        assert "Unsaved chapter title" in result.text
        assert form_snapshot(result)[0] == revision
        assert "← Back to Courses" in result.text
        assert form_action(result, "artifact-editor-form") == form_action(editor, "artifact-editor-form")
        if failure == "stale":
            reload_url = html.unescape(re.search(r'href="([^"]+)">Reload saved values', result.text)[1])
            assert "← Back to Courses" in client.get(reload_url).text
        assert author.inspect("course/demo/first")["artifact"]["title"] == "First chapter"


def test_start_and_summary_task_keep_listing_origin(author):
    with TestClient(create_app(author.root)) as client:
        editor = client.get(chapter_link(client.get("/cms/courses?q=Demo")))
        revision, _ = form_snapshot(editor)
        started = client.post(form_action(editor, "artifact-start-action"), data={"revision": revision}, headers={"HX-Request": "true"})
        assert started.status_code == 200
        assert "← Back to Courses" in started.text
        revision, _ = form_snapshot(started)
        task = client.post(form_action(started, "artifact-summary-task-form"), data={"revision": revision}, follow_redirects=False)
        assert task.status_code == 303
        returned = client.get(task.headers["location"])
        assert "← Back to Courses" in returned.text
        assert "return_to=" in form_action(returned, "artifact-editor-form")


@pytest.mark.parametrize("origin", ["https://example.com/cms/courses", "//example.com/cms/courses", "/cms/kanban", "/cms/courses/other#outline", "/cms/courses\\evil", "/cms/courses\n"])
def test_invalid_return_targets_fall_back_to_parent_course(author, origin):
    with TestClient(create_app(author.root)) as client:
        editor = client.get("/cms/artifact/course/demo/first?" + urlencode({"return_to": origin}))
        assert 'href="/cms/courses/demo#outline">← Back to Demo course</a>' in editor.text
        assert 'data-cancel href="/cms/courses/demo#outline"' in editor.text


@pytest.mark.parametrize("started", [False, True])
def test_outline_disclosures_offer_the_same_developer_controls(author, started):
    if started:
        author.start("course/demo/first")
    with TestClient(create_app(author.root)) as client:
        outline = client.get("/cms/courses/demo")
        details = re.search(r'<details class="chapter-details">(.*?)</details>', outline.text, re.S)[1]
        expanded = details.split('<div class="chapter-expanded">')[1]
        assert '<code>course/demo/first</code>' in expanded
        assert f'data-copy="{author.root}/content/notebooks/courses/demo/first.ipynb">Copy source path</button>' in expanded
        assert 'href="/cms/kanban?add=1&amp;link=course/demo/first">Create Kanban task</a>' in expanded
        if started:
            assert 'Edit in VS Code ↗</a>' in expanded
            assert 'vscode://file/' in expanded
        else:
            assert 'href="/cms/plan/course/demo/first" data-plan-open' in expanded
            assert 'Edit in VS Code' not in expanded
