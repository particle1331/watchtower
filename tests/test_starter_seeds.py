"""Starter inputs are temporary authoring state, never committed page fields."""
import json

import pytest
from test_api import author_workspace
from test_plan_authority import entry
from typer.testing import CliRunner

from watchtower.cli import app
from watchtower.models import Artifact, ChapterPlan, PortfolioEntry
from watchtower.services.content import CATALOG, ContentService, yaml_bytes
from watchtower.services.starter_seeds import StarterSeedMigration
from watchtower.services.workspace import ServiceError, load_yaml


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


def stored_seed(author, identifier, kind):
    if kind == 'post':
        catalog = load_yaml(author.store.inputs()[CATALOG], CATALOG)
        return next(item for item in catalog['artifacts'] if item['id'] == identifier).get('planned', {})
    if kind == 'portfolio':
        return next(item for item in author.read_data('portfolio')['data']['entries'] if item['id'] == identifier).get('planned', {})
    row = next(item for item in author.read_data('course/parent')['data']['planned']['chapters'] if item['chapter_id'] == identifier)
    return {key: value for key, value in row.items() if key not in {'chapter_id', 'section', 'summary'}}


@pytest.mark.parametrize('kind', ['post', 'portfolio', 'chapter'])
def test_start_moves_seed_into_notebook_and_removes_it_from_active_records(author, kind):
    identifier, data = entry(author, kind)
    author.create(data)
    saved = stored_seed(author, identifier, kind)
    started = author.start(identifier)
    source = author.root / started['source_path']
    assert b'INITIAL-INTENT' in source.read_bytes()
    assert stored_seed(author, identifier, kind) == {}
    archive = author.root / started['starter_seed_archive']
    assert json.loads((archive / 'record.json').read_text())['starter_seeds'][identifier] == saved
    before = source.read_bytes()
    author.update(identifier, {'internal_notes': 'Review the seeded body.'})
    assert source.read_bytes() == before and stored_seed(author, identifier, kind) == {}
    if kind == 'chapter':
        assert author.read_plan(identifier)['summary'] == 'Public summary'


def test_metadata_schema_has_no_starter_body_fields():
    starter_keys = {'problem', 'introduction', 'content', 'evidence', 'lab_and_evidence', 'planned_content', 'planned_evidence'}
    for model in (Artifact, PortfolioEntry, ChapterPlan):
        assert not starter_keys & model.model_fields.keys()


def test_seed_consumption_is_atomic_when_start_fails(author):
    author.create_post('large', {'title': 'Large', 'planned': {'content': '```python\n' + 'x' * 20_000 + '\n```'}})
    before = author.store.inputs()
    with pytest.raises(ServiceError, match='split it before starting'):
        author.start('post/large')
    assert author.store.inputs() == before
    assert not list((author.root / 'archive/starter-seeds').glob('*'))


def test_migration_cleans_legacy_consumed_seeds_and_preserves_plans_and_notebooks(author):
    author.create_post('started', {'title': 'Started', 'planned': {'content': 'Accepted body.'}})
    source = author.root / author.start('post/started')['source_path']
    author.create_post('planned', {'title': 'Planned', 'planned': {'content': 'Future body.'}})
    # Simulate metadata retained by the earlier Start implementation.
    with author.store.locked():
        files = author.store.inputs()
        catalog = load_yaml(files[CATALOG], CATALOG)
        record = next(item for item in catalog['artifacts'] if item['id'] == 'post/started')
        record['planned'] = {'content': 'Historical seed.', 'extension': 'Keep this history.'}
        author.store.commit({CATALOG: yaml_bytes(catalog)}, files, 'fixture: legacy consumed seed')
    before = author.store.inputs()
    body = source.read_bytes()
    with pytest.raises(ServiceError, match='consumed starter inputs'):
        author.validate()
    migration = StarterSeedMigration(author.root)
    review = migration.run()
    assert review['ready'] and not review['applied']
    assert [item['id'] for item in review['entries']] == ['post/started']
    assert author.store.inputs() == before
    applied = migration.run(apply=True, expected_revision=review['revision'])
    assert applied['applied']
    assert stored_seed(author, 'post/started', 'post') == {}
    assert stored_seed(author, 'post/planned', 'post') == {'content': 'Future body.'}
    assert source.read_bytes() == body
    archive = author.root / applied['archive_path']
    assert (archive / CATALOG).read_bytes() == before[CATALOG]
    assert json.loads((archive / 'record.json').read_text())['starter_seeds']['post/started'] == record['planned']
    assert migration.run()['entries'] == []
    with pytest.raises(ServiceError, match='stale workspace revision'):
        migration.run(apply=True, expected_revision=review['revision'])


def test_cli_exposes_seed_cleanup_as_an_explicit_migration(author, monkeypatch):
    monkeypatch.chdir(author.root)
    runner = CliRunner()
    result = runner.invoke(app, ['migrate', '--starter-seeds'])
    assert result.exit_code == 0, result.exception
    assert json.loads(result.output)['entries'] == []
    rejected = runner.invoke(app, ['migrate', '--starter-seeds', '--layout'])
    assert rejected.exit_code == 1 and 'cannot be combined' in str(rejected.exception)
