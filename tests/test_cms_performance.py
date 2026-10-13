"""Navigation avoids repeated parsing and validation without hiding saved changes."""

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace, form_snapshot

from watchtower.api import create_app
from watchtower.services import content as content_module
from watchtower.services import workspace as workspace_module
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError, load_yaml


def test_yaml_parsing_reuses_bytes_but_returns_independent_records(monkeypatch):
    parser = workspace_module.YAML
    calls = []

    def counted_parser(*args, **kwargs):
        calls.append(1)
        return parser(*args, **kwargs)

    monkeypatch.setattr(workspace_module, "YAML", counted_parser)
    value = b"version: 1\nitems:\n  - text: Original\n"
    first = load_yaml(value, "cache-isolation.yaml")
    first["items"][0]["text"] = "Changed in memory"
    assert load_yaml(value, "cache-isolation.yaml")["items"][0]["text"] == "Original"
    assert len(calls) == 1
    assert load_yaml(value.replace(b"Original", b"Modified"), "cache-isolation.yaml")["items"][0]["text"] == "Modified"
    with pytest.raises(ServiceError, match="cannot parse YAML"):
        load_yaml(value + b"version: 1\n", "cache-isolation.yaml")


@pytest.fixture
def author(tmp_path):
    content = ContentService(author_workspace(tmp_path))
    for name in ["first", "second", "third"]:
        identifier = f"course/{name}"
        content.create({"id": identifier, "kind": "course", "title": name, "path": f"content/notebooks/courses/{name}"})
        content.start(identifier)
        content.create({"id": identifier + "/chapter", "kind": "chapter", "title": "Chapter", "toc_title": "Chapter", "parent": identifier,
                        "section": "main", "path": f"content/notebooks/courses/{name}/chapter.ipynb"})
    content.start("course/first/chapter")
    return content


def test_course_listing_validates_once_and_preserves_source_controls(author, monkeypatch):
    app = create_app(author.root)
    validate = content_module.validate_state
    inputs = app.state.content.store.inputs
    last_build = app.state.builds.last_successful
    calls = {"validation": 0, "inputs": 0, "build": 0}

    def counted_validation(*args, **kwargs):
        calls["validation"] += 1
        return validate(*args, **kwargs)

    def counted_inputs():
        calls["inputs"] += 1
        return inputs()

    def counted_build(*args, **kwargs):
        calls["build"] += 1
        return last_build(*args, **kwargs)

    monkeypatch.setattr(content_module, "validate_state", counted_validation)
    monkeypatch.setattr(app.state.content.store, "inputs", counted_inputs)
    monkeypatch.setattr(app.state.builds, "last_successful", counted_build)
    with TestClient(app) as client:
        page = client.get("/cms/courses")
    assert page.status_code == 200
    assert calls == {"validation": 1, "inputs": 2, "build": 1}
    assert f'href="vscode://file/{author.root}/content/notebooks/courses/first/chapter.ipynb"' in page.text
    assert 'href="/cms/plan/course/second/chapter"' in page.text


def test_new_post_uses_its_existing_listing(author, monkeypatch):
    app = create_app(author.root)
    inputs = app.state.content.store.inputs
    calls = []

    def counted_inputs():
        calls.append(1)
        return inputs()

    monkeypatch.setattr(app.state.content.store, "inputs", counted_inputs)
    with TestClient(app) as client:
        assert client.get("/cms/new?kind=post").status_code == 200
    assert len(calls) == 1


def test_batch_inspection_matches_individual_records(author):
    identifiers = ["course/first", "course/first/chapter", "course/second/chapter"]
    records = author.inspect_many(identifiers)
    assert len({record["revision"] for record in records.values()}) == 1
    assert records == {identifier: author.inspect(identifier) for identifier in identifiers}


def test_cached_navigation_observes_same_size_external_changes_and_rejects_stale_save(author):
    with TestClient(create_app(author.root)) as client:
        editor = client.get("/cms/artifact/course/first/chapter")
        revision, snapshot = form_snapshot(editor)
        catalog = author.root / "backend/data/catalog.yaml"
        previous = catalog.read_bytes()
        # An unmanaged IDE edit must invalidate reads even when file length is unchanged.
        updated = previous.replace(b"title: Chapter", b"title: Revised", 1)
        assert updated != previous and len(updated) == len(previous)
        catalog.write_bytes(updated)
        record = client.get("/api/artifacts/course/first/chapter").json()
        assert record["artifact"]["title"] == "Revised"
        assert record["revision"] != revision
        assert record["errors"]  # The authored H1 still needs coordinated repair.
        saved = client.post("/cms/save/course/first/chapter", data={"revision": revision, "snapshot": snapshot})
        assert saved.status_code == 412
        assert catalog.read_bytes() == updated
