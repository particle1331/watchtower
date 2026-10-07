"""CMS name-derived post identity and permanent post-name reservations."""
import json
import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace
from test_content_service import author_body

from watchtower.api import create_app
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def service(tmp_path):
    return ContentService(author_workspace(tmp_path))


def test_post_name_form_infers_identity_and_preserves_metadata(service):
    with TestClient(create_app(service.root)) as client:
        page = client.get('/cms/new?kind=post')
        assert 'Create a post plan' in page.text
        assert 'name="name"' in page.text
        assert 'data-generated-id data-kind="post"' in page.text
        assert 'Generated stable ID: <code></code>' in page.text
        assert '>Filename<' not in page.text
        assert 'name="id"' not in page.text
        assert 'name="path"' not in page.text
        assert '<select name="kind">' not in page.text
        token = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        response = client.post('/cms/new?kind=post', data={"revision": token, "name": "GLiNER", "title": "GLiNER article", "planned_content": "Article outline", "tags": "NLP, NER", "description": "Description", "visibility": "private", "kind": "portfolio", "id": "wrong", "path": "wrong"}, follow_redirects=False)
        assert response.status_code == 303, response.text
        assert response.headers['location'] == '/cms/artifact/post/gliner'
    record = service.inspect('post/gliner')['artifact']
    assert record['kind'] == 'post'
    assert record['path'] == 'content/notebooks/posts/gliner.ipynb'
    assert record['title'] == 'GLiNER article'
    assert record['planned']['content'] == 'Article outline'
    assert record['tags'] == ['NLP', 'NER']
    assert record['visibility'] == 'private'
    assert not (service.root / record['path']).exists()
    service.start('post/gliner')
    assert (service.root / record['path']).exists()


@pytest.mark.parametrize('name', ['', '!!!'])
def test_invalid_name_never_writes_and_preserves_submitted_values(service, name):
    with TestClient(create_app(service.root)) as client:
        token = service.list()['revision']
        response = client.post('/cms/new?kind=post', data={"revision": token, "name": name, "title": "Saved title", "planned_content": "Saved outline"})
        assert response.status_code == 422
        assert 'Saved title' in response.text
        assert 'Saved outline' in response.text
        assert 'name="name"' in response.text
        assert service.list()['revision'] == token
        assert service.list()['artifacts'] == []


@pytest.mark.parametrize('lifecycle', ['planned', 'draft', 'published'])
def test_deleted_filename_stays_reserved_without_archive(service, lifecycle):
    service.create_post('gliner', {'title': 'GLiNER', 'planned': {'content': 'Content'}})
    if lifecycle != 'planned':
        service.start('post/gliner')
    if lifecycle == 'published':
        author_body(service, 'post/gliner')
        service.publish('post/gliner')
    result = service.delete('post/gliner')
    # Persistent reservations are independent of the archive record.
    archive = service.root / result['archive_path'] / 'record.json'
    assert json.loads(archive.read_text())['artifact']['id'] == 'post/gliner'
    archive.unlink()
    service = ContentService(service.root)
    for filename in ['gliner', 'GLINER']:
        before = service.list()['revision']
        with pytest.raises(ServiceError, match='reserved'):
            service.create_post(filename, {'title': 'Attempted reuse'})
        assert service.list()['revision'] == before
    catalog = json.loads(json.dumps(service._catalog(service.store.inputs())))
    assert 'post/gliner' in catalog['retired_ids']
    assert 'content/notebooks/posts/gliner.ipynb' in catalog['retired_sources']
    service.validate()


@pytest.mark.parametrize('deleted', [False, True])
def test_legacy_post_id_reserves_same_filename(service, deleted):
    service.create({'id': 'legacy-id', 'kind': 'post', 'title': 'Legacy', 'path': 'content/notebooks/posts/gliner.ipynb'})
    if deleted:
        service.delete('legacy-id')
    with pytest.raises(ServiceError, match='Name'):
        service.create_post('gliner', {'title': 'Collision'})
    assert len(service.list()['artifacts']) == (0 if deleted else 1)


def test_active_id_and_stale_form_fail_without_overwriting(service):
    service.create_post('gliner', {'title': 'First'})
    before = service.list()['revision']
    with pytest.raises(ServiceError, match='already used'):
        service.create_post('GLINER', {'title': 'Second'})
    with TestClient(create_app(service.root)) as client:
        service.update('post/gliner', {'description': 'Changed'})
        response = client.post('/cms/new?kind=post', data={"revision": before, "name": "another", "title": "Unsaved title"})
        assert response.status_code == 412
        assert 'value="another"' in response.text
        assert 'Unsaved title' in response.text
        assert 'post/another' not in {a['id'] for a in service.list()['artifacts']}


def test_deleted_id_cannot_be_recreated_through_generic_api(service):
    service.create_post('gliner', {'title': 'First'})
    service.delete('post/gliner')
    with TestClient(create_app(service.root)) as client:
        token = client.get('/api/artifacts').headers['etag']
        result = client.post('/api/artifacts', headers={'If-Match': token}, json={'id': 'post/gliner', 'kind': 'post', 'title': 'Reused', 'path': 'content/notebooks/posts/elsewhere.ipynb'})
        assert result.status_code == 422
    service.validate()
