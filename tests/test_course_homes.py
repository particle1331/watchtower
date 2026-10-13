"""Course homes have one CMS authority; chapter and portfolio bodies keep notebooks."""
import html
import re

import nbformat
import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.models import CourseHome
from watchtower.services.build import _Generator
from watchtower.services.content import ContentService
from watchtower.services.course_homes import CourseHomeMigration
from watchtower.services.workspace import ServiceError


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def course(author, *, purpose=""):
    author.create({"id": "course/example", "kind": "course", "title": "Example",
                   "path": "content/notebooks/courses/example", "contract": {"planned": {"description": purpose}}})
    author.start("course/example")
    return "course/example"


def test_start_consumes_plan_into_cms_home_and_has_no_notebook(author, monkeypatch):
    identifier = course(author, purpose="Explain the mechanism.")
    record = author.inspect(identifier)
    assert record['source_path'] is None and record['editor_url'] is None
    assert record['contract']['home']['description'] == 'Explain the mechanism.'
    assert not (author.root / 'content/notebooks/courses/example/index.ipynb').exists()
    assert record['route'] == 'nb/courses/example/index.qmd'
    assert author.read_plan(identifier)['plan'] == {}
    with pytest.raises(ServiceError, match='consumed'):
        author.update(identifier, {'contract': {'planned': {'description': 'Stale replacement'}}})
    with pytest.raises(ServiceError, match='CMS-managed'):
        author.update(identifier, {'contract': {'home': None}})
    monkeypatch.chdir(author.root)
    context = CliRunner().invoke(app, ['context', identifier])
    assert context.exit_code == 0 and '"home"' in context.output
    assert 'backend/data/courses/example.yaml' in context.output
    result = CliRunner().invoke(app, ['cat', identifier])
    assert result.exit_code != 0 and 'CMS-managed' in str(result.exception)


def test_cms_saves_six_sections_publishes_and_preserves_notes_and_drafts(author):
    identifier = course(author)
    author.create_post('topic', {'title': 'A related topic', 'planned': {'content': 'Topic content'}})
    author.start('post/topic')
    author.publish('post/topic')
    author.create({'id': identifier + '/one', 'kind': 'chapter', 'title': 'Chapter One',
                   'path': 'content/notebooks/courses/example/one.ipynb', 'parent': identifier,
                   'toc_title': 'One', 'section': 'main', 'plan': {'content': 'Explain one.', 'summary': 'A chapter summary.'}})
    author.start(identifier + '/one')
    author.update(identifier, {'internal_notes': 'SECRET-NOTES', 'internal_todos': [{'text': 'SECRET-TODO', 'done': True}]})
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/courses/example')
        # The CMS-owned home has no notebook; outline chapters have their own source tools.
        home_tools = re.search(r'<div class="source-tools">(.*?)</div>', page.text, re.S)[1]
        assert 'Edit in VS Code' not in home_tools and 'Copy source path' not in home_tools
        assert 'purpose, intended audience, scope, and what to expect' in html.unescape(page.text)
        for label in ("Course outcome", 'Course description', 'Related topics',
                      'Requirements', 'Prerequisites', 'References'):
            assert label in html.unescape(page.text)
        assert 'Automatically generated from' not in page.text  # CMS editor no longer shows the generated-content note
        rendered = html.unescape(page.text)
        description = rendered.index('name="field:["contract", "home", "description"]"')
        assert rendered.index('</textarea>', description) < rendered.index('Explain the purpose', description)  # hints follow their input
        revision, snapshot = form_snapshot(page)
        result = client.post('/cms/save/' + identifier, data={'revision': revision, 'snapshot': snapshot,
            'field:["contract", "home", "outcome"]': '- Build a useful thing.',
            'field:["contract", "home", "description"]': '### Why this matters\n\nThe course description.',
            'field:["relations"]': 'post/topic',
            'field:["contract", "home", "requirements"]': 'Python 3.14+\nDocker installed\nAWS account',
            'field:["contract", "home", "prerequisites"]': 'Knowledge of React and basics of Python',
            'field:["contract", "home", "references"]': '[Outside material](https://example.com/source)\n[Second source](https://example.com/second)',
            'save_action': 'publish'}, follow_redirects=False)
        assert result.status_code == 303, result.text
        record = author.inspect(identifier)
        assert record['artifact']['lifecycle'] == 'published'
        assert record['artifact']['internal_notes'] == 'SECRET-NOTES'
        assert record['artifact']['internal_todos'][0]['done']
        assert record['contract']['home']['requirements'] == ['Python 3.14+', 'Docker installed', 'AWS account']
        assert record['contract']['home']['prerequisites'] == ['Knowledge of React and basics of Python']
        assert record['contract']['home']['references'] == [
            '[Outside material](https://example.com/source)', '[Second source](https://example.com/second)']
        # Partial API home patches preserve the other sections.
        patched = client.patch('/api/artifacts/' + identifier, headers={'If-Match': record['revision']}, json={'contract': {'home': {'prerequisites': ['Python and arrays.']}}})
        assert patched.status_code == 200, patched.text
        assert author.inspect(identifier)['contract']['home']['requirements'] == ['Python 3.14+', 'Docker installed', 'AWS account']
        stale = client.post('/cms/save/' + identifier, data={'revision': revision, 'snapshot': snapshot,
                              'field:["contract", "home", "description"]': 'Unsaved body <keep>'})
        assert stale.status_code == 412
        assert 'Unsaved body <keep>' in html.unescape(stale.text)
        assert form_snapshot(stale)[0] == revision
    snapshot = author.snapshot()
    for mode in ('preview', 'production'):
        stage = author.root / '.tmp' / mode
        generator = _Generator(snapshot, stage, mode)
        generator.course_home(next(a for a in snapshot.state.artifacts if a.id == identifier))
        body = (stage / 'nb/courses/example/index.qmd').read_text()
        assert re.findall(r'^## (.+)$', body, re.M) == ["Course outcome", 'Course description', 'Related topics', 'Course content', 'Prerequisites', 'References']
        assert 'SECRET-' not in body and 'Actualized' not in body
        assert 'A related topic' in body
        requirements = body.split('## Prerequisites\n\n', 1)[1].split('\n## References', 1)[0]
        references = body.split('## References\n\n', 1)[1]
        assert re.findall(r'^- (.+)$', requirements, re.M) == [
            'Python 3.14+', 'Docker installed', 'AWS account', 'Python and arrays.',
        ]
        assert re.findall(r'^- (.+)$', references, re.M) == [
            '[Outside material](https://example.com/source)', '[Second source](https://example.com/second)']
        assert ('A chapter summary.' in body) == (mode == 'preview')
        assert body.count('| Section | Chapter title | Summary |') == (1 if mode == 'preview' else 0)


def test_empty_related_topics_are_omitted_from_generated_home(author):
    identifier = course(author)
    author.update(identifier, {"contract": {"home": {"description": "There are no related topics."}}})
    author.publish(identifier)
    snapshot = author.snapshot()
    artifact = next(a for a in snapshot.state.artifacts if a.id == identifier)
    for mode in ('preview', 'production'):
        stage = author.root / '.tmp' / f'{mode}-empty-related'
        generator = _Generator(snapshot, stage, mode)
        generator.course_home(artifact)
        body = (stage / 'nb/courses/example/index.qmd').read_text()
        assert '## Related topics' not in body
        assert '## Prerequisites' not in body
        assert '## References' not in body


def test_legacy_home_fields_are_normalized_to_item_lists():
    home = CourseHome.model_validate({
        'hardware_access': '**Tools:** Docker installed\nAWS account',
        'knowledge': '**Knowledge:** Python and React',
        'references': '[Guide](https://example.com/guide)',
    })
    assert home.requirements == ['Docker installed', 'AWS account']
    assert home.prerequisites == ['Python and React']
    assert home.references == ['[Guide](https://example.com/guide)']


def test_empty_home_publish_is_rejected_and_unknown_related_ids_are_atomic(author):
    identifier = course(author)
    before = author.store.inputs()
    with pytest.raises(ServiceError, match='course-home content'):
        author.publish(identifier)
    with pytest.raises(ServiceError, match='unknown relation'):
        author.update(identifier, {'relations': ['post/missing'], 'contract': {'home': {'description': 'Useful prose'}}})
    assert author.store.inputs() == before


def legacy(author, cells=None):
    path = author.root / 'content/notebooks/courses/legacy/index.ipynb'
    path.parent.mkdir(parents=True)
    body = '# Legacy\n\n{{< include _course-context.md >}}\n\nIntro [outside](https://example.com/source).\n\n## Outcome\n\nBuild it.\n\n## Prerequisites\n\n**Knowledge:** Python.\n\n**Tools:** CPU.\n\n## Learning path\n\n| Chapter | Summary |\n| --- | --- |\n| [One](one.ipynb) | Legacy navigation |'
    nbformat.write(nbformat.v4.new_notebook(cells=cells or [nbformat.v4.new_markdown_cell(body)]), path)
    author.create({'id': 'course/legacy', 'kind': 'course', 'title': 'Legacy', 'lifecycle': 'draft', 'path': 'content/notebooks/courses/legacy'})
    author.create({'id': 'course/legacy/one', 'kind': 'chapter', 'title': 'One', 'parent': 'course/legacy', 'section': 'main', 'toc_title': 'One', 'path': 'content/notebooks/courses/legacy/one.ipynb'})
    return path


def test_migration_reviews_and_archives_exact_home_bytes_without_touching_chapters(author):
    source = legacy(author)
    author.start('course/legacy/one')
    chapter = author.root / 'content/notebooks/courses/legacy/one.ipynb'
    chapter_bytes, home_bytes = chapter.read_bytes(), source.read_bytes()
    migration = CourseHomeMigration(author.root)
    review = migration.run()
    assert not review['applied'] and source.read_bytes() == home_bytes
    home = review['courses'][0]['home']
    assert home['outcome'] == 'Build it.'
    assert home['requirements'] == ['CPU.'] and home['prerequisites'] == ['Python.']
    assert 'Legacy navigation' not in str(home) and 'include' not in str(home)
    author.update('course/legacy', {'internal_notes': 'New revision'})
    with pytest.raises(ServiceError, match='stale'):
        migration.run(apply=True, expected_revision=review['revision'])
    review = migration.run()
    applied = migration.run(apply=True, expected_revision=review['revision'])
    assert not source.exists() and chapter.read_bytes() == chapter_bytes
    assert (author.root / applied['courses'][0]['archive']).read_bytes() == home_bytes
    record = author.inspect('course/legacy')
    assert record['source_path'] is None and record['route'] == 'nb/courses/legacy/index.qmd'
    assert record['contract']['home']['description'].startswith('Intro')
    assert not migration.run()['courses']
    author.validate()


def test_migration_refuses_executable_home_without_partial_writes(author):
    legacy(author, [nbformat.v4.new_code_cell('print(1)')])
    before = author.store.inputs()
    with pytest.raises(ServiceError, match='Markdown-only'):
        CourseHomeMigration(author.root).run(apply=True)
    assert author.store.inputs() == before
