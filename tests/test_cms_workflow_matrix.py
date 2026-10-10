"""Exercise the minimal CMS paths for each authoring kind and CLI handoffs."""

import html
import json
import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.api.authoring import plan_path, summary_path
from watchtower.cli import app
from watchtower.services.content import ContentService


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def token(page):
    return re.search(r'name="revision" value="([^"]+)"', page.text)[1]


def field(path):
    return "field:" + json.dumps(path)


@pytest.mark.parametrize("kind", ["post", "course", "chapter", "portfolio"])
@pytest.mark.parametrize("start", [False, True])
def test_title_only_creation_and_edit_roundtrip(author, kind, start):
    if kind == "chapter":
        author.create({"id": "course/parent", "kind": "course", "title": "Parent", "path": "content/notebooks/courses/parent"})
    with TestClient(create_app(author.root)) as client:
        url = f"/cms/new?kind={kind}"
        page = client.get(url)
        assert page.status_code == 200
        name_control = re.search(r'<input[^>]*name="field:\[&#34;name&#34;\]"[^>]*>', page.text)[0]
        assert " required" not in name_control
        assert 'Save this plan to add a linked Kanban' in page.text
        assert 'data-summary-prompt=' not in page.text
        assert 'featured_image' not in page.text  # Add uploads after an entry exists.
        data = {"revision": token(page), "kind": kind, field(["title"]): "Minimal entry"}
        if kind == "chapter":
            data.update({field(["parent"]): "course/parent", field(["section"]): "main"})
        if start:
            data["start_draft"] = "1"
        created = client.post(url, data=data, follow_redirects=False)
        assert created.status_code == 303, created.text
        identity = "course/parent/minimal-entry" if kind == "chapter" else f"{kind}/minimal-entry"
        record = author.inspect(identity)
        assert record["artifact"]["lifecycle"] == ("draft" if start else "planned")
        assert record["artifact"]["visibility"] == "private"
        assert record["has_source"] == start
        editor_url = "/cms/courses/minimal-entry" if kind == "course" else f"/cms/artifact/{identity}"
        page = client.get(editor_url)
        revision, snapshot = form_snapshot(page)
        key = "introduction" if kind == "portfolio" else "purpose" if kind == "course" else "content"
        data = {
            "revision": revision, "snapshot": snapshot,
            field(["title"]): "Revised title",
            field(plan_path(kind, key)): "A concrete writing brief.",
            field(summary_path(kind)): "A public summary.",
            field(["internal_notes"]): "A private author decision.",
        }
        if kind not in {"course", "chapter"}:
            data[field(["tags"])] = "testing\nTesting\nworkflow"
        assert ('>Tags</span>' in page.text) == (kind not in {"course", "chapter"})
        saved = client.post(f"/cms/save/{identity}", data=data, headers={"HX-Request": "true"})
        assert saved.status_code == 200, re.findall(r"<pre>(.*?)</pre>", saved.text, re.S)
        record = author.inspect(identity)
        assert record["artifact"]["title"] == "Revised title"
        if kind in {"course", "chapter"}:
            assert "tags" not in record["artifact"]
        else:
            assert record["artifact"]["tags"] == ["testing", "workflow"]
        assert record["artifact"]["internal_notes"] == "A private author decision."
        plan = author.read_plan(identity)
        assert plan["summary"] == "A public summary."
        assert plan["plan"][key] == "A concrete writing brief."
        # A stale form must keep the user's input and must not save it.
        stale = client.post(f"/cms/save/{identity}", data={**data, field(["title"]): "Unsaved title"})
        assert stale.status_code == 412
        assert "Unsaved title" in stale.text
        assert author.inspect(identity)["artifact"]["title"] == "Revised title"
        if not start:
            fresh = client.get(editor_url)
            started = client.post(f"/cms/action/start/{identity}", data={"revision": token(fresh)})
            assert started.status_code == 200, started.text
            assert author.inspect(identity)["artifact"]["lifecycle"] == "draft"


def test_cli_changes_surface_in_cms_and_board_tokens_survive_content_edits(author, monkeypatch):
    monkeypatch.chdir(author.root)
    runner = CliRunner()
    created = runner.invoke(app, ["new", "post", "handoff", "--title", "CLI handoff"])
    assert created.exit_code == 0, created.output
    with TestClient(create_app(author.root)) as client:
        editor = client.get('/cms/artifact/post/handoff')
        revision, snapshot = form_snapshot(editor)
        saved = client.post('/cms/save/post/handoff', data={
            'revision': revision, 'snapshot': snapshot,
            field(['planned', 'content']): 'A CMS-authored outline.',
        })
        assert saved.status_code == 200
        plan = runner.invoke(app, ['plan', 'post/handoff'])
        assert plan.exit_code == 0 and 'A CMS-authored outline.' in plan.output
        board = runner.invoke(app, ['kanban', 'ls'])
        assert board.exit_code == 0
        board_revision = json.loads(board.output)['board_revision']
        updated = runner.invoke(app, ['update', 'post/handoff', '--internal-notes', 'From CLI'])
        assert updated.exit_code == 0, updated.output
        added = runner.invoke(app, ['kanban', 'add', '--title', 'Write the draft', '--link', 'post/handoff', '--expected-revision', board_revision])
        assert added.exit_code == 0, added.output
        card = json.loads(added.output)['card']
        page = client.get('/cms/kanban')
        assert 'Write the draft' in page.text and card['ref'] in page.text
        moved = client.post('/cms/kanban/move', data={
            'revision': json.loads(added.output)['board_revision'],
            'card_id': card['ref'], 'column': 'review',
        }, follow_redirects=False)
        assert moved.status_code == 303, moved.text
        board = json.loads(runner.invoke(app, ['kanban', 'ls']).output)
        assert board['cards'][0]['column'] == 'review'
        assert author.inspect('post/handoff')['artifact']['lifecycle'] == 'planned'


def test_course_outline_is_default_and_section_actions_are_open(author):
    author.create({'id': 'course/demo', 'kind': 'course', 'title': 'Demo', 'path': 'content/notebooks/courses/demo'})
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/courses/demo')
        assert 'data-default-pane="outline"' in page.text
        assert '<details class="section-management"' not in page.text
        assert '<details class="outline-add"' not in page.text
        assert 'name="action" value="rename-section"' in page.text
        assert 'name="action" value="add-section"' in page.text
        assert 'Create Kanban task' in html.unescape(page.text)
        assert 'Copy source path' in page.text


def test_cms_kanban_form_survives_unrelated_content_edits(author):
    author.create_post('idea', {'title': 'Idea'})
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/kanban?add=1&link=post/idea')
        revision = token(page)
        assert revision.startswith('kanban:')
        author.update('post/idea', {'internal_notes': 'An unrelated content edit'})
        created = client.post('/cms/kanban/create', data={
            'revision': revision, 'title': 'Write the draft', 'column': 'todo', 'artifact_ids': 'post/idea',
        }, follow_redirects=False)
        assert created.status_code == 303, created.text
        # That same form now conflicts with the board edit and preserves its text.
        stale = client.post('/cms/kanban/create', data={
            'revision': revision, 'title': 'Unsaved next task', 'column': 'todo',
        })
        assert stale.status_code == 412 and 'Unsaved next task' in stale.text


@pytest.mark.parametrize('kind', ['post', 'course', 'chapter', 'portfolio'])
def test_failed_publish_then_save_keeps_metadata_edits(author, kind):
    if kind == 'chapter':
        author.create({'id': 'course/parent', 'kind': 'course', 'title': 'Parent', 'path': 'content/notebooks/courses/parent'})
    with TestClient(create_app(author.root)) as client:
        url = f'/cms/new?kind={kind}'
        data = {'revision': token(client.get(url)), 'kind': kind, field(['title']): 'Retry entry', 'start_draft': '1'}
        if kind == 'chapter':
            data.update({field(['parent']): 'course/parent', field(['section']): 'main'})
        assert client.post(url, data=data, follow_redirects=False).status_code == 303
        identity = 'course/parent/retry-entry' if kind == 'chapter' else f'{kind}/retry-entry'
        revision, snapshot = form_snapshot(client.get(f'/cms/artifact/{identity}'))
        edits = {field(['title']): 'Edited title', field(summary_path(kind)): 'Edited summary', field(['internal_notes']): 'Keep this decision'}
        failed = client.post(f'/cms/save/{identity}', data={
            'revision': revision, 'snapshot': snapshot, 'save_action': 'publish', **edits,
        }, headers={'HX-Request': 'true'})
        assert failed.status_code == 422
        assert 'Edited title' in failed.text and 'Edited summary' in failed.text
        assert author.inspect(identity)['artifact']['title'] == 'Retry entry'
        retry_revision, retry_snapshot = form_snapshot(failed)
        assert retry_revision == revision
        assert json.loads(retry_snapshot)['title'] == 'Retry entry'
        saved = client.post(f'/cms/save/{identity}', data={
            'revision': retry_revision, 'snapshot': retry_snapshot, **edits,
        }, headers={'HX-Request': 'true'})
        assert saved.status_code == 200, re.findall(r'<pre>(.*?)</pre>', saved.text, re.S)
        assert author.inspect(identity)['artifact']['title'] == 'Edited title'
        assert author.read_plan(identity)['summary'] == 'Edited summary'
        assert author.inspect(identity)['artifact']['internal_notes'] == 'Keep this decision'
        assert author.inspect(identity)['artifact']['lifecycle'] == 'draft'
