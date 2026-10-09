"""Visible rows, direct entity editing and Kanban modal fallback behavior."""
import html
import json
import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, portfolio_image_bytes

from watchtower.api import create_app
from watchtower.api.cms import field_groups, form_fields
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService


@pytest.fixture
def author(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    content.create_post('example', {'title': 'Example post', 'description': 'Visible description'})
    content.create({'id': 'gallery/photos', 'kind': 'gallery', 'title': 'Personal', 'path': 'backend/data/photos.yaml'})
    content.update_gallery({'photos': [{'heading': 'First photo', 'caption': 'First caption', 'lifecycle': 'draft'}, {'heading': 'Second photo', 'caption': 'Second caption', 'lifecycle': 'draft'}]})
    return content


def photo_form(page):
    token = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
    snapshot = re.search(r'name="snapshot" value=\'([^\']+)\'', page.text)[1]
    return {'revision': token, 'snapshot': html.unescape(snapshot)}


def field_paths(page):
    paths = []
    for name in re.findall(r'name="([^"]+)"', page.text):
        name = html.unescape(name)
        if name.startswith(("field:", "new:")):
            paths.append(json.loads(name.split(":", 1)[1]))
    return paths


def test_home_illustration_serves_only_its_content_asset(author):
    atlas = author.root / 'backend/assets/atlas.png'
    with TestClient(create_app(author.root)) as client:
        assert client.get('/cms/home/atlas.png').status_code == 404
        payload = portfolio_image_bytes()
        atlas.parent.mkdir(parents=True, exist_ok=True)
        atlas.write_bytes(payload)
        image = client.get('/cms/home/atlas.png')
        assert image.status_code == 200
        assert image.headers['content-type'] == 'image/png'
        assert image.content == payload
        assert 'src="/cms/home/atlas.png"' in client.get('/cms/home').text
        assert 'src="/cms/home/atlas.png"' not in client.get('/cms/resume').text
        assert 'src="/cms/home/atlas.png"' not in client.get('/cms/home?edit=profile').text
        atlas.unlink()
        outside = author.root / 'private.png'
        outside.write_bytes(payload)
        atlas.symlink_to(outside)
        assert client.get('/cms/home/atlas.png').status_code == 404


@pytest.mark.parametrize('section', ['posts', 'portfolio', 'courses'])
def test_list_lifecycle_and_visibility_dropdowns_auto_submit(author, section):
    with TestClient(create_app(author.root)) as client:
        page = client.get(f'/cms/{section}')
        assert page.status_code == 200
        assert page.text.count('name="lifecycle" data-auto-submit') == 1
        assert page.text.count('name="visibility" data-auto-submit') == 1
        assert '<button>Filter</button>' not in page.text
        assert 'name="page_size"' in page.text
        if section == 'posts':
            assert 'name="q"' in page.text


@pytest.mark.parametrize('htmx', [False, True])
def test_portfolio_row_opens_combined_editor_and_save_returns_to_overview(author, htmx):
    (author.root / 'archive/2026-09-30/projects/legacy-example').mkdir(parents=True)
    author.create({'id': 'portfolio/example', 'kind': 'portfolio', 'title': 'Example project', 'detail': {'notebook_path': 'content/notebooks/portfolio/example.ipynb', 'project_path': 'archive/2026-09-30/projects/legacy-example', 'planned': {'introduction': 'The introduction', 'what_it_contains': 'The contents'}}})
    with TestClient(create_app(author.root)) as client:
        overview = client.get('/cms/portfolio')
        assert 'href="/cms/artifact/portfolio/example">Edit</a>' in overview.text
        assert 'href="/cms/data/portfolio"' not in overview.text
        editor = client.get('/cms/artifact/portfolio/example')
        assert 'data-editing="true"' in editor.text
        assert 'data-cancel href="/cms/portfolio"' in editor.text
        assert 'href="/cms/portfolio">← Back to Portfolio</a>' in editor.text
        assert 'href="/cms/data/portfolio"' not in editor.text
        assert 'Project name' not in editor.text and 'Project source' not in editor.text and 'Archive date' not in editor.text
        assert 'Source paths' not in editor.text and 'href="#source"' not in editor.text
        assert ["detail", "notebook_path"] not in field_paths(editor)
        assert not any(path[-1] in {'project_name', 'project_source', 'archive_date'} for path in field_paths(editor))
        for field in ['title', 'detail / abstract', 'detail / figure_path', 'detail / planned / introduction']:
            assert f'title="{field}"' in editor.text
        form = photo_form(editor)
        form.update({'field:["title"]': 'Updated project', 'field:["detail", "abstract"]': 'Updated abstract'})
        saved = client.post('/cms/save/portfolio/example', data=form, headers={'HX-Request': 'true'} if htmx else {}, follow_redirects=False)
        target = '/cms/portfolio?saved=portfolio'
        assert saved.status_code == (200 if htmx else 303)
        assert saved.headers['hx-redirect' if htmx else 'location'] == target
        record = author.inspect('portfolio/example')
        assert record['artifact']['title'] == 'Updated project'
        assert record['detail']['abstract'] == 'Updated abstract'
        assert record['detail']['planned']['introduction'] == 'The introduction'
        assert record['detail']['project_path'] == 'archive/2026-09-30/projects/legacy-example'
        restored = client.get(target)
        assert 'Portfolio entry saved.' in restored.text
        assert 'Updated project' in restored.text and 'Updated abstract' in restored.text


def test_portfolio_conflict_keeps_combined_editor_and_submitted_values(author):
    author.create({'id': 'portfolio/example', 'kind': 'portfolio', 'title': 'Example project', 'detail': {'notebook_path': 'content/notebooks/portfolio/example.ipynb', 'planned': {'introduction': 'The introduction', 'what_it_contains': 'The contents'}}})
    with TestClient(create_app(author.root)) as client:
        form = photo_form(client.get('/cms/artifact/portfolio/example'))
        author.update('portfolio/example', {'title': 'Concurrent title'})
        form.update({'field:["title"]': 'My title', 'field:["detail", "abstract"]': 'My unsaved abstract'})
        failed = client.post('/cms/save/portfolio/example', data=form, headers={'HX-Request': 'true'})
        assert failed.status_code == 412
        assert 'data-editing="true"' in failed.text
        assert 'My title' in failed.text and 'My unsaved abstract' in failed.text
        assert 'data-cancel href="/cms/portfolio"' in failed.text
        assert photo_form(failed)['revision'] == form['revision']
        record = author.inspect('portfolio/example')
        assert record['artifact']['title'] == 'Concurrent title'
        assert record['detail']['abstract'] is None


@pytest.mark.parametrize('htmx', [False, True])
def test_portfolio_save_and_publish_saves_metadata_and_upload_atomically(author, htmx):
    author.create({'id': 'portfolio/example', 'kind': 'portfolio', 'title': 'Example', 'detail': {'planned': {'introduction': 'Project introduction'}}})
    author.start('portfolio/example')
    with TestClient(create_app(author.root)) as client:
        editor = client.get('/cms/artifact/portfolio/example')
        assert 'form="artifact-editor-form" name="save_action" value="publish" data-save data-save-publish>Publish</button>' in editor.text
        assert editor.text.count('>Publish</button>') == 1
        assert 'Save and publish</button>' not in editor.text
        assert 'id="artifact-publish-action"' not in editor.text
        form = photo_form(editor)
        form.update(save_action='publish', **{'field:["title"]': 'Finished project', 'field:["detail", "abstract"]': 'Finished abstract', 'field:["detail", "figure_caption"]': 'Finished figure'})
        saved = client.post('/cms/save/portfolio/example', data=form, files={'featured_image': ('figure.png', portfolio_image_bytes(), 'image/png')}, headers={'HX-Request': 'true'} if htmx else {}, follow_redirects=False)
        assert saved.status_code == (200 if htmx else 303), saved.text
        assert saved.headers['hx-redirect' if htmx else 'location'] == '/cms/portfolio?saved=portfolio'
        record = author.inspect('portfolio/example')
        assert record['artifact']['title'] == 'Finished project'
        assert record['artifact']['lifecycle'] == 'published'
        assert record['artifact']['visibility'] == 'public'
        assert record['detail']['abstract'] == 'Finished abstract'
        assert record['detail']['figure_caption'] == 'Finished figure'
        assert (author.root / record['detail']['figure_path']).is_file()


@pytest.mark.parametrize('failure', ['metadata', 'content', 'stale'])
def test_portfolio_save_and_publish_failure_preserves_draft_and_submitted_values(author, failure):
    author.create({'id': 'portfolio/example', 'kind': 'portfolio', 'title': 'Example', 'detail': {'planned': {} if failure == 'content' else {'introduction': 'Project introduction'}}})
    author.start('portfolio/example')
    with TestClient(create_app(author.root)) as client:
        editor = client.get('/cms/artifact/portfolio/example')
        form = photo_form(editor)
        if failure == 'content':
            assert 'data-save data-save-publish>Publish</button>' in editor.text
            assert 'data-blocked' not in editor.text
            assert 'The notebook has no body content yet.' in editor.text
            assert 'The abstract and featured image do not count as notebook body content.' in editor.text
        if failure == 'stale':
            author.update('portfolio/example', {'title': 'Concurrent title'})
        before = author.inspect('portfolio/example')
        form.update(save_action='publish', **{'field:["title"]': 'Unsaved title', 'field:["detail", "abstract"]': '' if failure == 'metadata' else 'Unsaved abstract', 'field:["detail", "figure_caption"]': 'Unsaved caption'})
        failed = client.post('/cms/save/portfolio/example', data=form, files={'featured_image': ('figure.png', portfolio_image_bytes(), 'image/png')}, headers={'HX-Request': 'true'})
        assert failed.status_code == (412 if failure == 'stale' else 422), failed.text
        assert 'Unsaved title' in failed.text
        if failure == 'content':
            assert 'Cannot publish: the notebook has no body content.' in failed.text
        assert photo_form(failed)['revision'] == form['revision']
        after = author.inspect('portfolio/example')
        assert after['artifact'] == before['artifact']
        assert after['detail'] == before['detail']
        assert after['artifact']['lifecycle'] == 'draft'
        assert not list((author.root / 'backend/assets/portfolio').glob('*.png'))


def test_short_overviews_have_visible_actions_and_thumbnails(author):
    with TestClient(create_app(author.root)) as client:
        home = client.get('/cms/home')
        assert '<h2>Contact</h2>' in home.text
        assert '<summary>Contact' not in home.text
        assert 'mailto:writer@example.com' in home.text
        assert '<summary>Homepage introduction' not in home.text
        posts = client.get('/cms/posts')
        assert 'entity-row-heading' in posts.text
        assert 'Visible description' in posts.text
        assert 'href="/cms/artifact/post/example">Edit</a>' in posts.text
        assert '<summary>' not in posts.text
        personal = client.get('/cms/personal')
        assert 'photo-list-row' in personal.text
        assert 'photo-thumbnail' in personal.text
        assert '<summary>' not in personal.text
        assert 'href="/cms/photos/1/edit"' in personal.text
        assert 'href="/cms/photos/1/delete">Delete</a>' in personal.text
        assert '>Edit photos</a>' not in personal.text
        assert 'href="/cms/personal?reorder=1">Reorder photos</a>' in personal.text
        editor = client.get('/cms/data/profile')
        assert '>General</legend>' in editor.text
        assert '>Contact</legend>' in editor.text
        photo_editor = client.get('/cms/data/photos')
        assert 'data-editing="true"' in photo_editor.text
        assert 'data-begin-edit' not in photo_editor.text
        assert 'data-cancel href="/cms/personal"' in photo_editor.text
        assert 'href="/cms/personal">← Back to Personal</a>' in photo_editor.text
        assert '<details class="entity-group"' not in photo_editor.text
        assert 'placeholder="100%"' in photo_editor.text


def test_resume_editor_entries_fold_regardless_of_length():
    profile = {'name': 'Writer', 'contact': {'email': 'writer@example.com'}, 'employment': [{'title': 'Brief', 'bullets': ['Short']}, {'title': 'Long role', 'bullets': ['Long detail ' * 50]}], 'early_employment': [{'title': 'Early role', 'bullets': []}], 'skills': [{'name': 'Data Analysis', 'entries': ['Short']}], 'education': [{'degree': 'Degree', 'institution': 'School', 'dates': '2020'}]}
    groups = field_groups(form_fields(profile), profile)
    assert [group['fold'] for group in groups] == [False, False, True, True, True, True, True]


def test_resume_overview_entries_start_folded_even_when_short(author):
    profile = author.read_data('profile')['data']
    profile.update(employment=[{'title': 'Engineer', 'company': 'Company', 'dates': '2020', 'bullets': ['Brief']}], early_employment=[{'title': 'Intern', 'company': 'Early company', 'dates': '2019', 'bullets': []}], skills=[{'name': 'Data Analysis', 'entries': ['One skill']}], education=[{'degree': 'Degree', 'institution': 'School', 'dates': '2018'}])
    author.update_data('profile', profile)
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/resume')
        for title in ['Engineer · Company', 'Intern · Early company', 'Data Analysis', 'Degree · School']:
            assert f'<details class="data-record" data-list-item><summary>{title}</summary>' in page.text
        assert '<h2>Contact</h2>' in page.text
        assert '<summary>Contact' not in page.text


@pytest.mark.parametrize('view', ['home', 'resume'])
def test_profile_edit_mode_starts_ready_and_returns_to_origin(author, view):
    with TestClient(create_app(author.root)) as client:
        overview = client.get(f'/cms/{view}')
        assert f'href="/cms/{view}?edit=profile"' in overview.text
        editor = client.get(f'/cms/{view}?edit=profile')
        assert editor.status_code == 200
        assert 'data-editing="true"' in editor.text
        assert 'data-begin-edit' not in editor.text
        assert f'data-cancel href="/cms/{view}"' in editor.text
        header = re.search(r'<header>(.*?)</header>', editor.text, re.S).group(1)
        assert f'data-cancel href="/cms/{view}"' in header
        assert 'aria-label="Cancel editing"' in header
        assert 'form="profile-editor-form" data-save>Save</button>' in header
        assert 'class="action-bar' not in editor.text
        form = photo_form(editor)
        form.update(profile_view=view, **{'field:["summary"]': 'Updated summary'})
        saved = client.post('/cms/data/profile', data=form, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        assert saved.headers['location'] == f'/cms/{view}?saved=profile'
        restored = client.get(saved.headers['location'])
        assert 'Profile saved.' in restored.text and 'Updated summary' in restored.text
        assert 'data-editor-fields' not in restored.text


def test_profile_edit_structure_and_field_order_match_resume(author):
    profile = author.read_data('profile')['data']
    profile.update(employment=[{'bullets': ['Brief'], 'dates': '2020', 'company': 'Company', 'title': 'Engineer'}], early_employment=[{'bullets': [], 'dates': '2019', 'company': 'Early company', 'title': 'Intern'}], skills=[{'entries': ['One skill'], 'name': 'Data Analysis'}], education=[{'dates': '2018', 'institution': 'School', 'degree': 'Degree'}])
    author.update_data('profile', profile)
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/resume?edit=profile')
        headings = [page.text.index(f'<h2>{label}</h2>') for label in ['Contact', 'Employment', 'Early employment', 'Skills', 'Education']]
        assert headings == sorted(headings)
        for owner, fields in [('employment', ['title', 'company', 'dates', 'bullets']), ('skills', ['name', 'entries']), ('education', ['degree', 'institution', 'dates'])]:
            positions = [page.text.index(f'title="{owner} / 0 / {field}"') for field in fields]
            assert positions == sorted(positions)
        assert '<summary>1. Engineer · Company</summary>' in page.text
        assert '<summary>1. Degree · School</summary>' in page.text
        form = photo_form(page)
        profile['summary'] = 'A newer saved summary'
        author.update_data('profile', profile)
        form.update(profile_view='resume', **{'field:["summary"]': 'My unsaved summary'})
        failed = client.post('/cms/data/profile', data=form, headers={'HX-Request': 'true'})
        assert failed.status_code == 412
        assert 'My unsaved summary' in failed.text
        assert 'data-cancel href="/cms/resume"' in failed.text
        assert 'data-editing="true"' in failed.text
        assert author.read_data('profile')['data']['summary'] == 'A newer saved summary'


def test_direct_photo_editor_starts_editing_and_saves_only_selected_photo(author):
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/photos/1/edit')
        assert page.status_code == 200
        assert 'data-editing="true"' in page.text
        assert 'data-begin-edit' not in page.text
        assert 'href="/cms/personal">← Back to Personal</a>' in page.text
        assert 'value="Second photo"' in page.text
        assert 'value="First photo"' not in page.text
        assert 'Remove row' not in page.text
        assert 'placeholder="100%"' in page.text
        form = photo_form(page)
        form.update({'field:["photos", "1", "heading"]': 'Updated second', 'field:["photos", "1", "caption"]': 'Updated caption', 'field:["photos", "0", "caption"]': 'Attempted change to another photo'})
        response = client.post('/cms/photos/1/edit', data=form, follow_redirects=False)
        assert response.status_code == 303, response.text
        assert response.headers['location'] == '/cms/personal?saved=photo'
        photos = author.read_data('photos')['data']['photos']
        assert photos[0]['caption'] == 'First caption'
        assert photos[1]['heading'] == 'Updated second'
        assert photos[1]['caption'] == 'Updated caption'
        for index in [-1, 2]:
            assert client.get(f'/cms/photos/{index}/edit').status_code == 404


def test_photo_editor_conflict_and_invalid_publication_preserve_values(author):
    with TestClient(create_app(author.root)) as client:
        form = photo_form(client.get('/cms/photos/0/edit'))
        data = author.read_data('photos')['data']
        data['photos'][1]['caption'] = 'Concurrent change'
        author.update_gallery(data)
        form['field:["photos", "0", "caption"]'] = 'Unsaved caption'
        stale = client.post('/cms/photos/0/edit', data=form)
        assert stale.status_code == 412
        assert 'Unsaved caption' in stale.text
        assert author.read_data('photos')['data']['photos'][0]['caption'] == 'First caption'
        assert author.read_data('photos')['data']['photos'][1]['caption'] == 'Concurrent change'
        form = photo_form(client.get('/cms/photos/0/edit'))
        form['field:["photos", "0", "lifecycle"]'] = 'published'
        invalid = client.post('/cms/photos/0/edit', data=form)
        assert invalid.status_code == 422
        assert 'Photo was not saved' in invalid.text
        assert author.read_data('photos')['data']['photos'][0]['lifecycle'] == 'draft'


def test_photo_direct_upload_is_atomic_and_isolated(author):
    from io import BytesIO

    from PIL import Image
    buffer = BytesIO()
    Image.new('RGB', (1, 1), 'gray').save(buffer, format='PNG')
    image = buffer.getvalue()
    with TestClient(create_app(author.root)) as client:
        form = photo_form(client.get('/cms/photos/1/edit'))
        response = client.post('/cms/photos/1/edit', data=form, files={'photo_image:1': ('image.png', image, 'image/png')}, follow_redirects=False)
        assert response.status_code == 303, response.text
        photos = author.read_data('photos')['data']['photos']
        assert not photos[0].get('path')
        assert (author.root / photos[1]['path']).read_bytes() == image
        assert client.get('/cms/photo/1').status_code == 200


def test_direct_photo_deletion_removes_selected_entry_and_retains_image(author):
    image = author.root / 'backend/assets/photo.svg'
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    data = author.read_data('photos')['data']
    data['photos'][0].update(path='backend/assets/photo.svg', lifecycle='published')
    author.update_gallery(data)
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/photos/0/delete')
        assert page.status_code == 200
        assert 'First photo' in page.text and 'image file stays in place' in page.text
        revision = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        unconfirmed = client.post('/cms/photos/0/delete', data={'revision': revision})
        assert unconfirmed.status_code == 422
        assert len(author.read_data('photos')['data']['photos']) == 2
        deleted = client.post('/cms/photos/0/delete', data={'revision': revision, 'confirm': 'yes'}, follow_redirects=False)
        assert deleted.status_code == 303
        assert deleted.headers['location'] == '/cms/personal?deleted=1'
        assert author.read_data('photos')['data']['photos'] == [data['photos'][1]]
        assert author.inspect('gallery/photos')['artifact']['lifecycle'] == 'planned'
        assert image.read_text() == '<svg xmlns="http://www.w3.org/2000/svg"/>'
        for index in [-1, 1]:
            assert client.get(f'/cms/photos/{index}/delete').status_code == 404
        revision = author.read_data('photos')['revision']
        last = client.post('/cms/photos/0/delete', data={'revision': revision, 'confirm': 'yes'})
        assert last.status_code == 200 and 'No photos yet' in last.text
        assert author.read_data('photos')['data']['photos'] == []
        assert image.exists()


def test_photo_deletion_rejects_stale_review_after_reordering(author):
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/photos/1/delete')
        revision = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        data = author.read_data('photos')['data']
        data['photos'].reverse()
        author.update_gallery(data)
        stale = client.post('/cms/photos/1/delete', data={'revision': revision, 'confirm': 'yes'})
        assert stale.status_code == 412
        assert 'Reload before deleting' in stale.text
        assert 'name="revision" value="' + revision + '"' in stale.text
        assert '<button class="danger" disabled>' in stale.text
        assert author.read_data('photos')['data'] == data


def test_kanban_edit_links_have_modal_and_native_fallback(author):
    board = KanbanService(author.root)
    board.create({'id': 'task-one', 'title': 'Task one', 'artifact_ids': ['post/example']})
    with TestClient(create_app(author.root)) as client:
        page = client.get('/cms/kanban')
        assert '<details' not in page.text
        assert 'data-dialog-open="edit-task-one"' in page.text
        assert 'href="/cms/kanban?edit=task-one"' in page.text
        assert '<article class="data-record kanban-card"' in page.text
        edit = client.get('/cms/kanban?edit=task-one')
        assert re.search(r'<dialog id="edit-task-one"[^>]*\bopen\b', edit.text)
        assert 'value="Task one"' in edit.text
        assert client.get('/cms/kanban?edit=missing').status_code == 404
        add = client.get('/cms/kanban?add=1')
        assert re.search(r'<dialog id="new-card"[^>]*\bopen\b', add.text)
        saved = client.post('/cms/kanban/update', data={'revision': board.read()['revision'], 'card_id': 'task-one', 'title': 'Updated task', 'column': 'review', 'artifact_ids': 'post/example'}, follow_redirects=False)
        assert saved.status_code == 303
        assert board.read()['cards'][0]['title'] == 'Updated task'
        invalid = client.post('/cms/kanban/update', data={'revision': board.read()['revision'], 'card_id': 'task-one', 'title': 'Unsaved task', 'column': 'review', 'artifact_ids': 'post/missing'})
        assert invalid.status_code == 422
        assert re.search(r'<dialog id="unsaved-card"[^>]*\bopen\b', invalid.text)
        assert 'value="Unsaved task"' in invalid.text
        assert 'data-unsaved' in invalid.text
        assert json.loads(json.dumps(board.read()))['cards'][0]['title'] == 'Updated task'
