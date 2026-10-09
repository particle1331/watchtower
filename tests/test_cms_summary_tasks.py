"""Summary tasks carry saved authoring context without changing publication."""

import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot

from watchtower.api import create_app
from watchtower.services.content import ContentService


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def create_entry(author, kind):
    if kind == 'chapter':
        author.create({'id': 'course/parent', 'kind': 'course', 'title': 'Parent course',
                       'path': 'content/notebooks/courses/parent',
                       'contract': {'purpose': 'Teach a concrete skill'}, 'internal_notes': 'Parent decision'})
        identifier = 'course/parent/idea'
        data = {'parent': 'course/parent', 'section': 'main', 'toc_title': 'Idea', 'plan': {'content': 'Explain a concrete example'}}
    elif kind == 'course':
        identifier = 'course/idea'
        data = {'contract': {'purpose': 'Explain a concrete example'}}
    elif kind == 'portfolio':
        identifier = 'portfolio/idea'
        data = {'detail': {'planned': {'introduction': 'Explain a concrete example'}}}
    else:
        identifier = 'post/idea'
        data = {'planned': {'content': 'Explain a concrete example'}}
    path = {'course': 'content/notebooks/courses/idea', 'chapter': 'content/notebooks/courses/parent/idea.ipynb',
            'post': 'content/notebooks/posts/idea.ipynb', 'portfolio': 'content/notebooks/portfolio/idea.ipynb'}[kind]
    author.create({'id': identifier, 'kind': kind, 'title': 'A useful idea', 'path': path,
                   'internal_notes': 'Saved author decision', **data})
    return identifier


@pytest.mark.parametrize('kind', ['post', 'course', 'chapter', 'portfolio'])
@pytest.mark.parametrize('htmx', [False, True])
def test_summary_task_contains_saved_brief_and_context_commands(author, kind, htmx):
    identifier = create_entry(author, kind)
    with TestClient(create_app(author.root)) as client:
        page = client.get(f'/cms/artifact/{identifier}')
        revision, _ = form_snapshot(page)
        assert 'data-summary-task>' in page.text
        assert 'Copy prompt' not in page.text and 'data-summary-prompt' not in page.text
        before = author.snapshot().files
        result = client.post(f'/cms/summary-task/{identifier}', data={'revision': revision},
                             headers={'HX-Request': 'true'} if htmx else {}, follow_redirects=False)
        assert result.status_code == (200 if htmx else 303), result.text
        board = client.app.state.kanban.read()
        assert len(board['cards']) == 1
        card = board['cards'][0]
        assert card['ref'] == 'card#1' and card['column'] == 'todo'
        assert card['artifact_ids'] == [identifier]
        assert card['description'].startswith(f'Summary task for {identifier}.')
        assert author.read_plan(identifier)['build_brief'] in card['description']
        assert 'Explain a concrete example' in card['description']
        assert 'Saved author decision' in card['description']
        assert f'.venv/bin/wt plan {identifier}' in card['description']
        assert f'.venv/bin/wt context {identifier}' in card['description']
        assert '--summary <text> --expected-revision' in card['description']
        assert 'at most 80 words' in card['description'] if kind == 'portfolio' else 'one or two sentences' in card['description']
        if kind == 'chapter':
            assert 'Parent course' in card['description'] and 'Parent decision' in card['description']
        target = result.headers['hx-redirect' if htmx else 'location']
        if kind == 'course':
            assert target.startswith('/cms/courses/idea?summary_task=') and target.endswith('#course-brief')
        else:
            assert target.startswith(f'/cms/artifact/{identifier}?summary_task=') and target.endswith('#page')
        restored = client.get(target)
        assert f'task {card["ref"]} is ready' in restored.text
        assert f'/cms/kanban?edit={card["id"]}' in restored.text
        # Creating a task changes only the board, never the plan, notebook or state.
        after = author.snapshot().files
        assert {name: data for name, data in before.items() if name != 'backend/data/kanban.yaml'} == {
            name: data for name, data in after.items() if name != 'backend/data/kanban.yaml'}


def test_unfinished_task_is_reused_and_completed_task_can_be_replaced(author):
    identifier = create_entry(author, 'post')
    with TestClient(create_app(author.root)) as client:
        def add_task():
            revision = author.read_plan(identifier)['revision']
            return client.post(f'/cms/summary-task/{identifier}', data={'revision': revision}, follow_redirects=False)
        assert add_task().status_code == 303
        board = client.app.state.kanban.read()
        original = board['cards'][0]
        client.app.state.kanban.update(original['ref'], {'title': 'Edited task title', 'column': 'review'}, board['board_revision'])
        assert add_task().status_code == 303
        board = client.app.state.kanban.read()
        assert len(board['cards']) == 1 and board['cards'][0]['title'] == 'Edited task title'
        client.app.state.kanban.update(original['ref'], {'column': 'done'}, board['board_revision'])
        assert add_task().status_code == 303
        assert [card['ref'] for card in client.app.state.kanban.read()['cards']] == ['card#1', 'card#2']


@pytest.mark.parametrize('conflict', ['content', 'board', 'during_create'])
def test_summary_task_rejects_stale_context_without_creating_card(author, monkeypatch, conflict):
    identifier = create_entry(author, 'post')
    with TestClient(create_app(author.root)) as client:
        revision = author.read_plan(identifier)['revision']
        if conflict == 'content':
            author.update(identifier, {'internal_notes': 'A newer decision'})
        elif conflict == 'board':
            client.app.state.kanban.create({'title': 'Another task'})
        else:
            create = client.app.state.kanban.create
            def concurrently_changed(payload, token):
                author.update(identifier, {'internal_notes': 'A concurrent decision'})
                return create(payload, token)
            monkeypatch.setattr(client.app.state.kanban, 'create', concurrently_changed)
        response = client.post(f'/cms/summary-task/{identifier}', data={'revision': revision}, headers={'HX-Request': 'true'})
        assert response.status_code == 412
        assert 'Task was not created' in response.text
        assert re.search(r'name="revision" value="' + revision + '"', response.text)
        assert not any(card['artifact_ids'] == [identifier] for card in client.app.state.kanban.read()['cards'])


def test_summary_task_requires_revision_and_registered_artifact(author):
    identifier = create_entry(author, 'post')
    with TestClient(create_app(author.root)) as client:
        assert client.post(f'/cms/summary-task/{identifier}', data={}).status_code == 428
        assert client.post('/cms/summary-task/post/missing', data={'revision': author.read_plan(identifier)['revision']}).status_code == 404
        assert not client.app.state.kanban.read()['cards']
