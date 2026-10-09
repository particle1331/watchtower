"""Creation and editing share one intent-based form per authoring kind."""

import html
import json
import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot

from watchtower.api import create_app
from watchtower.services.content import ContentService

SECTION_ORDER = ["basics", "plan", "page", "notes"]
RETIRED = {"next_steps", "scope_notes", "takeaway", "prerequisites", "constraints", "summary_progression"}


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def section_ids(text: str) -> list[str]:
    return re.findall(r'<(?:section|dialog) id="([a-z]+)" class="(?:author-section|cms-dialog notes-dialog)', text)


def field_paths(text: str) -> list[list[str]]:
    names = re.findall(r'name="field:([^"]+)"', text)
    return [json.loads(html.unescape(name)) for name in names]


def course(author):
    author.create({"id": "course/demo", "kind": "course", "title": "Demo course", "path": "content/notebooks/courses/demo", "contract": {"purpose": "Teach", "audience": "Learners", "planned": {"outcomes": "Build it", "chapters": []}, "toc": [{"id": "main", "title": "", "chapters": []}]}})


@pytest.mark.parametrize("kind", ["post", "portfolio", "course", "chapter"])
def test_new_form_has_four_intent_sections_in_order(author, kind):
    if kind == "chapter":
        course(author)
    with TestClient(create_app(author.root)) as client:
        page = client.get(f"/cms/new?kind={kind}" + ("&parent=course/demo&section=main" if kind == "chapter" else "")).text
    assert section_ids(page) == SECTION_ORDER
    paths = field_paths(page)
    assert ["name"] in paths and ["title"] in paths
    assert not {path[-1] for path in paths} & RETIRED
    assert "Track a next step" not in page  # no saved entry yet, so nothing to link


def test_creation_maps_plan_fields_to_storage_and_starts_a_draft(author):
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/new?kind=post")
        revision = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        response = client.post("/cms/new?kind=post", data={
            "revision": revision, "kind": "post",
            'field:["name"]': "Gradient notes", 'field:["title"]': "Gradient notes",
            'field:["description"]': "The takeaway in one sentence.",
            'field:["planned", "content"]': "## Ideas\n\nExplain the update rule.",
            'field:["planned", "audience"]': "Students",
            'field:["planned", "evidence"]': "A worked example",
            'field:["planned", "references"]': "",
            'field:["tags"]': "ml\nnotes",
            'field:["internal_notes"]': "Open question about batch size",
            "start_draft": "1",
        }, follow_redirects=False)
    assert response.status_code == 303, response.text[:300]
    record = author.inspect("post/gradient-notes")
    assert record["artifact"]["description"] == "The takeaway in one sentence."
    assert record["artifact"]["planned"]["content"].startswith("## Ideas")
    assert record["artifact"]["internal_notes"] == "Open question about batch size"
    assert record["artifact"]["tags"] == ["ml", "notes"]
    assert record["artifact"]["lifecycle"] == "draft"
    assert record["artifact"]["visibility"] == "private"


def test_creation_error_keeps_submitted_values(author):
    with TestClient(create_app(author.root)) as client:
        revision = re.search(r'name="revision" value="([^"]+)"', client.get("/cms/new?kind=post").text)[1]
        response = client.post("/cms/new?kind=post", headers={"HX-Request": "true"}, data={
            "revision": revision, "kind": "post", 'field:["name"]': "Draft idea", 'field:["title"]': "",
            'field:["planned", "content"]': "Keep this outline",
        })
    assert response.status_code == 422
    assert "Keep this outline" in response.text


def test_editor_saves_plan_summary_and_notes_without_touching_legacy_keys(author):
    author.create({"id": "post/idea", "kind": "post", "title": "Idea", "path": "content/notebooks/posts/idea.ipynb", "description": "Old summary", "planned": {"content": "Outline", "next_steps": "Retired text stays put"}})
    with TestClient(create_app(author.root)) as client:
        editor = client.get("/cms/artifact/post/idea")
        assert section_ids(editor.text) == SECTION_ORDER
        assert 'Recommended to start' in editor.text
        assert 'name="field:[&#34;planned&#34;, &#34;next_steps&#34;]"' not in editor.text
        revision, snapshot = form_snapshot(editor)
        result = client.post("/cms/save/post/idea", data={"revision": revision, "snapshot": snapshot, 'field:["description"]': "New summary", 'field:["planned", "audience"]': "Readers", 'field:["internal_notes"]': "Decision noted"}, headers={"HX-Request": "true"})
    assert result.status_code == 200, result.text[:300]
    record = author.inspect("post/idea")
    assert record["artifact"]["description"] == "New summary"
    assert record["artifact"]["planned"]["audience"] == "Readers"
    assert record["artifact"]["internal_notes"] == "Decision noted"
    assert record["artifact"]["planned"]["next_steps"] == "Retired text stays put"


def test_editor_section_order_for_course_includes_outline(author):
    course(author)
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/courses/demo").text
    assert section_ids(page) == SECTION_ORDER
    assert 'id="outline"' in page
    assert 'href="#outline"' in page


def test_editor_task_action_creates_a_card_with_current_artifact_context(author):
    author.create({"id": "post/idea", "kind": "post", "title": "Idea", "path": "content/notebooks/posts/idea.ipynb",
                   "planned": {"content": "Explain a concrete example"}, "internal_notes": "Saved decision"})
    with TestClient(create_app(author.root)) as client:
        editor = client.get("/cms/artifact/post/idea").text
        link = re.search(r'<a class="button" href="([^"]+)">Create Kanban task</a>', editor)[1]
        page = client.get(html.unescape(link)).text
        assert re.search(r'<option value="post/idea" selected', page)
        assert 'open data-auto-open' in page
        assert not client.app.state.kanban.read()["cards"]
        revision = re.search(r'name="revision" value="([^"]+)"', page)[1]
        result = client.post("/cms/kanban/create", data={"revision": revision, "title": "Write the example",
                             "column": "todo", "artifact_ids": "post/idea"}, follow_redirects=False)
        assert result.status_code == 303
        context = client.app.state.kanban.context("card#1")
        assert context["card"]["artifact_ids"] == ["post/idea"]
        assert context["artifacts"][0]["plan"]["content"] == "Explain a concrete example"
        assert context["artifacts"][0]["internal_notes"] == "Saved decision"
    assert author.inspect("post/idea")["artifact"]["lifecycle"] == "planned"
