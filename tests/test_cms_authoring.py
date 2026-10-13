"""Creation and editing share one intent-based form per authoring kind."""

import html
import json
import re

import nbformat
import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot, portfolio_image_bytes

from watchtower.api import create_app
from watchtower.services.content import ContentService

SECTION_ORDER = ["basics", "plan", "page", "notes"]
COURSE_SECTION_ORDER = ["basics", "home", "page", "notes"]
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
    author.create({"id": "course/demo", "kind": "course", "title": "Demo course", "path": "content/notebooks/courses/demo", "contract": {"planned": {"outcome": "Build it", "description": "Teach", "prerequisites": "Learners", "chapters": []}, "toc": [{"id": "main", "title": "", "chapters": []}]}})


@pytest.mark.parametrize("kind", ["post", "portfolio", "course", "chapter"])
def test_new_form_has_four_intent_sections_in_order(author, kind):
    if kind == "chapter":
        course(author)
    with TestClient(create_app(author.root)) as client:
        page = client.get(f"/cms/new?kind={kind}" + ("&parent=course/demo&section=main" if kind == "chapter" else "")).text
    expected = COURSE_SECTION_ORDER if kind == "course" else ["basics", "page", "plan", "notes"]
    assert section_ids(page) == expected
    paths = field_paths(page)
    assert ["name"] in paths and ["title"] in paths
    if kind == 'chapter':
        assert [list(path) for path in dict.fromkeys(map(tuple, paths))] == [
            ['title'], ['name'], ['parent'], ['section'], ['toc_title'], ['plan', 'summary'], ['relations'],
            ['plan', 'introduction'], ['plan', 'content'], ['plan', 'lab_and_evidence']]
        assert 'featured_image' not in page and ['tags'] not in paths
    # Course homes own a live Prerequisites field; the retired name only applies to other kinds.
    assert not {path[-1] for path in paths} & (RETIRED - {"prerequisites"} if kind == "course" else RETIRED)
    assert "Track a next step" not in page  # no saved entry yet, so nothing to link


def test_portfolio_plan_upload_and_start_keep_metadata_and_seed_three_sections(author):
    author.create_post('related', {'title': 'Related post', 'planned': {'content': 'Related body'}})
    author.start('post/related')
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/new?kind=portfolio')
        paths = [list(path) for path in dict.fromkeys(map(tuple, field_paths(page.text)))]
        assert paths == [['title'], ['name'], ['detail', 'abstract'], ['detail', 'figure_path'],
                         ['detail', 'figure_caption'], ['detail', 'project_path'], ['relations'],
                         ['detail', 'planned', 'introduction'], ['detail', 'planned', 'content'], ['detail', 'planned', 'evidence']]
        assert 'name="featured_image"' in page.text
        image = portfolio_image_bytes()
        created = client.post('/cms/new?kind=portfolio', data={
            'revision': re.search(r'name="revision" value="([^"]+)"', page.text)[1],
            'field:["title"]': 'Project plan', 'field:["detail", "abstract"]': 'Listing abstract.',
            'field:["detail", "figure_caption"]': 'Listing caption.',
            'field:["detail", "project_path"]': 'projects/custom-code',
            'field:["detail", "planned", "introduction"]': 'The problem body.',
            'field:["detail", "planned", "content"]': 'The content body.',
            'field:["detail", "planned", "evidence"]': 'The evidence body.',
            'field:["relations"]': 'post/related',
        }, files={'featured_image': ('figure.png', image, 'image/png')}, follow_redirects=False)
        assert created.status_code == 303, created.text
        plan = author.inspect('portfolio/project-plan')
        assert plan['artifact']['lifecycle'] == 'planned'
        assert not (author.root / plan['source_path']).exists()
        assert plan['detail']['abstract'] == 'Listing abstract.'
        assert plan['detail']['figure_caption'] == 'Listing caption.'
        assert (author.root / plan['detail']['figure_path']).read_bytes() == image
        assert plan['detail']['project_path'] == 'projects/custom-code'
        assert plan['artifact']['relations'] == ['post/related']
        assert 'tags' not in plan['artifact']
        started = author.start('portfolio/project-plan', plan['revision'])
        cells = nbformat.read(author.root / started['source_path'], as_version=4).cells
        assert [cell.source.strip() for cell in cells] == ['# Project plan', '## The problem\n\nThe problem body.',
                                                        '## Planned content\n\nThe content body.', '## Planned evidence\n\nThe evidence body.']
        draft = client.get(created.headers['location'])
        paths = [list(path) for path in dict.fromkeys(map(tuple, field_paths(draft.text)))]
        assert ['tags'] not in paths
        assert not any('planned' in path for path in paths)
        assert paths[:9] == [['title'], ['visibility'], ['date'], ['lifecycle'], ['detail', 'abstract'], ['detail', 'figure_path'],
                            ['detail', 'figure_caption'], ['detail', 'project_path'], ['relations']]
        saved = author.inspect('portfolio/project-plan')
        assert saved['detail']['abstract'] == plan['detail']['abstract']
        assert saved['detail']['figure_path'] == plan['detail']['figure_path']


@pytest.mark.parametrize('failure', ['invalid_image', 'stale', 'invalid_relation'])
def test_portfolio_plan_creation_upload_failure_is_atomic(author, failure):
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/new?kind=portfolio')
        revision = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        if failure == 'stale':
            author.create_post('concurrent', {'title': 'Concurrent'})
        before = author.snapshot().revision
        result = client.post('/cms/new?kind=portfolio', data={
            'revision': revision, 'field:["title"]': 'Failed project',
            'field:["detail", "figure_caption"]': 'Keep this caption.',
            'field:["relations"]': 'post/missing' if failure == 'invalid_relation' else '',
        }, files={'featured_image': ('figure.png', b'invalid' if failure == 'invalid_image' else portfolio_image_bytes(), 'image/png')})
        assert result.status_code in (409, 412, 422)
        assert 'Keep this caption.' in result.text
        assert author.snapshot().revision == before
        assert not list((author.root / 'backend/assets/portfolio').glob('*'))


def test_creation_maps_plan_fields_to_storage_and_starts_a_draft(author):
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/new?kind=post")
        paths = [list(path) for path in dict.fromkeys(map(tuple, field_paths(page.text)))]
        assert paths == [['title'], ['name'], ['description'], ['tags'], ['relations'],
                         ['planned', 'introduction'], ['planned', 'content'], ['planned', 'evidence']]
        assert 'featured_image' not in page.text
        revision = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        response = client.post("/cms/new?kind=post", data={
            "revision": revision, "kind": "post",
            'field:["name"]': "Gradient notes", 'field:["title"]': "Gradient notes",
            'field:["description"]': "The takeaway in one sentence.",
            'field:["planned", "content"]': "## Ideas\n\nExplain the update rule.",
            'field:["planned", "introduction"]': "Understand the update rule.",
            'field:["planned", "evidence"]': "A worked example",
            'field:["tags"]': "ml\nnotes",
            "start_draft": "1",
        }, follow_redirects=False)
    assert response.status_code == 303, response.text[:300]
    record = author.inspect("post/gradient-notes")
    assert record["artifact"]["description"] == "The takeaway in one sentence."
    assert "Explain the update rule." in "\n".join(c.source for c in nbformat.read(author.root / record["source_path"], as_version=4).cells)
    assert "planned" not in record["artifact"]
    assert record["artifact"]["internal_notes"] == ""
    assert record["artifact"]["tags"] == ["ml", "notes"]
    assert record["artifact"]["lifecycle"] == "draft"
    assert record["artifact"]["visibility"] == "private"
    cells = nbformat.read(author.root / record['source_path'], as_version=4).cells
    assert [cell.source.splitlines()[0] for cell in cells] == ['# Gradient notes', '## The problem', '## Planned content', '## Planned evidence']
    with TestClient(create_app(author.root)) as client:
        draft_paths = field_paths(client.get('/cms/artifact/post/gradient-notes').text)
    assert draft_paths[:4] == [['title'], ['visibility'], ['date'], ['lifecycle']]
    assert ['description'] in draft_paths and ['tags'] in draft_paths and ['relations'] in draft_paths
    assert not any('planned' in path for path in draft_paths)


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
        assert section_ids(editor.text) == ['basics', 'page', 'plan', 'notes']
        assert 'Recommended to start' in editor.text
        assert 'name="field:[&#34;planned&#34;, &#34;next_steps&#34;]"' not in editor.text
        revision, snapshot = form_snapshot(editor)
        result = client.post("/cms/save/post/idea", data={"revision": revision, "snapshot": snapshot, 'field:["description"]': "New summary", 'field:["planned", "introduction"]': "Readers need context."}, headers={"HX-Request": "true"})
    assert result.status_code == 200, result.text[:300]
    record = author.inspect("post/idea")
    assert record["artifact"]["description"] == "New summary"
    assert record["artifact"]["planned"]["introduction"] == "Readers need context."
    assert record["artifact"]["internal_notes"] == ""
    assert record["artifact"]["planned"]["next_steps"] == "Retired text stays put"


def test_editor_section_order_for_course_includes_outline(author):
    course(author)
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/courses/demo").text
    assert section_ids(page) == COURSE_SECTION_ORDER
    assert 'id="outline"' in page
    assert 'href="#outline"' in page


def test_editor_task_action_creates_a_card_with_current_artifact_context(author):
    author.create({"id": "post/idea", "kind": "post", "title": "Idea", "path": "content/notebooks/posts/idea.ipynb",
                   "planned": {"content": "Explain a concrete example"}})
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
        assert context["artifacts"][0]["internal_notes"] == ""
    assert author.inspect("post/idea")["artifact"]["lifecycle"] == "planned"
