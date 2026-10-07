"""The HTTP/CMS contracts exercise shared services against real saved files."""

import html
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from test_content_service import author_body

from watchtower.api import create_app
from watchtower.api.cms import apply_fields, field_groups, form_fields
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


def lifecycle_options(response):
    select = re.search(r'<select name="field:\["lifecycle"\]">(.*?)</select>', html.unescape(response.text), re.S).group(1)
    return [label for attrs, label in re.findall(r"<option([^>]*)>([^<]*)</option>", select) if "disabled" not in attrs]


def test_cms_lifecycle_choices_follow_authored_content(client):
    assert create_post(client).status_code == 201
    page = client.get("/cms/artifact/post/a%20space")
    assert lifecycle_options(page) == ["planned"]
    revision, snapshot = form_snapshot(page)
    saved = client.post("/cms/save/post/a%20space", data={"revision": revision, "snapshot": snapshot, 'field:["description"]': "Detailed planning metadata"})
    assert saved.status_code == 200, saved.text
    current = client.get("/api/artifacts/post/a%20space")
    assert current.json()["has_authored_content"] is False
    assert client.post("/api/actions/start/post/a%20space", headers={"If-Match": current.headers["etag"]}).status_code == 200
    page = client.get("/cms/artifact/post/a%20space")
    assert lifecycle_options(page) == ["draft", "published"]
    current = client.get("/api/artifacts/post/a%20space")
    assert current.json()["has_authored_content"] is True
    assert current.json()["artifact"]["visibility"] == "private"
    author_body(ContentService(client.app.state.root), "post/a space")
    page = client.get("/cms/artifact/post/a%20space")
    assert lifecycle_options(page) == ["draft", "published"]
    current = client.get("/api/artifacts/post/a%20space")
    assert current.json()["has_authored_content"] is True
    assert client.post("/api/actions/publish/post/a%20space", headers={"If-Match": current.headers["etag"]}).status_code == 200
    assert lifecycle_options(client.get("/cms/artifact/post/a%20space")) == ["draft", "published"]


def test_cms_rejects_authored_post_as_planned_without_changing_files(client):
    assert create_post(client).status_code == 201
    current = client.get("/api/artifacts/post/a%20space")
    assert client.post("/api/actions/start/post/a%20space", headers={"If-Match": current.headers["etag"]}).status_code == 200
    author_body(ContentService(client.app.state.root), "post/a space")
    source = client.app.state.root / "content/notebooks/posts/a space.ipynb"
    catalog = client.app.state.root / "content/data/catalog.yaml"
    original = source.read_bytes(), catalog.read_bytes()
    revision, snapshot = form_snapshot(client.get("/cms/artifact/post/a%20space"))
    response = client.post("/cms/save/post/a%20space", data={"revision": revision, "snapshot": snapshot, 'field:["lifecycle"]': "planned"})
    assert response.status_code == 422, response.text
    assert lifecycle_options(response) == ["draft", "published"]
    assert "planned (requires repair)" in response.text
    assert (source.read_bytes(), catalog.read_bytes()) == original


def test_cms_can_repair_authored_post_with_mismatched_planned_metadata(client):
    assert create_post(client).status_code == 201
    current = client.get("/api/artifacts/post/a%20space")
    assert client.post("/api/actions/start/post/a%20space", headers={"If-Match": current.headers["etag"]}).status_code == 200
    author_body(ContentService(client.app.state.root), "post/a space")
    catalog = client.app.state.root / "content/data/catalog.yaml"
    data = yaml.safe_load(catalog.read_text())
    data["artifacts"][0]["lifecycle"] = "planned"
    catalog.write_text(yaml.safe_dump(data))
    source = client.app.state.root / "content/notebooks/posts/a space.ipynb"
    original = source.read_bytes()
    page = client.get("/cms/artifact/post/a%20space")
    assert lifecycle_options(page) == ["draft", "published"]
    assert "planned (requires repair)" in page.text
    revision, snapshot = form_snapshot(page)
    saved = client.post("/cms/save/post/a%20space", data={"revision": revision, "snapshot": snapshot, 'field:["lifecycle"]': "draft"})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/artifacts/post/a%20space").json()["artifact"]["lifecycle"] == "draft"
    assert source.read_bytes() == original


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
    assert 'id="cms-page-actions"' in response.text
    assert 'hx-swap-oob="outerHTML"' in response.text
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
        assert "Rebuild" in response.text
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
    for key in ("parent", "toc_title", "section"):
        assert f'name="field:["{key}"]"' in html.unescape(page.text)
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
    assert "<h3>A photo heading" in personal.text
    assert 'href="/cms/photos/0/edit"' in personal.text
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
    assert 'name="field:["photos", "0", "width"]"' in html.unescape(page.text)
    assert 'name="new:["photos", "width"]"' in html.unescape(page.text)
    assert 'placeholder="100%"' in page.text
    revision, snapshot = form_snapshot(page)
    published = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "lifecycle"]': "published", 'field:["photos", "0", "width"]': "80%"})
    assert published.status_code == 200, published.text
    assert client.get("/api/gallery").json()["photos"][0]["lifecycle"] == "published"
    assert client.get("/api/gallery").json()["photos"][0]["width"] == "80%"
    assert '<span class="badge">published</span>' in client.get("/cms/personal").text
    page = client.get("/cms/data/photos")
    revision, snapshot = form_snapshot(page)
    invalid = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "width"]': "80"})
    assert invalid.status_code == 422, invalid.text
    assert 'value="80"' in invalid.text
    assert client.get("/api/gallery").json()["photos"][0]["width"] == "80%"
    cleared = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "width"]': ""})
    assert cleared.status_code == 200, cleared.text
    assert client.get("/api/gallery").json()["photos"][0]["width"] is None
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
    assert "color-scheme: light" in response.text
    assert "--wt-background: #f5f5f5" in response.text
    assert "--wt-accent: #222222" in response.text
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
    form = FormData({"collection_action": json.dumps({"path": ["photos"], "action": "add", "prototype": {"heading": "", "path": "", "caption": "", "lifecycle": "draft", "width": ""}}), 'new:["photos", "heading"]': "A new heading", 'new:["photos", "path"]': "content/assets/photo.jpg", 'new:["photos", "caption"]': "An entered caption", 'new:["photos", "lifecycle"]': "draft", 'new:["photos", "width"]': "80%"})
    assert apply_fields({"photos": []}, form)["photos"] == [{"heading": "A new heading", "path": "content/assets/photo.jpg", "caption": "An entered caption", "lifecycle": "draft", "width": "80%"}]


@pytest.mark.parametrize("width", ["0%", "101%", "-10%", "80", "80px", '80%" onload="alert(1)'])
def test_photo_width_rejects_invalid_percentages(width):
    from watchtower.models import Photo

    with pytest.raises(ValueError, match="photo width must be a percentage"):
        Photo(heading="Photo", path="content/assets/photo.jpg", caption="Caption", width=width)


@pytest.mark.parametrize(("width", "expected"), [(None, None), ("", None), ("  ", None), (" 80% ", "80%"), ("0.5%", "0.5%"), ("100%", "100%")])
def test_photo_width_accepts_optional_percentage(width, expected):
    from watchtower.models import Photo

    assert Photo(heading="Photo", path="content/assets/photo.jpg", caption="Caption", width=width).width == expected


def test_editor_groups_keep_nested_fields_with_their_entity():
    data = {"version": 1, "entries": [
        {"id": "portfolio/first", "title": "First", "planned": {"content": "First plan"}},
        {"id": "portfolio/second", "title": "Second", "planned": {"content": "Second plan"}},
    ]}
    groups = field_groups(form_fields(data), data)
    assert [(group["context"], group["title"]) for group in groups] == [
        ("Entries", "1. First"), ("Entries / 1. First", "Planned"),
        ("Entries", "2. Second"), ("Entries / 2. Second", "Planned"),
    ]
    fields = [field for group in groups for field in group["fields"]]
    assert {field["name"] for field in fields} == {field["name"] for field in form_fields(data) if field["label"] != "version"}
    assert groups[0]["row_action"] == {"path": ("entries",), "index": 0, "count": 2}
    assert groups[1]["row_action"] is None
    assert groups[3]["fields"][0]["caption"] == "Content"
    assert groups[3]["fields"][0]["value"] == "Second plan"


def test_editor_cancel_after_failed_save_reloads_saved_values(client):
    page = client.get("/cms/data/profile")
    revision, snapshot = form_snapshot(page)
    service = ContentService(client.app.state.root)
    data = service.read_data("profile")["data"]
    data["summary"] = "Newer saved summary"
    service.update_data("profile", data, expected_revision=revision)
    failed = client.post("/cms/data/profile", headers={"HX-Request": "true"}, data={
        "revision": revision, "snapshot": snapshot, 'field:["summary"]': "Unsaved draft summary",
    })
    assert failed.status_code == 412
    assert 'data-editing="true"' in failed.text
    assert "Unsaved draft summary" in failed.text
    cancel = re.search(r'data-cancel href="([^"]+)"', failed.text).group(1)
    restored = client.get(cancel)
    assert "Newer saved summary" in restored.text
    assert "Unsaved draft summary" not in restored.text
    assert 'href="/cms/resume?edit=profile"' in restored.text
    assert 'data-editor-fields' not in restored.text
    assert service.read_data('profile')['revision'] != revision


def test_native_editor_actions_have_form_and_cancel_destinations(client):
    assert create_post(client).status_code == 201
    create_portfolio(client)
    create_image_course(client)
    create_image_gallery(client)
    client.app.state.content.update_gallery({"version": 1, "photos": [{"heading": "Draft photo", "caption": "Caption", "lifecycle": "draft"}]})
    for route, cancel, form_id in [
        ("/cms/data/profile", "/cms/resume", "profile-editor-form"),
        ("/cms/home?edit=profile", "/cms/home", "profile-editor-form"),
        ("/cms/artifact/post/a%20space", "/cms/posts", "artifact-editor-form"),
        ("/cms/artifact/portfolio/image", "/cms/portfolio", "artifact-editor-form"),
        ("/cms/courses/image", "/cms/courses", "artifact-editor-form"),
        ("/cms/new?kind=post", "/cms/posts", "new-editor-form"),
        ("/cms/new?kind=portfolio", "/cms/portfolio", "new-editor-form"),
        ("/cms/new?kind=course", "/cms/courses", "new-editor-form"),
        ("/cms/new?kind=chapter", "/cms/courses", "new-editor-form"),
        ("/cms/photos/new", "/cms/personal", "photo-add-form"),
        ("/cms/data/photos?add=photo", "/cms/personal", "photo-add-form"),
        ("/cms/photos/0/edit", "/cms/personal", "photo-editor-form"),
    ]:
        page = client.get(route)
        assert page.status_code == 200
        header = re.search(r"<header>(.*?)</header>", page.text, re.S).group(1)
        assert f'data-cancel href="{cancel}"' in header
        assert 'aria-label="Cancel editing"' in header and '<svg' in header
        assert f'type="submit" form="{form_id}" data-save' in header
        assert '>Save</button>' in header
        assert f'<form id="{form_id}" data-editor' in page.text
        assert page.text.count('id="cms-page-actions"') == 1
        assert not re.search(r'class="action-bar(?: |")', page.text)
        # Fields remain usable if JavaScript is unavailable; enhanced viewing
        # mode disables their fieldset only after the script initializes.
        assert 'data-editor-fields disabled' not in page.text


@pytest.mark.parametrize("kind", ["portfolio", "post", "course"])
def test_creation_errors_refresh_header_actions_without_extra_banner(client, kind):
    page = client.get(f"/cms/new?kind={kind}")
    revision = re.search(r'name="revision" value="([^"]+)"', page.text).group(1)
    failed = client.post(f"/cms/new?kind={kind}", headers={"HX-Request": "true"}, data={
        "revision": revision, "name": "", "title": "An unsaved title",
    })
    assert failed.status_code == 422
    assert "An unsaved title" in failed.text
    assert failed.text.count('id="cms-page-actions"') == 1
    assert 'hx-swap-oob="outerHTML"' in failed.text
    assert 'form="new-editor-form" data-save>Save</button>' in failed.text
    assert not re.search(r'class="action-bar(?: |")', failed.text)


def test_photo_header_save_retries_only_the_new_photo(client):
    create_image_gallery(client)
    add_uploaded_photo(client)
    service = client.app.state.content
    existing = service.read_data("photos")["data"]["photos"]
    page = client.get("/cms/photos/new")
    revision = re.search(r'name="revision" value="([^"]+)"', page.text).group(1)
    failed = client.post("/cms/photos/new", headers={"HX-Request": "true"}, data={
        "revision": revision, "heading": "Pending photo", "caption": "Pending caption", "width": "101%",
    })
    assert failed.status_code == 422, failed.text
    assert "Pending photo" in failed.text
    assert "Uploaded photo" not in failed.text
    assert 'hx-swap-oob="outerHTML"' in failed.text
    assert 'form="photo-add-form" data-save>Save</button>' in failed.text
    assert f'name="revision" value="{revision}"' in failed.text
    assert service.read_data("photos")["data"]["photos"] == existing
    saved = client.post("/cms/photos/new", headers={"HX-Request": "true"}, data={
        "revision": revision, "heading": "Pending photo", "caption": "Repaired caption", "width": "80%",
    }, files={"new_photo_image": ("photo.png", portfolio_image_bytes(color="red"), "image/png")})
    assert saved.status_code == 200, saved.text
    assert saved.headers["HX-Redirect"] == "/cms/personal?saved=photo"
    photos = service.read_data("photos")["data"]["photos"]
    assert len(photos) == 2 and photos[:1] == existing
    assert photos[1]["heading"] == "Pending photo" and photos[1]["caption"] == "Repaired caption"
    assert client.get("/cms/photo/0").content == portfolio_image_bytes()
    assert client.get("/cms/photo/1").content == portfolio_image_bytes(color="red")


def test_photo_composer_only_shows_new_fields_and_ignores_existing_row_edits(client):
    create_image_gallery(client)
    add_uploaded_photo(client, heading="Existing photo")
    service = client.app.state.content
    existing = service.read_data("photos")["data"]["photos"]
    page = client.get("/cms/photos/new")
    assert "Existing photo" not in page.text
    assert 'name="snapshot"' not in page.text and 'name="collection_action"' not in page.text
    assert "Adding it also saves the other fields" not in page.text
    controls = re.findall(r'<(?:input|select|textarea)\b[^>]*name="([^"]+)"', page.text)
    assert controls == ["revision", "heading", "new_photo_image", "caption", "lifecycle", "width"]
    assert 'id="add-photo" open' in page.text and 'placeholder="100%"' in page.text
    revision = re.search(r'name="revision" value="([^"]+)"', page.text).group(1)
    payload = {"revision": revision, "heading": "New draft", "caption": "New caption", "snapshot": "{}", 'field:["photos", "0", "caption"]': "Unwanted edit", "path": existing[0]["path"]}
    saved = client.post("/cms/photos/new", data=payload, follow_redirects=False)
    assert saved.status_code == 303 and saved.headers["location"] == "/cms/personal?saved=photo"
    photos = service.read_data("photos")["data"]["photos"]
    assert photos[:1] == existing and len(photos) == 2
    assert photos[1]["path"] == "" and photos[1]["lifecycle"] == "draft"
    duplicate = client.post("/cms/photos/new", data=payload)
    assert duplicate.status_code == 412
    assert "New draft" in duplicate.text and "Existing photo" not in duplicate.text
    assert f'name="revision" value="{revision}"' in duplicate.text
    assert service.read_data("photos")["data"]["photos"] == photos


@pytest.mark.parametrize("payload,upload,status", [
    ({"caption": "Needs a heading"}, None, 422),
    ({"heading": "Needs an image", "caption": "Caption", "lifecycle": "published"}, None, 422),
    ({"heading": "Bad image", "caption": "Caption"}, b"not an image", 422),
    ({"heading": "Missing revision", "caption": "Caption", "revision": ""}, None, 428),
])
def test_photo_composer_errors_preserve_only_new_values(client, payload, upload, status):
    create_image_gallery(client)
    add_uploaded_photo(client, heading="Existing photo")
    service = client.app.state.content
    before = service.read_data("photos")
    files = {"new_photo_image": ("photo.png", upload, "image/png")} if upload else None
    failed = client.post("/cms/photos/new", data={"revision": before["revision"], **payload}, files=files)
    assert failed.status_code == status, failed.text
    assert payload["caption"] in failed.text
    assert "Existing photo" not in failed.text
    assert service.read_data("photos") == before


def test_artifact_action_refreshes_header_publication_controls(client):
    assert create_post(client).status_code == 201
    revision, _ = form_snapshot(client.get("/cms/artifact/post/a%20space"))
    started = client.post("/cms/action/start/post/a%20space", headers={"HX-Request": "true"}, data={"revision": revision})
    assert started.status_code == 200, started.text
    assert 'hx-swap-oob="outerHTML"' in started.text
    assert 'form="artifact-publish-action" data-publication-action' in started.text
    assert 'form="artifact-start-action"' not in started.text
    updated_revision, _ = form_snapshot(started)
    assert updated_revision != revision
    publication_form = re.search(r'<form id="artifact-publish-action".*?</form>', started.text, re.S).group(0)
    assert f'name="revision" value="{updated_revision}"' in publication_form


@pytest.mark.parametrize("kind", ["portfolio", "chapter", "post"])
def test_new_plan_fields_follow_entry_kind(client, kind):
    page = client.get(f"/cms/new?kind={kind}")
    assert page.status_code == 200
    controls = re.findall(r"<(?:input|textarea|select)\b([^>]*)>", page.text)
    enabled = {match.group(1) for attrs in controls if "disabled" not in attrs and (match := re.search(r'name="([^"]+)"', attrs))}
    chapter_fields = {"parent", "toc_title", "section", "planned_lab_and_evidence"}
    portfolio_fields = {"introduction", "what_it_contains", "scope_notes"}
    assert enabled & chapter_fields == (chapter_fields if kind == "chapter" else set())
    assert enabled & portfolio_fields == (portfolio_fields if kind == "portfolio" else set())
    assert ("planned_content" in enabled) == (kind != "portfolio")
    assert "name" in enabled
    assert "id" not in enabled and "path" not in enabled and "filename" not in enabled
    if kind == "post":
        assert '<select name="kind">' not in page.text
    assert {"tags", "relations"} <= enabled


@pytest.mark.parametrize("identifier,path", [
    ("portfolio/demo", None), ("portfolio/wrong", "projects/wrong"),
    ("portfolio/demo", "nb/portfolio/demo.html"), ("portfolio/demo", "content/notebooks/portfolio/demo.ipynb"),
])
def test_cms_portfolio_plan_generates_page_from_name_before_starting_notebook(client, monkeypatch, identifier, path):
    import nbformat

    from watchtower.services.build import BuildService

    page = client.get("/cms/new?kind=portfolio")
    revision = re.search(r'name="revision" value="([^"]+)"', page.text).group(1)
    plan = {"introduction": "A browser interface for the agent.", "what_it_contains": "A durable journal and queryable sessions.", "scope_notes": "The local implementation is the demonstrated path."}
    response = client.post("/cms/new", follow_redirects=False, data={
        "revision": revision, "kind": "portfolio", "name": "Demo", "title": "Demo", "id": identifier,
        **({"path": path} if path is not None else {}), "visibility": "public", **plan,
        # Ignore stale chapter values if the selected kind has changed.
        "parent": "course/stale", "toc_title": "Stale", "section": "stale",
        "planned_content": "Stale generic content", "planned_lab_and_evidence": "Stale lab",
    })
    assert response.status_code == 303, response.text
    root = client.app.state.root
    identifier = "portfolio/demo"
    slug = "demo"
    source = root / f"content/notebooks/portfolio/{slug}.ipynb"
    service = ContentService(root)
    record = service.inspect(identifier)
    assert record["artifact"]["lifecycle"] == "planned"
    assert record["artifact"]["planned"] == {}
    assert record["artifact"]["path"] is None
    assert all(record["artifact"][key] is None for key in ("parent", "toc_title", "section"))
    assert record["detail"]["planned"] == plan
    assert record["detail"]["notebook_path"] == str(source.relative_to(root))
    assert not source.exists()

    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    generated = BuildService(root).generate("production")
    assert not (generated / f"nb/portfolio/{slug}.ipynb").exists()
    assert slug not in (generated / "portfolio.qmd").read_text()
    assert not source.exists()

    # Complete the existing card/source requirements before starting the plan.
    (root / "projects/demo").mkdir(parents=True)
    figure = root / "content/assets/demo.svg"
    figure.parent.mkdir(parents=True)
    figure.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    revision = service.inspect(identifier)["revision"]
    ready = service.update(identifier, {"detail": {
        "abstract": "A browser interface for the agent.", "figure_path": "content/assets/demo.svg",
        "figure_caption": "The session flow.", "project_name": "demo",
    }}, expected_revision=revision)
    assert not source.exists()
    started = service.start(identifier, expected_revision=ready["revision"])
    assert started["artifact"]["lifecycle"] == "draft"
    assert source.exists()
    authored = nbformat.read(source, as_version=4)
    assert authored.cells[0].source == f"# {record['artifact']['title']}\n"
    assert service.inspect(identifier)["detail"]["planned"] == plan


def test_portfolio_editor_omits_chapter_fields_and_preserves_routing_on_save(client):
    service = ContentService(client.app.state.root)
    service.create({
        "id": "portfolio/demo", "kind": "portfolio", "title": "Demo",
        "path": "content/notebooks/portfolio/legacy.ipynb", "route": "nb/portfolio/custom.ipynb",
        "detail": {"notebook_path": "content/notebooks/portfolio/demo.ipynb", "planned": {
            "introduction": "Project introduction", "what_it_contains": "Project contents", "scope_notes": "Project scope",
        }},
    })
    page = client.get("/cms/artifact/portfolio/demo")
    assert page.status_code == 200
    for key in ("parent", "toc_title", "section", "path", "route"):
        assert f'name="field:["{key}"]"' not in html.unescape(page.text)
    for key in ("abstract", "figure_path", "notebook_path", "project_name"):
        assert f'name="field:["detail", "{key}"]"' in html.unescape(page.text)
    revision, snapshot = form_snapshot(page)
    saved = client.post("/cms/save/portfolio/demo", data={
        "revision": revision, "snapshot": snapshot, 'field:["title"]': "Revised project title",
    })
    assert saved.status_code == 200, saved.text
    artifact = service.inspect("portfolio/demo")["artifact"]
    assert artifact["title"] == "Revised project title"
    assert artifact["path"] == "content/notebooks/portfolio/legacy.ipynb"
    assert artifact["route"] == "nb/portfolio/custom.ipynb"
    assert not (client.app.state.root / "content/notebooks/portfolio/demo.ipynb").exists()


def portfolio_image_bytes(format="PNG", color="blue"):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (16, 16), color=color).save(buffer, format=format)
    return buffer.getvalue()


def create_portfolio(client):
    return ContentService(client.app.state.root).create({
        "id": "portfolio/image", "kind": "portfolio", "title": "Image project",
        "detail": {"notebook_path": "content/notebooks/portfolio/image.ipynb", "planned": {
            "introduction": "Introduction", "what_it_contains": "Contents", "scope_notes": "Scope",
        }},
    })


@pytest.mark.parametrize("format,extension", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp"), ("GIF", "gif")])
def test_portfolio_image_upload_saves_caption_and_renders_above_abstract(client, monkeypatch, format, extension):
    import nbformat

    from watchtower.services.build import BuildService

    create_portfolio(client)
    page = client.get("/cms/artifact/portfolio/image")
    assert 'type="file" name="featured_image"' in page.text
    assert 'hx-encoding="multipart/form-data"' in page.text
    revision, snapshot = form_snapshot(page)
    image = portfolio_image_bytes(format)
    saved = client.post("/cms/save/portfolio/image", data={
        "revision": revision, "snapshot": snapshot,
        'field:["detail", "abstract"]': "The project abstract.",
        'field:["detail", "figure_caption"]': "The featured figure caption.",
    }, files={"featured_image": ("../../untrusted.html", image, "application/octet-stream")})
    assert saved.status_code == 200, saved.text
    service = ContentService(client.app.state.root)
    record = service.inspect("portfolio/image")
    detail = record["detail"]
    path = detail["figure_path"]
    assert path.startswith("content/assets/portfolio/image-") and path.endswith(f".{extension}")
    assert (client.app.state.root / path).read_bytes() == image
    assert detail["figure_caption"] == "The featured figure caption."
    assert 'class="featured-figure-preview"' in saved.text
    assert client.get("/cms/figure/portfolio/image").content == image
    assert record["artifact"]["lifecycle"] == "planned"
    assert not (client.app.state.root / detail["notebook_path"]).exists()
    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    ContentService(client.app.state.root).start("portfolio/image")
    generated = BuildService(client.app.state.root).generate("preview")
    listing = (generated / "portfolio.qmd").read_text()
    relative = path.removeprefix("content/")
    assert listing.index(f"![The featured figure caption.]({relative})") < listing.index("The project abstract.")
    assert 'aria-label="Publication status"' in listing
    assert 'callout-caution' not in listing
    assert 'Review content, then publish in CMS' in listing
    generated_page = nbformat.read(generated / "nb/portfolio/image.ipynb", as_version=4)
    assert yaml.safe_load(generated_page.cells[0].source.split("---", 2)[1])["description"] == "The project abstract."
    assert any('aria-label="Publication status"' in cell.source and 'Review content, then publish in CMS' in cell.source for cell in generated_page.cells)
    assert (generated / relative).read_bytes() == image


@pytest.mark.parametrize("failure", ["stale", "invalid", "invalid_metadata", "too_large"])
def test_failed_portfolio_image_upload_writes_no_image_or_metadata(client, failure):
    from watchtower.services.images import MAX_FIGURE_BYTES

    create_portfolio(client)
    service = ContentService(client.app.state.root)
    page = client.get("/cms/artifact/portfolio/image")
    revision, snapshot = form_snapshot(page)
    if failure == "stale":
        service.update("portfolio/image", {"description": "A concurrent edit"}, expected_revision=revision)
    original = service.snapshot().files
    image = b"not an image" if failure == "invalid" else b"x" * (MAX_FIGURE_BYTES + 1) if failure == "too_large" else portfolio_image_bytes()
    response = client.post("/cms/save/portfolio/image", headers={"HX-Request": "true"}, data={
        "revision": revision, "snapshot": snapshot,
        'field:["detail", "abstract"]': "Unsaved abstract",
        'field:["detail", "figure_caption"]': "Unsaved caption",
        **({'field:["visibility"]': "invalid"} if failure == "invalid_metadata" else {}),
    }, files={"featured_image": ("figure.png", image, "image/png")})
    assert response.status_code == (412 if failure == "stale" else 422), response.text
    assert "Unsaved caption" in response.text
    assert "Unsaved abstract" in response.text
    assert "Choose the image again before saving" in response.text
    assert service.snapshot().files == original


def test_portfolio_image_replacement_preserves_previous_asset_and_empty_upload_keeps_figure(client):
    create_portfolio(client)
    service = ContentService(client.app.state.root)
    image = portfolio_image_bytes()
    service.update("portfolio/image", {"detail": {"figure_caption": "Original caption"}}, figure_image=image)
    original_path = service.inspect("portfolio/image")["detail"]["figure_path"]
    revision, snapshot = form_snapshot(client.get("/cms/artifact/portfolio/image"))
    saved = client.post("/cms/save/portfolio/image", data={
        "revision": revision, "snapshot": snapshot, 'field:["detail", "figure_caption"]': "Revised caption",
    }, files={"featured_image": ("", b"", "application/octet-stream")})
    assert saved.status_code == 200, saved.text
    assert service.inspect("portfolio/image")["detail"]["figure_path"] == original_path
    revised_image = portfolio_image_bytes(color="red")
    revision, snapshot = form_snapshot(client.get("/cms/artifact/portfolio/image"))
    replaced = client.post("/cms/save/portfolio/image", data={"revision": revision, "snapshot": snapshot},
        files={"featured_image": ("replacement.png", revised_image, "image/png")})
    assert replaced.status_code == 200, replaced.text
    revised_path = service.inspect("portfolio/image")["detail"]["figure_path"]
    assert revised_path != original_path
    assert (client.app.state.root / original_path).read_bytes() == image
    assert (client.app.state.root / revised_path).read_bytes() == revised_image


def create_image_course(client):
    return ContentService(client.app.state.root).create({
        "id": "course/image", "kind": "course", "title": "Image course",
        "path": "content/notebooks/courses/image", "contract": {
            "purpose": "Learn with images", "audience": "Readers",
            "planned": {"summary": "Course plan", "chapters": []}, "actualized": {}, "toc": [],
        },
    })


def create_image_gallery(client):
    return ContentService(client.app.state.root).create({
        "id": "gallery/photos", "kind": "gallery", "title": "Personal", "path": "content/data/photos.yaml",
    })


def add_uploaded_photo(client, heading="Uploaded photo", format="PNG"):
    revision, snapshot = form_snapshot(client.get("/cms/data/photos"))
    return client.post("/cms/data/photos", data={
        "revision": revision, "snapshot": snapshot,
        "collection_action": json.dumps({"path": ["photos"], "action": "add", "prototype": {
            "heading": "", "path": "", "caption": "", "lifecycle": "draft", "width": "",
        }}),
        'new:["photos", "heading"]': heading,
        'new:["photos", "caption"]': "Photo caption",
        'new:["photos", "width"]': "80%",
    }, files={"new_photo_image": ("../../untrusted.html", portfolio_image_bytes(format), "application/octet-stream")})


@pytest.mark.parametrize("path", [None, "", "   "])
def test_photo_draft_without_image_saves_then_requires_upload_to_publish(client, path):
    from watchtower.services.build import BuildService

    create_image_gallery(client)
    revision, snapshot = form_snapshot(client.get("/cms/data/photos"))
    fields = {
        "revision": revision, "snapshot": snapshot,
        "collection_action": json.dumps({"path": ["photos"], "action": "add", "prototype": {
            "heading": "", "path": "", "caption": "", "lifecycle": "draft", "width": "",
        }}),
        'new:["photos", "heading"]': "Unfinished photo",
        'new:["photos", "caption"]': "A saved draft caption",
    }
    if path is not None:
        fields['new:["photos", "path"]'] = path
    saved = client.post("/cms/data/photos", data=fields)
    assert saved.status_code == 200, saved.text
    service = ContentService(client.app.state.root)
    photo = service.read_data("photos")["data"]["photos"][0]
    assert photo["path"] == "" and photo["lifecycle"] == "draft"
    assert 'aria-label="No Photo"' in saved.text
    personal = client.get("/cms/personal").text
    assert 'aria-label="No Photo"' in personal
    assert 'src="/cms/photo/0"' not in personal
    assert client.get("/cms/photo/0").status_code == 404
    preview = BuildService(client.app.state.root).generate("preview")
    assert not (preview / "personal.qmd").exists()
    assert 'aria-label="No Photo"' in (preview / "gallery.qmd").read_text()
    production = BuildService(client.app.state.root).generate("production")
    assert "Unfinished photo" not in (production / "gallery.qmd").read_text()
    assert "No Photo" not in (production / "gallery.qmd").read_text()
    revision, snapshot = form_snapshot(saved)
    original = service.snapshot().files
    publishing = {"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "lifecycle"]': "published"}
    rejected = client.post("/cms/data/photos", data=publishing)
    assert rejected.status_code == 422
    assert "Published photos need an image" in rejected.text
    assert 'role="alert"' in rejected.text
    assert service.snapshot().files == original
    uploaded = client.post("/cms/data/photos", data=publishing,
                           files={"photo_image:0": ("photo.png", portfolio_image_bytes(), "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    photo = service.read_data("photos")["data"]["photos"][0]
    assert photo["lifecycle"] == "published" and photo["path"]
    assert client.get("/cms/photo/0").content == portfolio_image_bytes()
    production = BuildService(client.app.state.root).generate("production")
    assert "Unfinished photo" in (production / "gallery.qmd").read_text()
    assert 'aria-label="No Photo"' not in (production / "gallery.qmd").read_text()


def test_gallery_api_accepts_draft_with_omitted_path_but_rejects_invalid_paths(client):
    create_image_gallery(client)
    revision = client.get("/api/gallery").headers["etag"]
    photo = {"heading": "Draft stub", "caption": "Draft caption"}
    saved = client.put("/api/gallery", headers={"If-Match": revision}, json={"photos": [photo]})
    assert saved.status_code == 200, saved.text
    revision = client.get("/api/gallery").headers["etag"]
    for path in ("../escape.png", "/absolute.png", "https://example.org/photo.png", "content/assets/missing.png"):
        invalid = client.put("/api/gallery", headers={"If-Match": revision}, json={"photos": [{**photo, "path": path}]})
        assert invalid.status_code == 422
        assert client.get("/api/gallery").headers["etag"] == revision


@pytest.mark.parametrize("format,extension", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp"), ("GIF", "gif")])
def test_course_upload_is_used_by_card_grid(client, monkeypatch, format, extension):
    import nbformat

    from watchtower.services.build import BuildService

    create_image_course(client)
    page = client.get("/cms/artifact/course/image")
    assert 'type="file" name="featured_image"' in page.text
    assert "Card image" in page.text
    revision, snapshot = form_snapshot(page)
    image = portfolio_image_bytes(format)
    saved = client.post("/cms/save/course/image", data={"revision": revision, "snapshot": snapshot},
                        files={"featured_image": ("../../untrusted.html", image, "application/octet-stream")})
    assert saved.status_code == 200, saved.text
    service = ContentService(client.app.state.root)
    cover = service.inspect("course/image")["artifact"]["cover"]
    assert cover.startswith("content/assets/courses/image-") and cover.endswith(f".{extension}")
    assert client.get("/cms/figure/course/image").content == image
    assert 'class="featured-figure-preview"' in saved.text
    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    service.start("course/image")
    author_body(service, "course/image")
    service.publish("course/image")
    generated = BuildService(client.app.state.root).generate("production")
    page = nbformat.read(generated / "nb/courses/image/index.ipynb", as_version=4)
    assert yaml.safe_load(page.cells[0].source.split("---")[1])["image"] == "/" + cover.removeprefix("content/")
    assert (generated / cover.removeprefix("content/")).read_bytes() == image
    listing = yaml.safe_load((generated / "courses.qmd").read_text().split("---")[1])["listing"]
    assert listing["contents"][0]["path"] == "nb/courses/image/index.html"
    assert listing["contents"][0]["image"] == cover.removeprefix("content/")
    # Withdrawing the parent also withdraws its cover from the public build.
    service.update("course/image", {"visibility": "private"})
    generated = BuildService(client.app.state.root).generate("production")
    assert not (generated / cover.removeprefix("content/")).exists()


@pytest.mark.parametrize("format,extension", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp"), ("GIF", "gif")])
def test_new_photo_upload_and_publication(client, monkeypatch, format, extension):
    from watchtower.services.build import BuildService

    create_image_gallery(client)
    page = client.get("/cms/data/photos")
    assert 'type="file" name="new_photo_image"' in page.text
    assert 'hx-encoding="multipart/form-data"' in page.text
    saved = add_uploaded_photo(client, format=format)
    assert saved.status_code == 200, saved.text
    service = ContentService(client.app.state.root)
    photo = service.read_data("photos")["data"]["photos"][0]
    path = photo["path"]
    assert path.startswith("content/assets/photos/Uploaded-photo-") and path.endswith(f".{extension}")
    assert photo["heading"] == "Uploaded photo" and photo["caption"] == "Photo caption"
    assert photo["lifecycle"] == "draft" and photo["width"] == "80%"
    assert 'type="file" name="photo_image:0"' in saved.text
    assert client.get("/cms/photo/0").content == portfolio_image_bytes(format)
    monkeypatch.setattr("watchtower.services.build.build_resume_pdf", lambda stage: None)
    build = BuildService(client.app.state.root)
    production = build.generate("production")
    assert not (production / path.removeprefix("content/")).exists()
    preview = build.generate("preview")
    assert (preview / path.removeprefix("content/")).exists()
    assert "Uploaded photo" in (preview / "gallery.qmd").read_text()
    revision, snapshot = form_snapshot(saved)
    published = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot,
                            'field:["photos", "0", "lifecycle"]': "published"},
                            files={"photo_image:0": ("", b"", "application/octet-stream")})
    assert published.status_code == 200, published.text
    production = build.generate("production")
    assert (production / path.removeprefix("content/")).exists()
    assert "Photo caption" in (production / "gallery.qmd").read_text()


@pytest.mark.parametrize("kind", ["course", "photo"])
@pytest.mark.parametrize("failure", ["stale", "invalid", "too_large", "invalid_metadata", "missing_revision"])
def test_course_and_photo_failed_uploads_are_atomic(client, kind, failure):
    from watchtower.services.images import MAX_FIGURE_BYTES

    service = ContentService(client.app.state.root)
    if kind == "course":
        create_image_course(client)
        editor, target, upload = "/cms/artifact/course/image", "/cms/save/course/image", "featured_image"
        fields = {'field:["description"]': "Unsaved description"}
        invalid = {'field:["visibility"]': "invalid"}
    else:
        create_image_gallery(client)
        assert add_uploaded_photo(client).status_code == 200
        editor = target = "/cms/data/photos"
        upload = "photo_image:0"
        fields = {'field:["photos", "0", "caption"]': "Unsaved description"}
        invalid = {'field:["photos", "0", "width"]': "101%"}
    revision, snapshot = form_snapshot(client.get(editor))
    if failure == "stale":
        if kind == "course":
            service.update("course/image", {"description": "Concurrent edit"})
        else:
            data = service.read_data("photos")["data"]
            data["photos"][0]["caption"] = "Concurrent edit"
            service.update_gallery(data)
    original = service.snapshot().files
    image = b"bad image" if failure == "invalid" else b"x" * (MAX_FIGURE_BYTES + 1) if failure == "too_large" else portfolio_image_bytes(color="red")
    response = client.post(target, headers={"HX-Request": "true"}, data={
        "revision": "" if failure == "missing_revision" else revision, "snapshot": snapshot, **fields,
        **(invalid if failure == "invalid_metadata" else {}),
    }, files={upload: ("image.png", image, "image/png")})
    assert response.status_code == (412 if failure == "stale" else 428 if failure == "missing_revision" else 422), response.text
    assert "Unsaved description" in response.text
    assert "again before saving" in response.text
    assert service.snapshot().files == original


@pytest.mark.parametrize("action,index,uploaded_index,expected_index", [
    ("up", 1, 1, 0), ("down", 0, 0, 1), ("remove", 0, 1, 0), ("remove", 1, 0, 0),
])
def test_photo_replacement_follows_reordered_rows(client, action, index, uploaded_index, expected_index):
    create_image_gallery(client)
    assert add_uploaded_photo(client, "First").status_code == 200
    assert add_uploaded_photo(client, "Second").status_code == 200
    service = ContentService(client.app.state.root)
    old = service.read_data("photos")["data"]["photos"]
    revision, snapshot = form_snapshot(client.get("/cms/data/photos"))
    image = portfolio_image_bytes(color="red")
    saved = client.post("/cms/data/photos", data={
        "revision": revision, "snapshot": snapshot,
        "collection_action": json.dumps({"path": ["photos"], "action": action, "index": index}),
    }, files={f"photo_image:{uploaded_index}": ("replacement.png", image, "image/png")})
    assert saved.status_code == 200, saved.text
    rows = service.read_data("photos")["data"]["photos"]
    assert rows[expected_index]["heading"] == old[uploaded_index]["heading"]
    assert client.get(f"/cms/photo/{expected_index}").content == image
    assert (client.app.state.root / old[uploaded_index]["path"]).exists()


def test_photo_add_and_replacement_save_multiple_images_atomically(client):
    create_image_gallery(client)
    assert add_uploaded_photo(client, "First").status_code == 200
    service = ContentService(client.app.state.root)
    revision, snapshot = form_snapshot(client.get("/cms/data/photos"))
    original = service.snapshot().files
    form = {
        "revision": revision, "snapshot": snapshot,
        "collection_action": json.dumps({"path": ["photos"], "action": "add", "prototype": {
            "heading": "", "path": "", "caption": "", "lifecycle": "draft", "width": "",
        }}),
        'new:["photos", "heading"]': "Second", 'new:["photos", "caption"]': "Second caption",
    }
    replacement = portfolio_image_bytes(color="red")
    files = {"photo_image:0": ("replacement.png", replacement, "image/png"),
             "new_photo_image": ("bad.png", b"not an image", "image/png")}
    failed = client.post("/cms/data/photos", data=form, files=files)
    assert failed.status_code == 422
    assert service.snapshot().files == original
    assert "Second caption" in failed.text
    files["new_photo_image"] = ("new.png", portfolio_image_bytes(), "image/png")
    saved = client.post("/cms/data/photos", data=form, files=files)
    assert saved.status_code == 200, saved.text
    rows = service.read_data("photos")["data"]["photos"]
    assert [row["heading"] for row in rows] == ["First", "Second"]
    assert client.get("/cms/photo/0").content == replacement
    assert client.get("/cms/photo/1").content == portfolio_image_bytes()


def test_course_replacement_and_empty_upload_keep_saved_assets(client):
    create_image_course(client)
    service = ContentService(client.app.state.root)
    original = portfolio_image_bytes()
    service.update("course/image", {}, figure_image=original)
    old_path = service.inspect("course/image")["artifact"]["cover"]
    revision, snapshot = form_snapshot(client.get("/cms/artifact/course/image"))
    empty = client.post("/cms/save/course/image", data={"revision": revision, "snapshot": snapshot},
                        files={"featured_image": ("", b"", "application/octet-stream")})
    assert empty.status_code == 200, empty.text
    assert service.inspect("course/image")["artifact"]["cover"] == old_path
    revision, snapshot = form_snapshot(empty)
    replacement = portfolio_image_bytes(color="red")
    saved = client.post("/cms/save/course/image", data={"revision": revision, "snapshot": snapshot},
                        files={"featured_image": ("replacement.png", replacement, "image/png")})
    assert saved.status_code == 200, saved.text
    assert client.get("/cms/figure/course/image").content == replacement
    assert (client.app.state.root / old_path).read_bytes() == original


def test_posts_title_search_pagination_preserves_filters(client):
    service = ContentService(client.app.state.root)
    for index in range(23):
        service.create({"id": f"post/item-{index}", "kind": "post", "title": f"A very long article title about attention mechanisms and evaluation {index:02}", "path": f"content/notebooks/posts/item-{index}.ipynb", "planned": {"content": "Planned body"}, "tags": ["Models"]})
    second = client.get("/cms/posts", params={"q": "long article title about attention", "tag": "Models", "lifecycle": "planned", "visibility": "private", "page": 2})
    assert second.status_code == 200
    assert "11–20 of 23" in second.text
    assert 'id="post-item-0"' not in second.text and 'id="post-item-10"' in second.text
    next_link = html.unescape(re.search(r'rel="next" href="([^"]+)"', second.text).group(1))
    assert "page=3" in next_link and "tag=Models" in next_link and "visibility=private" in next_link and "q=" in next_link
    last = client.get(next_link)
    assert "21–23 of 23" in last.text
    found = client.get("/cms/posts", params={"q": "VERY LONG ARTICLE TITLE ABOUT ATTENTION MECHANISMS AND EVALUATION 22"})
    assert 'id="post-item-22"' in found.text and 'id="post-item-21"' not in found.text
    assert not re.search(r'<details class="card data-group"[^>]*\bopen\b', found.text)
    assert "No matching entries." in client.get("/cms/posts?q=nonexistent").text


def test_personal_add_photo_and_pagination_keep_source_indices(client):
    service = ContentService(client.app.state.root)
    service.create({"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "content/data/photos.yaml"})
    service.update_gallery({"version": 1, "photos": [{"heading": f"Photo {index}", "caption": "Saved caption", "path": "", "lifecycle": "draft"} for index in range(12)]})
    page = client.get("/cms/personal?page=2")
    assert "11–12 of 12" in page.text and "Photo 10" in page.text and "Photo 0 " not in page.text
    assert 'href="/cms/photos/new"' in page.text
    assert '>Edit photos</a>' not in page.text
    assert 'href="/cms/personal?reorder=1">Reorder photos</a>' in page.text
    editor = client.get("/cms/data/photos?add=photo")
    assert 'id="add-photo" open' in editor.text
    assert 'data-editing="true"' in editor.text
    assert "Photo 0" not in editor.text and "Photo 11" not in editor.text
    editor = client.get("/cms/data/photos")
    revision, snapshot = form_snapshot(editor)
    saved = client.post("/cms/data/photos", data={"revision": revision, "snapshot": snapshot, 'field:["photos", "0", "caption"]': "First edit", 'field:["photos", "11", "caption"]': "Last edit"})
    assert saved.status_code == 200
    photos = service.read_data("photos")["data"]["photos"]
    assert photos[0]["caption"] == "First edit" and photos[11]["caption"] == "Last edit"
