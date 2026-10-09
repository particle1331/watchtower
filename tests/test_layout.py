"""Storage relocation preserves authoring, ownership, recovery and public URLs."""
import copy
import shutil

import pytest
from test_content_service import content_service as content_service

from watchtower.services.attachments import AttachmentService, AttachmentUpload
from watchtower.services.build import BuildService
from watchtower.services.content import yaml_bytes
from watchtower.services.kanban import KanbanService
from watchtower.services.layout import LayoutMigration
from watchtower.services.workspace import ServiceError, load_yaml, revision


def legacy_workspace(service):
    for folder in ("data", "assets", "attachments"):
        source = service.root / f"backend/{folder}"
        if source.exists():
            target = service.root / f"content/{folder}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(source, target)
    for name, group, fields in [("catalog", "artifacts", ("path", "cover")), ("portfolio", "entries", ("figure_path",)), ("photos", "photos", ("path",))]:
        path = service.root / f"content/data/{name}.yaml"
        data = load_yaml(path.read_bytes(), str(path))
        for record in data[group]:
            for field in fields:
                if isinstance(record.get(field), str):
                    record[field] = record[field].replace("backend/", "content/", 1)
        path.write_bytes(yaml_bytes(data))
    return LayoutMigration(service.root)


def test_layout_moves_bytes_and_paths_preserving_notes_cards_sources_and_routes(content_service):
    service = content_service
    service.create_post("example", {"title": "Example", "internal_notes": "Old prose mentions content/data/catalog.yaml."})
    service.start("post/example")
    service.create({"id": "course/example", "kind": "course", "title": "Course", "path": "content/notebooks/courses/example"})
    service.create({"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "backend/data/photos.yaml"})
    image = service.root / "backend/assets/photos/a.svg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"<svg/>")
    service.update_gallery({"version": 1, "photos": [{"heading": "A", "path": "backend/assets/photos/a.svg", "caption": "A photo", "lifecycle": "draft"}]})
    attachments = AttachmentService(service.root)
    item = attachments.change("post/example", uploads=[AttachmentUpload("Context.txt", b"Exact context bytes")])["attachments"][0]
    card = KanbanService(service.root).create({"title": "Task", "artifact_ids": ["post/example"]})["card"]
    attachments.change(card["id"], link=item["id"])
    original_notebook = (service.root / "content/notebooks/posts/example.ipynb").read_bytes()
    original_board = (service.root / "backend/data/kanban.yaml").read_bytes()
    original_contract = (service.root / "backend/data/courses/example.yaml").read_bytes()
    migration = legacy_workspace(service)
    before = service.store.inputs()
    preview = migration.run()
    assert not preview["applied"] and preview["ready"]
    assert service.store.inputs() == before
    result = migration.run(apply=True, expected_revision=preview["revision"])
    assert result["applied"] and result["revision"] != preview["revision"]
    assert not any(path.is_file() for folder in ("data", "assets", "attachments") for path in (service.root / f"content/{folder}").rglob("*"))
    assert (service.root / "backend/assets/photos/a.svg").read_bytes() == b"<svg/>"
    assert (service.root / "backend/attachments" / item["id"]).read_bytes() == b"Exact context bytes"
    assert (service.root / "content/notebooks/posts/example.ipynb").read_bytes() == original_notebook
    assert (service.root / "backend/data/kanban.yaml").read_bytes() == original_board
    assert (service.root / "backend/data/courses/example.yaml").read_bytes() == original_contract
    assert service.read_plan("post/example")["internal_notes"].endswith("content/data/catalog.yaml.")
    assert service.inspect("gallery/photos")["artifact"]["path"] == "backend/data/photos.yaml"
    assert service.read_data("photos")["data"]["photos"][0]["path"] == "backend/assets/photos/a.svg"
    assert len(attachments.read("post/example")["attachments"][0]["owners"]) == 2
    assert migration.run(apply=True)["applied"] is False
    service.snapshot()


@pytest.mark.parametrize("failure", ["collision", "stale", "malformed"])
def test_layout_refuses_ambiguous_or_changed_inputs_without_writing(content_service, failure):
    service = content_service
    migration = legacy_workspace(service)
    preview = migration.run()
    if failure == "collision":
        path = service.root / "backend/data/profile.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("unrelated bytes")
    elif failure == "stale":
        (service.root / "content/data/profile.yaml").write_bytes((service.root / "content/data/profile.yaml").read_bytes() + b"\n")
    else:
        (service.root / "content/data/catalog.yaml").write_text("version: 1\nversion: 1\nartifacts: []\n")
    before = service.store.inputs()
    with pytest.raises(ServiceError):
        migration.run(apply=True, expected_revision=preview["revision"] if failure == "stale" else None)
    assert service.store.inputs() == before


def test_layout_rolls_forward_interrupted_moves_and_keeps_notebook_bytes(content_service):
    service = content_service
    service.create_post("example", {"title": "Example"})
    service.start("post/example")
    migration = legacy_workspace(service)
    source = service.root / "content/notebooks/posts/example.ipynb"
    original = source.read_bytes()
    def crash(event, index):
        if event == "installed" and index == 1:
            raise RuntimeError("interrupted move")
    migration.store.fault = crash
    with pytest.raises(ServiceError, match="pending recovery"):
        migration.run(apply=True)
    service.snapshot()
    assert source.read_bytes() == original
    assert not (service.root / "content/data/catalog.yaml").exists()
    assert (service.root / "backend/data/catalog.yaml").is_file()


def test_managed_files_are_dependencies_but_deleted_archives_are_prunable(content_service):
    service = content_service
    files = service.store.inputs()
    before = revision(files)
    signature = BuildService(service.root)._preview_signature()
    path = service.root / "backend/assets/example.svg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"<svg/>")
    assert service.snapshot().revision != before
    assert BuildService(service.root)._preview_signature() != signature
    archived = service.root / "archive/deleted/operation/backend/assets/example.svg"
    archived.parent.mkdir(parents=True)
    archived.write_bytes(b"archived bytes")
    state = copy.deepcopy(service.store.inputs())
    signature = BuildService(service.root)._preview_signature()
    shutil.rmtree(service.root / "archive/deleted")
    assert service.store.inputs() == state
    assert BuildService(service.root)._preview_signature() == signature
    service.snapshot()
