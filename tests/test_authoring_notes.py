"""Internal authoring context stays independent of notebook and publication state."""
import html

import nbformat
import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot
from test_content_service import author_body
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.models import route_for
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def create(author, kind):
    identifier = f'{kind}/notes'
    values = {'id': identifier, 'kind': kind, 'title': 'Notes example', 'description': 'Public summary', 'internal_notes': 'INTERNAL-NOTES-SENTINEL'}
    plan = {'content': 'SEED-OUTLINE-SENTINEL', 'next_steps': 'INTERNAL-NEXT-SENTINEL', 'extension': 'INTERNAL-LEGACY-SENTINEL'}
    if kind in {'course', 'chapter'}:
        parent = 'course/notes' if kind == 'course' else 'course/parent'
        author.create({'id': parent, 'kind': 'course', 'title': 'Course', 'path': f'content/notebooks/courses/{parent.split("/")[-1]}', 'description': 'Public course summary', 'internal_notes': 'INTERNAL-PARENT-SENTINEL', 'contract': {'purpose': 'SEED-PURPOSE-SENTINEL', 'audience': 'SEED-AUDIENCE-SENTINEL', 'planned': {**plan, 'summary': 'SEED-SUMMARY-SENTINEL', 'chapters': []}}})
        if kind == 'course':
            author.update(parent, {'internal_notes': values['internal_notes'], 'description': values['description']})
            return parent
        values.update(id='course/parent/notes', parent=parent, section='main', toc_title='Notes', path='content/notebooks/courses/parent/notes.ipynb', plan={**plan, 'lab_and_evidence': 'SEED-LAB-SENTINEL', 'summary': 'Public chapter summary'})
    elif kind == 'portfolio':
        values['detail'] = {'planned': {'introduction': plan['content'], 'what_it_contains': 'SEED-CONTENTS-SENTINEL', 'scope_notes': 'INTERNAL-SCOPE-SENTINEL', 'references': 'INTERNAL-REFERENCES-SENTINEL'}}
    else:
        values.update(path=f'content/notebooks/{kind}/notes.ipynb', planned=plan)
    author.create(values)
    return values['id']


@pytest.mark.parametrize('kind', ['post', 'personal', 'course', 'chapter', 'portfolio'])
@pytest.mark.parametrize('mode', ['preview', 'production'])
def test_generated_site_excludes_internal_context_at_every_stage(author, monkeypatch, kind, mode):
    monkeypatch.setattr('watchtower.services.build.build_resume_pdf', lambda stage: None)
    identifier = create(author, kind)
    for lifecycle in ['planned', 'draft', 'published']:
        if lifecycle == 'draft':
            if kind == 'chapter':
                author.start('course/parent')
            author.start(identifier)
            record = author.inspect(identifier)
            source = author.root / record['source_path']
            notebook = nbformat.read(source, as_version=4)
            assert notebook.cells[0].source == f"# {record['artifact']['title']}\n"
            assert len(notebook.cells) > 1
            assert record['artifact']['visibility'] == 'private'
            assert record['artifact']['internal_notes'] == 'INTERNAL-NOTES-SENTINEL'
            assert record['has_authored_content']
        elif lifecycle == 'published':
            if kind == 'chapter':
                author_body(author, 'course/parent')
                author.publish('course/parent')
            if kind == 'portfolio':
                figure = author.root / 'content/assets/notes.svg'
                figure.parent.mkdir(parents=True, exist_ok=True)
                figure.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
                author.update(identifier, {'detail': {'abstract': 'Public abstract', 'figure_path': 'content/assets/notes.svg', 'figure_caption': 'Public figure'}})
            author_body(author, identifier)
            author.publish(identifier)
        stage = BuildService(author.root).generate(mode)
        for path in stage.rglob('*'):
            if path.is_file() and path.suffix in {'.ipynb', '.md', '.qmd', '.yml', '.yaml', '.json', '.html'}:
                assert 'INTERNAL-' not in path.read_text(), path
        artifact = next(a for a in author.snapshot().state.artifacts if a.id == identifier)
        generated = stage / route_for(artifact)
        assert generated.exists() == (lifecycle == 'published' or mode == 'preview' and lifecycle == 'draft')
        if generated.exists():
            assert 'SEED-' in generated.read_text()
        assert 'INTERNAL-NOTES-SENTINEL' in author.inspect(identifier)['build_brief']


@pytest.mark.parametrize('kind', ['post', 'portfolio', 'course', 'chapter'])
def test_notes_cms_create_edit_conflict_and_api_preserve_notebook(author, kind):
    identifier = create(author, kind)
    author.start(identifier)
    source = author.root / author.inspect(identifier)['source_path']
    before = source.read_bytes()
    with TestClient(create_app(author.root)) as client:
        page = client.get(f'/cms/artifact/{identifier}')
        revision, snapshot = form_snapshot(page)
        assert 'Internal notes' in page.text
        saved = client.post(f'/cms/save/{identifier}', data={'revision': revision, 'snapshot': snapshot, 'field:["internal_notes"]': 'Saved notes\n\n- Follow up'}, follow_redirects=False)
        assert saved.status_code in {200, 303}, saved.text
        assert author.inspect(identifier)['artifact']['internal_notes'] == 'Saved notes\n\n- Follow up'
        stale = client.post(f'/cms/save/{identifier}', data={'revision': revision, 'snapshot': snapshot, 'field:["internal_notes"]': 'Unsaved notes <keep>'})
        assert stale.status_code == 412
        assert 'Unsaved notes <keep>' in html.unescape(stale.text)
        assert form_snapshot(stale)[0] == revision
        record = author.inspect(identifier)
        saved = client.patch(f'/api/artifacts/{identifier}', headers={'If-Match': record['revision']}, json={'internal_notes': ''})
        assert saved.status_code == 200, saved.text
        assert author.inspect(identifier)['artifact']['internal_notes'] == ''
        assert author.inspect(identifier)['artifact']['lifecycle'] == 'draft'
        assert source.read_bytes() == before


def test_cms_creates_notes_and_cli_edits_them_after_publication(author, monkeypatch):
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/new?kind=post')
        import re
        revision = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        created = client.post('/cms/new?kind=post', data={'revision': revision, 'name': 'new', 'title': 'New', 'visibility': 'public', 'internal_notes': 'Initial notes'}, follow_redirects=False)
        assert created.status_code == 303, created.text
    assert author.inspect('post/new')['artifact']['internal_notes'] == 'Initial notes'
    monkeypatch.chdir(author.root)
    runner = CliRunner()
    started = runner.invoke(app, ['start', 'post/new'])
    assert started.exit_code == 0, started.exception
    author_body(author, 'post/new')
    author.publish('post/new')
    source = author.root / author.inspect('post/new')['source_path']
    before = source.read_bytes()
    updated = runner.invoke(app, ['update', 'post/new', '--internal-notes', 'Future revision', '--planned-content', 'New outline'])
    assert updated.exit_code == 0, updated.exception
    record = author.inspect('post/new')
    assert record['artifact']['lifecycle'] == 'published'
    assert record['artifact']['internal_notes'] == 'Future revision'
    assert record['artifact']['planned']['content'] == 'New outline'
    assert source.read_bytes() == before


@pytest.mark.parametrize('kind', ['post', 'personal', 'course', 'chapter', 'portfolio'])
def test_renaming_a_scaffold_does_not_make_it_publishable(author, kind):
    identifier = create(author, kind)
    if kind == 'course':
        author.update(identifier, {'contract': {'purpose': '', 'audience': '', 'planned': {'summary': '', 'content': ''}}})
    elif kind == 'chapter':
        author.update(identifier, {'plan': {'content': '', 'lab_and_evidence': ''}})
    elif kind == 'portfolio':
        author.update(identifier, {'detail': {'planned': {'introduction': '', 'what_it_contains': ''}}})
    else:
        author.update(identifier, {'planned': {'content': ''}})
    author.start(identifier)
    author.update(identifier, {'title': 'Renamed scaffold'})
    record = author.inspect(identifier)
    notebook = nbformat.read(author.root / record['source_path'], as_version=4)
    assert notebook.cells[0].source.strip() == '# Renamed scaffold'
    assert not record['has_authored_content']
    with pytest.raises(ServiceError):
        author.publish(identifier)
