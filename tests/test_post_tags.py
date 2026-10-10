"""Entity editors expose tags and preserve managed routes and legacy labels."""
import html
import json
import re

import pytest
import yaml
from fastapi.testclient import TestClient
from test_api import author_workspace

from watchtower.api import create_app
from watchtower.api.cms import field_groups, form_fields
from watchtower.models import Artifact
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


@pytest.mark.parametrize(('kind', 'path'), [
    ('post', 'content/notebooks/posts/example.ipynb'),
    ('course', 'content/notebooks/courses/example'),
    ('chapter', 'content/notebooks/courses/example/chapter.ipynb'),
    ('portfolio', 'content/notebooks/portfolio/example.ipynb'),
    ('project', 'projects/example'),
    ('personal', 'content/notebooks/personal/example.ipynb'),
    ('gallery', 'backend/data/photos.yaml'),
])
def test_legacy_categories_merge_into_tags_and_are_removed_from_the_model(kind, path):
    values = {'id': f'{kind}/example', 'kind': kind, 'title': 'Example', 'path': path, 'tags': [' NLP ', 'meta'], 'categories': ['Meta', 'dev'], 'route': 'legacy/example.ipynb'}
    if kind == 'chapter':
        values.update(parent='course/example', toc_title='Example', section='main')
    artifact = Artifact.model_validate(values)
    assert artifact.tags == ([] if kind in {'course', 'chapter'} else ['NLP', 'meta', 'dev'])
    assert not hasattr(artifact, 'categories')
    assert artifact.route == 'legacy/example.ipynb'
    assert values['categories'] == ['Meta', 'dev']
    data = artifact.model_dump(mode='json')
    assert 'categories' not in data
    labels = {field['label'] for group in field_groups(form_fields(data), data) for field in group['fields']}
    assert ('tags' in labels) == (kind not in {'course', 'chapter'})
    assert ('tags' in data) == (kind not in {'course', 'chapter'})
    assert not {'route', 'categories'} & labels
    assert ('cover' in labels) == (kind == 'course')


def test_legacy_post_labels_are_visible_and_can_be_removed_in_cms(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    content.create_post('example', {'title': 'Example'})
    catalog_path = content.root / 'backend/data/catalog.yaml'
    catalog = yaml.safe_load(catalog_path.read_text())
    catalog['artifacts'][0].update(tags=['NLP'], categories=['meta', 'dev'])
    catalog_path.write_text(yaml.safe_dump(catalog))
    assert content.list('post')['artifacts'][0]['tags'] == ['NLP', 'meta', 'dev']
    with TestClient(create_app(content.root)) as client:
        listing = client.get('/cms/posts?tag=meta')
        assert 'Example' in listing.text and 'No matching entries' not in listing.text
        editor = client.get('/cms/artifact/post/example')
        assert '>Tags</span>' in editor.text
        assert '>Categories</span>' not in editor.text
        assert '>Cover</span>' not in editor.text
        assert '>Route</span>' not in editor.text
        assert 'NLP\nmeta\ndev' in editor.text
        revision = re.search(r'name="revision" value="([^"]+)"', editor.text)[1]
        snapshot = html.unescape(re.search(r'name="snapshot" value=\'([^\']+)\'', editor.text)[1])
        saved = client.post('/cms/save/post/example', data={'revision': revision, 'snapshot': snapshot, 'field:["tags"]': 'NLP'})
        assert saved.status_code == 200, saved.text
        assert content.inspect('post/example')['artifact']['tags'] == ['NLP']
        assert 'categories' not in content.inspect('post/example')['artifact']
        persisted = yaml.safe_load(catalog_path.read_text())['artifacts'][0]
        assert persisted['tags'] == ['NLP'] and 'categories' not in persisted
        assert json.loads(snapshot)['tags'] == ['NLP', 'meta', 'dev']


@pytest.mark.parametrize('kind', ['course', 'chapter'])
def test_course_and_chapter_legacy_labels_are_retired_without_changing_route(tmp_path, kind):
    content = ContentService(author_workspace(tmp_path))
    content.create({'id': 'course/example', 'kind': 'course', 'title': 'Example course', 'path': 'content/notebooks/courses/example', 'route': 'legacy/course/index.ipynb'})
    identifier = 'course/example'
    if kind == 'chapter':
        identifier += '/chapter'
        content.create({'id': identifier, 'kind': kind, 'title': 'Example chapter', 'path': 'content/notebooks/courses/example/chapter.ipynb', 'parent': 'course/example', 'section': 'main', 'toc_title': 'Example chapter', 'route': 'legacy/course/chapter.ipynb'})
    catalog_path = content.root / 'backend/data/catalog.yaml'
    catalog = yaml.safe_load(catalog_path.read_text())
    original = next(record for record in catalog['artifacts'] if record['id'] == identifier)
    route = original['route']
    original.update(tags=['NLP'], categories=['meta', 'dev'])
    catalog_path.write_text(yaml.safe_dump(catalog))
    assert 'tags' not in content.inspect(identifier)['artifact']
    assert 'tags' not in next(record for record in content.list()['artifacts'] if record['id'] == identifier)
    assert 'Tags:' not in content.read_plan(identifier)['build_brief']
    with TestClient(create_app(content.root)) as client:
        editor = client.get('/cms/artifact/' + identifier)
        assert ('>Card image</span>' in editor.text) == (kind == 'course')
        assert '>Tags</span>' not in editor.text
        assert '>Tags</span>' not in client.get('/cms/new?kind=' + kind).text
        assert '>Categories</span>' not in editor.text and '>Route</span>' not in editor.text
        revision, snapshot = editor_snapshot(editor)
        rejected = client.post('/cms/save/' + identifier, data={'revision': revision, 'snapshot': snapshot, 'field:["tags"]': 'NLP'})
        assert rejected.status_code == 422
        assert 'Courses and chapters do not support tags.' in rejected.text
        assert content.list()['revision'] == revision
        saved = client.post('/cms/save/' + identifier, data={'revision': revision, 'snapshot': snapshot, 'field:["internal_notes"]': 'Keep the outline.'})
        assert saved.status_code == 200, saved.text
        record = content.inspect(identifier)['artifact']
        assert 'tags' not in record and 'categories' not in record
        assert record['route'] == route
        persisted = next(record for record in yaml.safe_load(catalog_path.read_text())['artifacts'] if record['id'] == identifier)
        assert 'tags' not in persisted and 'categories' not in persisted


@pytest.mark.parametrize('kind', ['course', 'chapter'])
def test_course_and_chapter_tag_writes_are_rejected_atomically(tmp_path, kind):
    content = ContentService(author_workspace(tmp_path))
    course = {'id': 'course/example', 'kind': 'course', 'title': 'Example', 'path': 'content/notebooks/courses/example'}
    content.create(course)
    payload = course
    if kind == 'chapter':
        payload = {'id': 'course/example/chapter', 'kind': kind, 'title': 'Chapter', 'path': 'content/notebooks/courses/example/chapter.ipynb', 'parent': course['id'], 'section': 'main', 'toc_title': 'Chapter'}
        content.create(payload)
    before = content.list()['revision']
    for field in ('tags', 'categories'):
        with pytest.raises(ServiceError, match='do not support tags'):
            content.create({**payload, field: ['NLP']})
        with pytest.raises(ServiceError, match='do not support tags'):
            content.update(payload['id'], {field: ['NLP'], 'title': 'Unsaved'})
        with pytest.raises(ServiceError, match='do not support tags'):
            content.batch([{'id': payload['id'], 'patch': {field: ['NLP']}}], {})
        assert content.list()['revision'] == before
    with TestClient(create_app(content.root)) as client:
        response = client.patch('/api/artifacts/' + payload['id'], headers={'If-Match': before}, json={'tags': ['NLP']})
        assert response.status_code == 422
        assert 'do not support tags' in response.text
        response = client.post('/api/artifacts', headers={'If-Match': before}, json={**payload, 'tags': ['NLP']})
        assert response.status_code == 422
        assert 'do not support tags' in response.text
        assert content.list()['revision'] == before


def editor_snapshot(editor):
    revision = re.search(r'name="revision" value="([^"]+)"', editor.text)[1]
    snapshot = html.unescape(re.search(r'name="snapshot" value=\'([^\']+)\'', editor.text)[1])
    return revision, snapshot


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('route', 'custom/post.ipynb', 'Route is managed by the site'),
    ('cover', 'backend/assets/example.png', 'Only course card images'),
])
def test_cms_cannot_change_hidden_post_metadata(tmp_path, field, value, message):
    content = ContentService(author_workspace(tmp_path))
    content.create_post('example', {'title': 'Example'})
    catalog_path = content.root / 'backend/data/catalog.yaml'
    original = catalog_path.read_bytes()
    with TestClient(create_app(content.root)) as client:
        revision, snapshot = editor_snapshot(client.get('/cms/artifact/post/example'))
        saved = client.post('/cms/save/post/example', data={'revision': revision, 'snapshot': snapshot, f'field:["{field}"]': value})
        assert saved.status_code == 422
        assert message in saved.text
        assert catalog_path.read_bytes() == original
        assert content.list()['revision'] == revision


def test_cms_cannot_set_route_when_creating_post(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    original = (content.root / 'backend/data/catalog.yaml').read_bytes()
    with TestClient(create_app(content.root)) as client:
        saved = client.post('/cms/new?kind=post', data={'revision': content.list()['revision'], 'kind': 'post', 'field:["name"]': 'example', 'field:["title"]': 'Example', 'route': 'custom/post.ipynb'})
        assert saved.status_code == 422
        assert 'Route is managed by the site' in saved.text
        assert (content.root / 'backend/data/catalog.yaml').read_bytes() == original
