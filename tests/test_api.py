"""The HTTP/CMS contracts exercise shared services against real saved files."""

import html
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from watchtower.api import create_app
from watchtower.api.cms import apply_fields, form_fields
from watchtower.services.content import ContentService


def author_workspace(root: Path) -> Path:
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / "frontend", root / "frontend", ignore=shutil.ignore_patterns("generated"), dirs_exist_ok=True)
    documents = {
        "catalog": {"version": 1, "artifacts": []},
        "portfolio": {"version": 1, "entries": []},
        "photos": {"version": 1, "photos": []},
        "settings": {"version": 1, "repository_url": "https://github.com/example/watchtower", "timezone": "Asia/Manila", "source_ref": "main"},
        "profile": {"version": 1, "name": "Writer", "contact": {"phone": "123", "email": "writer@example.com", "github": "https://github.com/example", "linkedin": "https://linkedin.com/in/example"}, "summary": "Saved summary", "homepage_intro": ["Saved introduction"], "employment": [], "early_employment": [], "skills": [], "education": [], "projects": []},
    }
    for name, data in documents.items():
        path = root / "content/data" / f"{name}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return root


@pytest.fixture
def client(tmp_path):
    app = create_app(author_workspace(tmp_path))
    with TestClient(app) as client:
        yield client


def create_post(client, identifier="post/a space"):
    response = client.get("/api/artifacts")
    return client.post("/api/artifacts", headers={"If-Match": response.headers["etag"]}, json={"id": identifier, "kind": "post", "title": "A title", "path": "content/notebooks/posts/a space.ipynb", "planned": {"content": "A persisted article plan"}})


def form_snapshot(response):
    revision = re.search(r'name="revision" value="([^"]+)"', response.text).group(1)
    source = re.search(r'name="snapshot" value=\'([^\']+)\'', response.text).group(1)
    return revision, html.unescape(source)


def test_required_precondition_stale_save_and_two_clients(client):
    missing = client.post("/api/artifacts", json={"id": "post/test", "kind": "post", "title": "Test", "path": "content/notebooks/posts/test.ipynb"})
    assert missing.status_code == 428
    created = create_post(client)
    assert created.status_code == 201, created.text
    current = client.get("/api/artifacts/post/a%20space")
    etag = current.headers["etag"]
    saved = client.patch("/api/artifacts/post/a%20space", headers={"If-Match": etag}, json={"description": "First client's edit"})
    assert saved.status_code == 200, saved.text
    stale = client.patch("/api/artifacts/post/a%20space", headers={"If-Match": etag}, json={"tags": ["stale"]})
    assert stale.status_code == 412, stale.text
    assert client.get("/api/artifacts/post/a%20space").json()["artifact"]["description"] == "First client's edit"


def test_start_editor_link_and_conflict_preserves_form_values(client):
    assert create_post(client).status_code == 201
    page = client.get("/cms/artifact/post/a%20space")
    assert "Edit in VS Code" not in page.text
    revision, snapshot = form_snapshot(page)
    newer = client.patch("/api/artifacts/post/a%20space", headers={"If-Match": revision}, json={"description": "A concurrent edit"})
    assert newer.status_code == 200
    response = client.post("/cms/save/post/a%20space", headers={"HX-Request": "true"}, data={"revision": revision, "snapshot": snapshot, 'field:["title"]': "My unsaved <title>"})
    assert response.status_code == 412, response.text
    assert "My unsaved &lt;title&gt;" in response.text
    assert "Reload saved values" in response.text
    current = client.get("/api/artifacts/post/a%20space")
    started = client.post("/api/actions/start/post/a%20space", headers={"If-Match": current.headers["etag"]})
    assert started.status_code == 200, started.text
    page = client.get("/cms/artifact/post/a%20space")
    assert "a%20space.ipynb" in page.text
    assert "vscode://file/" in page.text
    assert "content/notebooks/posts/a space.ipynb" in page.text
    assert "frontend/generated" not in page.text
    assert str(client.app.state.root) in page.text


def test_native_metadata_form_roundtrip_preserves_nullable_fields(client):
    assert create_post(client).status_code == 201
    page = client.get("/cms/artifact/post/a%20space")
    revision, snapshot = form_snapshot(page)
    payload = {"revision": revision, "snapshot": snapshot}
    for field in form_fields(json.loads(snapshot)):
        if field["label"] not in {"id", "kind", "version"}:
            payload["field:" + field["name"]] = str(field["value"])
    response = client.post("/cms/save/post/a%20space", data=payload)
    assert response.status_code == 200, response.text
    artifact = client.get("/api/artifacts/post/a%20space").json()["artifact"]
    assert artifact["cover"] is None
    assert artifact["parent"] is None


def test_structured_profile_conflict_preserves_submitted_values(client):
    page = client.get("/cms/data/profile")
    revision, snapshot = form_snapshot(page)
    service = ContentService(client.app.state.root)
    data = service.read_data("profile")["data"]
    data["summary"] = "Changed manually"
    service.update_data("profile", data, expected_revision=revision)
    response = client.post("/cms/data/profile", data={"revision": revision, "snapshot": snapshot, 'field:["contact", "phone"]': "+63 unsaved number"})
    assert response.status_code == 412, response.text
    assert "+63 unsaved number" in response.text
    assert service.read_data("profile")["data"]["contact"]["phone"] == "123"


def test_native_pages_schema_and_local_origin(client):
    for section in ["home", "resume", "portfolio", "posts", "courses", "personal"]:
        response = client.get(f"/cms/{section}")
        assert response.status_code == 200, response.text
        assert "Refresh site preview" in response.text
        assert "/cms/static/theme.css" in response.text
    assert client.get("/cms/static/theme.css").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["components"]["schemas"]["ArtifactCreate"]["properties"]["planned"]
    assert client.post("/api/validate", headers={"Origin": "https://foreign.example"}).status_code == 403
    assert client.get("/api/artifacts", headers={"Host": "foreign.example"}).status_code == 400


def test_inline_chapter_plan_and_nested_ids_are_derived(client):
    revision = client.get("/api/artifacts").headers["etag"]
    course = client.post("/api/artifacts", headers={"If-Match": revision}, json={"id": "course/demo", "kind": "course", "title": "Demo", "path": "content/notebooks/courses/demo", "contract": {"purpose": "Understand", "audience": "Readers", "planned": {"summary": "Course plan", "chapters": []}, "actualized": {"summary": ""}, "toc": [{"id": "main", "title": "Foundations", "chapters": []}]}})
    assert course.status_code == 201, course.text
    revision = course.headers["etag"]
    chapter = client.post("/api/artifacts", headers={"If-Match": revision}, json={"id": "course/demo/first", "kind": "chapter", "title": "First Chapter", "path": "content/notebooks/courses/demo/first.ipynb", "parent": "course/demo", "toc_title": "First", "section": "main", "planned_content": "Explain a concept", "planned_lab_and_evidence": "Run a lab"})
    assert chapter.status_code == 201, chapter.text
    page = client.get("/cms/artifact/course/demo/first")
    revision, snapshot = form_snapshot(page)
    assert "Explain a concept" in page.text
    saved = client.post("/cms/save/course/demo/first", data={"revision": revision, "snapshot": snapshot, 'field:["plan", "content"]': "A revised teaching plan"})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/artifacts/course/demo/first").json()["chapter_plan"]["content"] == "A revised teaching plan"
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert "id" not in schema["CourseInput"]["required"]
    assert "id" not in schema["PortfolioInput"].get("required", [])


def test_gallery_photo_lifecycle_api_and_cms(client):
    revision = client.get("/api/artifacts").headers["etag"]
    created = client.post("/api/artifacts", headers={"If-Match": revision}, json={"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "content/data/photos.yaml"})
    assert created.status_code == 201, created.text
    root = client.app.state.root
    image = root / "content/assets/photo.svg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    revision = client.get("/api/data/photos").headers["etag"]
    missing = client.put("/api/gallery", json={"photos": []})
    assert missing.status_code == 428
    saved = client.put("/api/gallery", headers={"If-Match": revision}, json={"photos": [{"heading": "A photo heading", "path": "content/assets/photo.svg", "caption": "A caption", "lifecycle": "draft"}]})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/gallery").json()["photos"][0]["lifecycle"] == "draft"
    assert "lifecycle" not in client.get("/api/gallery").json()
    personal = client.get("/cms/personal")
    assert "/cms/photo/0" in personal.text
    assert "A caption" in personal.text
    assert "<h2>A photo heading</h2>" in personal.text
    assert '<span class="badge">draft</span>' in personal.text
    assert "Create personal plan" not in personal.text
    assert client.get("/cms/photo/0").status_code == 200
    assert client.get("/cms/photo/-1").status_code == 404
    assert client.get("/cms/photo/99").status_code == 404
    page = client.get("/cms/data/photos")
    assert "Gallery lifecycle" not in page.text
    assert "gallery_lifecycle" not in page.text
    assert "photos / 0 / heading" in page.text
    assert 'name="field:["photos", "0", "lifecycle"]"' in html.unescape(page.text)
    revision, snapshot = form_snapshot(page)
    published = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "lifecycle"]': "published"})
    assert published.status_code == 200, published.text
    assert client.get("/api/gallery").json()["photos"][0]["lifecycle"] == "published"
    assert '<span class="badge">published</span>' in client.get("/cms/personal").text
    page = client.get("/cms/data/photos")
    revision, snapshot = form_snapshot(page)
    response = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot, "collection_action": json.dumps({"path": ["photos"], "index": 0, "action": "remove"})})
    assert response.status_code == 200, response.text
    assert client.get("/api/data/photos").json()["data"]["photos"] == []
    assert client.get("/api/artifacts/gallery/photos").json()["artifact"]["lifecycle"] == "planned"
    assert "No photos yet" in client.get("/cms/personal").text


def test_gallery_required_heading_draft_default_and_conflict_preserves_row(client):
    revision = client.get("/api/artifacts").headers["etag"]
    gallery = client.post("/api/artifacts", headers={"If-Match": revision}, json={"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "content/data/photos.yaml"})
    assert gallery.status_code == 201
    root = client.app.state.root
    image = root / "content/assets/photo.svg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    revision = client.get("/api/gallery").headers["etag"]
    row = {"path": "content/assets/photo.svg", "caption": "A caption"}
    invalid = client.put("/api/gallery", headers={"If-Match": revision}, json={"photos": [row]})
    assert invalid.status_code == 422
    saved = client.put("/api/gallery", headers={"If-Match": revision}, json={"photos": [{**row, "heading": "A draft photo"}]})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/gallery").json()["photos"][0]["lifecycle"] == "draft"
    page = client.get("/cms/data/photos")
    revision, snapshot = form_snapshot(page)
    newer = client.put("/api/gallery", headers={"If-Match": revision}, json={"photos": [{**row, "heading": "Saved photo", "lifecycle": "published"}]})
    assert newer.status_code == 200
    failed = client.post("/cms/data/photos", headers={"HX-Request": "true"}, data={"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "heading"]': "My unsaved heading", 'field:["photos", "0", "lifecycle"]': "draft"})
    assert failed.status_code == 412
    assert "My unsaved heading" in failed.text
    assert "Gallery lifecycle" not in failed.text
    assert client.get("/api/gallery").json()["photos"][0]["heading"] == "Saved photo"


def test_personal_surface_omits_prose_and_photo_path_escape(client):
    revision = client.get("/api/artifacts").headers["etag"]
    created = client.post("/api/artifacts", headers={"If-Match": revision}, json={"id": "personal/notes", "kind": "personal", "title": "Private prose card", "path": "content/notebooks/personal/notes.ipynb", "planned": {"content": "Prose"}})
    assert created.status_code == 201, created.text
    personal = client.get("/cms/personal")
    assert "Private prose card" not in personal.text
    assert "Create personal plan" not in personal.text
    root = client.app.state.root
    secret = root / "outside.txt"
    secret.write_text("private file")
    (root / "content/data/photos.yaml").write_text(yaml.safe_dump({"version": 1, "photos": [{"heading": "Escape", "path": "../outside.txt", "caption": "Escape"}]}))
    assert client.get("/cms/photo/0").status_code == 404


def test_build_status_and_validated_log_ids(client, monkeypatch):
    record = {"id": "a" * 32, "status": "queued", "revision": "build-revision"}
    monkeypatch.setattr(client.app.state.builds, "submit", lambda mode: record)
    response = client.post("/api/builds", json={"mode": "preview"})
    assert response.status_code == 202
    assert response.json()["id"] == "a" * 32
    fragment = client.post("/cms/refresh", headers={"HX-Request": "true"})
    assert 'hx-trigger="every 1s"' in fragment.text
    native = client.post("/cms/refresh")
    assert native.text.count('id="build-status"') == 1
    successful = {**record, "status": "succeeded", "finished_at": "2026-10-01", "preview_url": "http://127.0.0.1:4321"}
    monkeypatch.setattr(client.app.state.builds, "last_successful", lambda mode: successful)
    page = client.get("/cms/data/profile")
    assert 'href="http://127.0.0.1:4321"' in page.text
    assert "Last successful refresh" in page.text
    assert client.get("/api/builds/invalid/logs").status_code == 400
    assert client.get("/api/builds/" + "f" * 32).status_code == 404


def test_author_palette_is_scoped_to_cms_static(client):
    response = client.get("/cms/static/theme.css")
    assert response.status_code == 200
    assert "--wt-background: #111015" in response.text
    assert "--wt-accent: #bd9bff" in response.text
    assert client.get("/cms/assets/theme.css").status_code == 404
    assert not (client.app.state.root / "frontend/assets/theme.css").exists()


def test_list_reorder_and_add_preserve_fields():
    from starlette.datastructures import FormData

    original = {"toc": [{"id": "a", "title": "A", "chapters": ["chapter/a"]}, {"id": "b", "title": "B", "chapters": []}]}
    form = FormData({"collection_action": json.dumps({"path": ["toc"], "action": "down", "index": 0}), 'field:["toc", "0", "title"]': "Edited A"})
    result = apply_fields(original, form)
    assert [row["id"] for row in result["toc"]] == ["b", "a"]
    assert result["toc"][1]["title"] == "Edited A"
    assert original["toc"][0]["title"] == "A"
    form = FormData({"collection_action": json.dumps({"path": ["photos"], "action": "add", "prototype": {"heading": "", "path": "", "caption": "", "lifecycle": "draft"}}), 'new:["photos", "heading"]': "A new heading", 'new:["photos", "path"]': "content/assets/photo.jpg", 'new:["photos", "caption"]': "An entered caption", 'new:["photos", "lifecycle"]': "draft"})
    assert apply_fields({"photos": []}, form)["photos"] == [{"heading": "A new heading", "path": "content/assets/photo.jpg", "caption": "An entered caption", "lifecycle": "draft"}]
