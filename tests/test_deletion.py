"""Artifact deletion retains authored files and repairs managed references atomically."""
import json
import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace
from test_content_service import author_body
from typer.testing import CliRunner

from watchtower.api import create_app
from watchtower.cli import app
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError


@pytest.fixture
def content(tmp_path):
    return ContentService(author_workspace(tmp_path))


def post(content, identifier="post/example"):
    return content.create({"id": identifier, "kind": "post", "title": "Example", "path": f"content/notebooks/posts/{identifier.split('/')[-1]}.ipynb", "planned": {"content": "Authored body."}})


def course(content):
    content.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example", "contract": {"purpose": "Teach", "audience": "Python users", "planned": {"summary": "Course plan", "chapters": []}}})
    for name in ["overview", "chapter"]:
        content.create({"id": f"course/example/{name}", "kind": "chapter", "title": name, "toc_title": name, "path": f"content/notebooks/courses/example/{name}.ipynb", "parent": "course/example", "section": "main", "planned_content": "Topic", "planned_lab_and_evidence": "Check"})
    contract = content.read_data("course/example")["data"]
    contract["overview"] = "course/example/overview"
    content.update_data("course/example", contract)


@pytest.mark.parametrize("lifecycle", ["planned", "draft", "published"])
def test_deletion_archives_exact_source_and_removes_build_entry(content, lifecycle):
    post(content)
    original = None
    if lifecycle != "planned":
        content.start("post/example")
        source = content.root / "content/notebooks/posts/example.ipynb"
        original = source.read_bytes()
    if lifecycle == "published":
        author_body(content, "post/example")
        original = source.read_bytes()
        content.publish("post/example")
    preview = content.deletion_plan("post/example")
    result = content.delete("post/example", preview["revision"])
    assert result["deleted"] == ["post/example"]
    assert content.validate()["valid"]
    assert content.list()["artifacts"] == []
    archive = content.root / result["archive_path"]
    record = json.loads((archive / "record.json").read_text())
    assert record["removed"][0]["lifecycle"] == lifecycle
    if original:
        assert not source.exists()
        assert (archive / "content/notebooks/posts/example.ipynb").read_bytes() == original
    stage = BuildService(content.root).generate(mode="preview")
    assert not (stage / "nb/posts/example.ipynb").exists()
    # Deletion retains permanent ID and source reservations.
    with pytest.raises(ServiceError, match="reserved"):
        post(content)


def test_delete_detaches_links_without_removing_other_records(content):
    post(content)
    post(content, "post/keep")
    content.update("post/keep", {"relations": ["post/example"]})
    task = KanbanService(content.root)
    task.create({"id": "keep-task", "title": "Task", "artifact_ids": ["post/example", "post/keep"]})
    profile = content.read_data("profile")["data"]
    profile["projects"] = [{"title": "Resume entry", "bullets": ["Work"], "artifact_id": "post/example"}]
    content.update_data("profile", profile)
    result = content.delete("post/example")
    assert {link["kind"] for link in result["detached_links"]} == {"relation", "kanban", "profile"}
    assert content.inspect("post/keep")["artifact"]["relations"] == []
    assert task.read()["cards"][0]["artifact_ids"] == ["post/keep"]
    assert content.read_data("profile")["data"]["projects"][0]["artifact_id"] is None
    assert content.validate()["valid"]


def test_chapter_deletion_repairs_plan_toc_and_overview(content):
    course(content)
    content.start("course/example/overview")
    result = content.delete("course/example/overview")
    contract = content.read_data("course/example")["data"]
    assert contract["overview"] is None
    assert contract["toc"][0]["chapters"] == ["course/example/chapter"]
    assert [p["chapter_id"] for p in contract["planned"]["chapters"]] == ["course/example/chapter"]
    assert (content.root / result["archive_path"] / "content/notebooks/courses/example/overview.ipynb").exists()
    assert content.validate()["valid"]


def test_course_deletion_requires_explicit_cascade_and_preserves_contract(content):
    course(content)
    content.start("course/example")
    content.start("course/example/chapter")
    before = content.snapshot()
    with pytest.raises(ServiceError) as error:
        content.delete("course/example")
    assert error.value.code == "has_children"
    assert content.snapshot().revision == before.revision
    result = content.delete("course/example", before.revision, cascade=True)
    assert len(result["deleted"]) == 3
    archive = content.root / result["archive_path"]
    assert not (content.root / "content/data/courses/example.yaml").exists()
    for name in ["content/data/courses/example.yaml", "content/notebooks/courses/example/index.ipynb", "content/notebooks/courses/example/chapter.ipynb"]:
        assert (archive / name).read_bytes() == before.files[name]
        assert not (content.root / name).exists()
    content.validate()
    with pytest.raises(ServiceError, match="reserved"):
        course(content)


def test_portfolio_project_and_images_are_retained(content):
    content.create({"id": "portfolio/example", "kind": "portfolio", "title": "Portfolio", "detail": {"notebook_path": "content/notebooks/portfolio/example.ipynb", "planned": {"introduction": "Intro", "what_it_contains": "Code"}, "project_path": "projects/example"}})
    content.start("portfolio/example")
    project = content.root / "projects/example"
    files = {path.relative_to(project): path.read_bytes() for path in project.rglob('*') if path.is_file()}
    image = content.root / "content/assets/retained.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"retained asset")
    content.delete("portfolio/example")
    assert content.read_data("portfolio")["data"]["entries"] == []
    assert image.read_bytes() == b"retained asset"
    assert content.inspect("project/example")["artifact"]["kind"] == "project"
    content.delete("project/example")
    assert {path.relative_to(project): path.read_bytes() for path in project.rglob('*') if path.is_file()} == files
    content.validate()


def test_stale_and_malformed_deletions_never_write(content):
    revision = post(content)["revision"]
    content.update("post/example", {"description": "Changed"})
    with pytest.raises(ServiceError) as error:
        content.delete("post/example", revision)
    assert error.value.status == 412
    assert not (content.root / "archive/deleted").exists()
    path = content.root / "content/data/kanban.yaml"
    path.write_text("version: 1\ncards: []\ncards: []\n")
    saved = path.read_bytes()
    with pytest.raises(ServiceError):
        content.delete("post/example")
    assert path.read_bytes() == saved
    assert len(content.list()["artifacts"]) == 1


@pytest.mark.parametrize("stage,index", [("prepared", -1), ("installed", 0), ("installed", 1), ("installed", 3), ("recorded", 3)])
def test_delete_crash_recovery_preserves_source(content, stage, index):
    post(content)
    content.start("post/example")
    source = content.root / "content/notebooks/posts/example.ipynb"
    before = source.read_bytes()
    def crash(current_stage, current_index):
        if (current_stage, current_index) == (stage, index):
            raise OSError("Injected crash")
    content.store.fault = crash
    with pytest.raises((OSError, ServiceError)):
        content.delete("post/example")
    recovered = ContentService(content.root)
    first = recovered.snapshot()
    assert first.revision == recovered.snapshot().revision
    if stage == "prepared":
        assert source.read_bytes() == before
        assert len(first.state.artifacts) == 1
    else:
        assert not source.exists()
        assert not first.state.artifacts
        assert next((content.root / "archive/deleted").glob('*/content/notebooks/posts/example.ipynb')).read_bytes() == before


def test_external_source_edit_blocks_delete_recovery(content):
    post(content)
    content.start("post/example")
    source = content.root / "content/notebooks/posts/example.ipynb"
    before = source.read_bytes()
    def crash(stage, index):
        if stage == "installed" and index == 0:
            raise OSError("Injected crash")
    content.store.fault = crash
    with pytest.raises(ServiceError):
        content.delete("post/example")
    source.write_bytes(b"External save")
    with pytest.raises(ServiceError) as error:
        ContentService(content.root).snapshot()
    assert error.value.code == "recovery_conflict"
    assert source.read_bytes() == b"External save"
    assert any(path.read_bytes() == before for path in (content.root / "backend/runtime/transactions").glob('*/preimage-*'))


def test_http_cms_confirmations_and_stale_review(content):
    post(content)
    course(content)
    with TestClient(create_app(content.root)) as client:
        detail = client.get('/cms/artifact/post/example')
        assert 'href="/cms/delete/post/example">Delete</a>' in detail.text
        page = client.get('/cms/delete/post/example')
        token = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        assert client.post('/cms/delete/post/example', data={"revision": token}).status_code == 422
        assert client.delete('/api/artifacts/post/example').status_code == 428
        content.update('post/example', {"description": "Changed"})
        stale = client.post('/cms/delete/post/example', data={"revision": token, "confirm": "post/example", "confirmation_id": "post/example"})
        assert stale.status_code == 412
        assert f'name="revision" value="{token}"' in stale.text
        assert 'Reload deletion review' in stale.text
        token = client.get('/api/deletions/post/example').headers['etag']
        response = client.delete('/api/artifacts/post/example', headers={"If-Match": token})
        assert response.status_code == 200
        assert client.get('/api/artifacts/post/example').status_code == 404
        page = client.get('/cms/delete/course/example')
        assert 'Include all 2 chapters' in page.text
        token = re.search(r'name="revision" value="([^"]+)"', page.text)[1]
        assert client.post('/cms/delete/course/example', data={"revision": token, "confirm": "course/example", "confirmation_id": "course/example"}).status_code == 409
        response = client.post('/cms/delete/course/example', data={"revision": token, "confirm": "course/example", "confirmation_id": "course/example", "cascade": "yes"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == '/cms/courses?deleted=1'


def test_cli_deletion_uses_review_revision(content, monkeypatch):
    monkeypatch.chdir(content.root)
    post(content)
    runner = CliRunner()
    plan = runner.invoke(app, ['delete', 'post/example', '--dry-run'])
    assert plan.exit_code == 0
    preview = json.loads(plan.output)
    assert preview['removed'][0]['id'] == 'post/example'
    result = runner.invoke(app, ['delete', 'post/example', '--expected-revision', preview['revision']])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)['deleted'] == ['post/example']
    post(content, 'post/next')
    result = runner.invoke(app, ['delete', 'post/next'])
    assert result.exit_code == 0
    assert json.loads(result.output)['deleted'] == ['post/next']


def test_gallery_remains_available_while_photos_use_existing_removal(content):
    content.create({"id": "gallery/photos", "kind": "gallery", "title": "Personal", "path": "content/data/photos.yaml"})
    with pytest.raises(ServiceError, match="individual photos"):
        content.delete("gallery/photos")
    assert content.validate()["valid"]
