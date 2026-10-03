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


@pytest.mark.parametrize(('kind', 'path'), [
    ('post', 'content/notebooks/posts/example.ipynb'),
    ('course', 'content/notebooks/courses/example'),
    ('chapter', 'content/notebooks/courses/example/chapter.ipynb'),
    ('portfolio', 'content/notebooks/portfolio/example.ipynb'),
    ('project', 'projects/example'),
    ('personal', 'content/notebooks/personal/example.ipynb'),
    ('gallery', 'content/data/photos.yaml'),
])
def test_entity_categories_merge_into_tags_and_managed_fields_are_hidden(kind, path):
    values = {'id': f'{kind}/example', 'kind': kind, 'title': 'Example', 'path': path, 'tags': [' NLP ', 'meta'], 'categories': ['Meta', 'dev'], 'route': 'legacy/example.ipynb'}
    if kind == 'chapter':
        values.update(parent='course/example', toc_title='Example', section='main')
    artifact = Artifact.model_validate(values)
    assert artifact.tags == ['NLP', 'meta', 'dev']
    assert artifact.categories == []
    assert artifact.route == 'legacy/example.ipynb'
    assert values['categories'] == ['Meta', 'dev']
    data = artifact.model_dump(mode='json')
    labels = {field['label'] for group in field_groups(form_fields(data), data) for field in group['fields']}
    assert 'tags' in labels
    assert not {'route', 'categories'} & labels
    assert ('cover' in labels) == (kind == 'course')


def test_legacy_post_labels_are_visible_and_can_be_removed_in_cms(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    content.create_post('example', {'title': 'Example'})
    catalog_path = content.root / 'content/data/catalog.yaml'
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
        assert content.inspect('post/example')['artifact']['categories'] == []
        persisted = yaml.safe_load(catalog_path.read_text())['artifacts'][0]
        assert persisted['tags'] == ['NLP'] and persisted['categories'] == []
        assert json.loads(snapshot)['tags'] == ['NLP', 'meta', 'dev']


def test_course_legacy_labels_can_be_removed_without_changing_route(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    content.create({'id': 'course/example', 'kind': 'course', 'title': 'Example course', 'path': 'content/notebooks/courses/example', 'route': 'legacy/course/index.ipynb'})
    catalog_path = content.root / 'content/data/catalog.yaml'
    catalog = yaml.safe_load(catalog_path.read_text())
    catalog['artifacts'][0].update(tags=['NLP'], categories=['meta', 'dev'])
    catalog_path.write_text(yaml.safe_dump(catalog))
    with TestClient(create_app(content.root)) as client:
        editor = client.get('/cms/artifact/course/example')
        assert '>Card image</span>' in editor.text
        assert '>Categories</span>' not in editor.text and '>Route</span>' not in editor.text
        revision, snapshot = editor_snapshot(editor)
        saved = client.post('/cms/save/course/example', data={'revision': revision, 'snapshot': snapshot, 'field:["tags"]': 'NLP'})
        assert saved.status_code == 200, saved.text
        record = content.inspect('course/example')['artifact']
        assert record['tags'] == ['NLP'] and record['categories'] == []
        assert record['route'] == 'legacy/course/index.ipynb'


def editor_snapshot(editor):
    revision = re.search(r'name="revision" value="([^"]+)"', editor.text)[1]
    snapshot = html.unescape(re.search(r'name="snapshot" value=\'([^\']+)\'', editor.text)[1])
    return revision, snapshot


@pytest.mark.parametrize(('field', 'value', 'message'), [
    ('route', 'custom/post.ipynb', 'Route is managed by the site'),
    ('cover', 'content/assets/example.png', 'Only course card images'),
])
def test_cms_cannot_change_hidden_post_metadata(tmp_path, field, value, message):
    content = ContentService(author_workspace(tmp_path))
    content.create_post('example', {'title': 'Example'})
    catalog_path = content.root / 'content/data/catalog.yaml'
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
    original = (content.root / 'content/data/catalog.yaml').read_bytes()
    with TestClient(create_app(content.root)) as client:
        saved = client.post('/cms/new?kind=post', data={'revision': content.list()['revision'], 'name': 'example', 'title': 'Example', 'route': 'custom/post.ipynb'})
        assert saved.status_code == 422
        assert 'Route is managed by the site' in saved.text
        assert (content.root / 'content/data/catalog.yaml').read_bytes() == original
