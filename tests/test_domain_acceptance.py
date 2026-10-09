"""Cross-entity acceptance and validation of manually edited saved inputs."""


import nbformat
import pytest
import yaml
from test_content_service import author_body, post
from test_content_service import content_service as content_service

from watchtower.models import PortfolioEntry, eligible
from watchtower.services.content import ContentService, yaml_bytes
from watchtower.services.workspace import ServiceError


def course(service, slug="example", published=False):
    key = f"course/{slug}"
    service.create({"id": key, "kind": "course", "title": f"{slug} course", "path": f"content/notebooks/courses/{slug}", "contract": {"purpose": "Teach", "audience": "Learners"}})
    if published:
        service.start(key)
        author_body(service, key)
        service.publish(key)
    return key


def chapter(service, slug="example", name="01", start=False):
    key = f"course/{slug}/{name}"
    service.create({"id": key, "kind": "chapter", "title": "Chapter Title", "toc_title": name, "section": "main", "parent": f"course/{slug}", "path": f"content/notebooks/courses/{slug}/{name}.ipynb", "planned_content": "Teach the topic", "planned_lab_and_evidence": "Check a reproducible example"})
    if start:
        service.start(key)
    return key


def portfolio_payload(service, name="example"):
    project = service.root / "projects" / name
    project.mkdir(parents=True)
    (project / "code.py").write_text("# Authored executable project code\n")
    figure = service.root / f"backend/assets/portfolio/{name}.svg"
    figure.parent.mkdir(parents=True, exist_ok=True)
    figure.write_text("<svg><title>Authored diagram</title></svg>")
    return {"id": f"portfolio/{name}", "kind": "portfolio", "title": "Portfolio example", "detail": {"abstract": "A project for a concrete problem.", "figure_path": f"backend/assets/portfolio/{name}.svg", "figure_caption": "The intended architecture.", "notebook_path": f"content/notebooks/portfolio/{name}.ipynb", "project_path": f"projects/{name}", "planned": {"introduction": "Investigate the concrete problem.", "what_it_contains": "A reproducible implementation and checks.", "success_criteria": "Each check passes."}}}


def file_state(service):
    return service.store.inputs()


def test_portfolio_complete_workflow_keeps_project_code_and_notebook_bytes(content_service):
    service = content_service
    payload = portfolio_payload(service)
    code = service.root / "projects/example/code.py"
    code_before = code.read_bytes()
    service.create(payload)
    source = service.root / payload["detail"]["notebook_path"]
    assert not source.exists()
    service.start(payload["id"])
    nb = nbformat.read(source, as_version=4)
    text = "\n".join(cell.source for cell in nb.cells)
    assert "Investigate the concrete problem." in text
    assert "A reproducible implementation and checks." in text
    assert "Each check passes." in text
    assert "## Success criteria\n\nEach check passes." in service.inspect(payload["id"])["build_brief"]
    nb.cells.append(nbformat.v4.new_code_cell("#| code-fold: true\nprint(1)", execution_count=3, outputs=[nbformat.v4.new_output("stream", name="stdout", text="1\n")]))
    nbformat.write(nb, source)
    body = source.read_bytes()
    service.publish(payload["id"])
    assert service.inspect(payload["id"])["eligible"]
    service.draft(payload["id"])
    assert not service.inspect(payload["id"])["eligible"]
    assert source.read_bytes() == body
    assert code.read_bytes() == code_before
    assert service.inspect(payload["id"])["detail"]["planned"] == payload["detail"]["planned"]


@pytest.mark.parametrize("missing", ["abstract", "figure_path", "figure_caption"])
def test_portfolio_publish_missing_required_detail_is_atomic(content_service, missing):
    service = content_service
    payload = portfolio_payload(service)
    payload["detail"].pop(missing)
    service.create(payload)
    service.start(payload["id"])
    author_body(service, payload["id"])
    service.update(payload["id"], {"detail": {missing: None}})
    before = file_state(service)
    with pytest.raises(ServiceError):
        service.publish(payload["id"])
    assert file_state(service) == before
    assert (service.root / "content/notebooks/portfolio/example.ipynb").exists()
    assert (service.root / "projects/example/code.py").exists()


@pytest.mark.parametrize("missing", ["introduction", "what_it_contains"])
def test_portfolio_start_accepts_partial_plan(content_service, missing):
    service = content_service
    payload = portfolio_payload(service)
    payload["detail"]["planned"].pop(missing)
    service.create(payload)
    service.start(payload["id"])
    record = service.inspect(payload["id"])
    assert record["artifact"]["lifecycle"] == "draft"
    assert record["has_authored_content"]


@pytest.mark.parametrize("project_path", [
    "bare-name",
    "projects/nested/example",
    "projects/../outside",
    "projects/./example",
    "archive/2026-09-30/code/example",
    "archive/2026-02-30/projects/example",
])
def test_invalid_portfolio_path_never_writes(content_service, project_path):
    service = content_service
    payload = portfolio_payload(service)
    payload["detail"]["project_path"] = project_path
    before = file_state(service)
    with pytest.raises(ServiceError, match="project_path"):
        service.create(payload)
    assert file_state(service) == before


def test_legacy_portfolio_project_fields_load_and_dump_as_project_path():
    archived = PortfolioEntry.model_validate({
        "id": "portfolio/historical", "project_name": "historical",
        "project_source": "archived", "archive_date": "2026-09-30",
    })
    active = PortfolioEntry.model_validate({"id": "portfolio/current", "project_name": "current"})
    empty = PortfolioEntry.model_validate({"id": "portfolio/unresolved", "project_name": ""})

    assert archived.project_path == "archive/2026-09-30/projects/historical"
    assert active.project_path == "projects/current"
    assert empty.project_path is None
    dumped = archived.model_dump(mode="json")
    assert dumped["project_path"] == "archive/2026-09-30/projects/historical"
    assert not {"project_name", "project_source", "archive_date"}.intersection(dumped)


def test_portfolio_escaping_project_symlink_is_rejected(content_service):
    service = content_service
    payload = portfolio_payload(service)
    external = service.root / "other-root"
    external.mkdir()
    (service.root / "projects/escape").symlink_to(external, target_is_directory=True)
    payload["detail"]["project_path"] = "projects/escape"
    before = file_state(service)
    with pytest.raises(ServiceError, match="symlink escapes"):
        service.create(payload)
    assert file_state(service) == before


def test_portfolio_project_relation_must_identify_same_directory(content_service):
    service = content_service
    payload = portfolio_payload(service)
    (service.root / "projects/other").mkdir()
    service.create({"id": "project/other", "kind": "project", "title": "Other", "path": "projects/other"})
    payload["relations"] = ["project/other"]
    before = file_state(service)
    with pytest.raises(ServiceError, match="different code directory"):
        service.create(payload)
    assert file_state(service) == before


@pytest.mark.parametrize("project_path", [None, "projects/future-code"])
def test_planned_portfolio_related_content_includes_reserved_source_before_code_exists(content_service, project_path):
    service = content_service
    related_id = course(service, "related", published=True)
    private_id = post(service, visibility="private")["artifact"]["id"]
    detail = {
        "notebook_path": "content/notebooks/portfolio/future.ipynb",
        "planned": {"introduction": "Introduction", "what_it_contains": "Contents",
                    "references": "[Prior work](https://example.org/prior)"},
    }
    if project_path is not None:
        detail["project_path"] = project_path
    service.create({"id": "portfolio/future", "kind": "portfolio", "title": "Future project",
        "relations": [related_id, private_id], "detail": detail})
    record = service.inspect("portfolio/future")
    source_name = project_path.rsplit("/", 1)[-1] if project_path else "future"
    assert f"## References and related content\n\n[Prior work](https://example.org/prior)\n\n- [Reserved source code](https://github.com/particle1331/watchtower/tree/main/projects/{source_name})\n- [related course]" in record["plan"]
    assert "[Example]" not in record["plan"]
    assert "nb/posts/example" not in record["plan"]
    assert "## Problem\n\nIntroduction\n\n## What it contains\n\nContents\n\n## References and related content" in record["plan"]
    assert "## References\n" not in record["plan"]
    assert "## Explore the project" not in record["plan"]
    assert not (service.root / f"projects/{source_name}").exists()
    assert not (service.root / "content/notebooks/portfolio/future.ipynb").exists()
    service.validate()


def test_planned_archived_source_still_requires_existing_archive_directory(content_service):
    service = content_service
    original = file_state(service)
    with pytest.raises(ServiceError, match="missing project directory"):
        service.create({"id": "portfolio/missing", "kind": "portfolio", "title": "Missing archived source",
            "detail": {"project_path": "archive/2026-09-30/projects/missing"}})
    assert file_state(service) == original


@pytest.mark.parametrize("references", ["", "- First reference\n- Second reference"])
def test_portfolio_preview_merges_references_with_related_content(content_service, references):
    service = content_service
    service.create({"id": "portfolio/resources", "kind": "portfolio", "title": "Resources",
        "detail": {"planned": {"introduction": "Introduction", "what_it_contains": "Contents", "references": references}}})
    body = service.inspect("portfolio/resources")["plan"]
    assert "## References\n" not in body
    assert body.count("## References and related content") == 1
    assert "- [Reserved source code]" in body
    if references:
        assert "- First reference\n- Second reference\n\n- [Reserved source code]" in body


def test_photo_lifecycle_updates_gallery_automatically_and_preserves_images(content_service):
    service = content_service
    service.create({"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "backend/data/photos.yaml"})
    with pytest.raises(ServiceError):
        service.publish("gallery/photos")
    picture = service.root / "backend/assets/photos/one.svg"
    picture.parent.mkdir(parents=True)
    picture.write_text("<svg><title>Photo</title></svg>")
    before_image = picture.read_bytes()
    photo = {"heading": "One afternoon", "path": "backend/assets/photos/one.svg", "caption": "A reviewed caption", "lifecycle": "draft"}
    service.update_gallery({"version": 1, "photos": [photo]})
    assert service.inspect("gallery/photos")["artifact"]["lifecycle"] == "planned"
    photo["lifecycle"] = "published"
    service.update_data("photos", {"version": 1, "photos": [photo]})
    assert service.inspect("gallery/photos")["artifact"]["lifecycle"] == "published"
    photo["lifecycle"] = "draft"
    service.update_gallery({"version": 1, "photos": [photo]})
    assert service.inspect("gallery/photos")["artifact"]["lifecycle"] == "planned"
    assert picture.read_bytes() == before_image
    assert service.read_data("photos")["data"]["photos"][0]["heading"] == "One afternoon"
    assert service.inspect("gallery/photos")["editor_url"] is None
    photo["lifecycle"] = "published"
    (service.root / "backend/data/photos.yaml").write_bytes(yaml_bytes({"version": 1, "photos": [photo]}))
    service.validate()
    assert service.inspect("gallery/photos")["artifact"]["lifecycle"] == "published"


@pytest.mark.parametrize("photo", [{"path": "backend/assets/photos/missing.svg", "caption": "Missing image"}, {"path": "https://example.org/image.png", "caption": "Remote image"}, {"path": "../escape.png", "caption": "Unsafe image"}, {"path": "backend/assets/photos/one.svg"}])
def test_invalid_manual_photo_records_block_saved_snapshot(content_service, photo):
    service = content_service
    (service.root / "backend/data/photos.yaml").write_bytes(yaml_bytes({"version": 1, "photos": [photo]}))
    with pytest.raises(ServiceError):
        service.snapshot()


@pytest.mark.parametrize("path,bad", [("backend/data/catalog.yaml", "version: 1\nversion: 1\nartifacts: []\n"), ("backend/data/catalog.yaml", "version: 1\nartifacts: wrong-type\n"), ("backend/data/portfolio.yaml", "version: 1\nentries: [\n"), ("backend/data/profile.yaml", "version: 1\nname: 42\n"), ("frontend/site.yaml", "version: 9\n")])
def test_malformed_manual_yaml_blocks_snapshot_without_rewriting(content_service, path, bad):
    service = content_service
    target = service.root / path
    target.write_text(bad)
    with pytest.raises(ServiceError):
        service.snapshot()
    assert target.read_text() == bad


@pytest.mark.parametrize("body", ["No title but authored body", "# Chapter Title\n\n# Second title\n\nBody", "# Different title\n\nBody", "```markdown\n# Chapter Title\n```\n\nBody"])
def test_missing_multiple_mismatched_or_fenced_only_h1_blocks_chapter(content_service, body):
    service = content_service
    course(service)
    chapter(service, start=True)
    path = service.root / "content/notebooks/courses/example/01.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell(body)]), path)
    before = path.read_bytes()
    with pytest.raises(ServiceError, match="one H1"):
        service.validate()
    assert path.read_bytes() == before


def test_real_h1_with_fake_fenced_and_code_headings_is_valid(content_service):
    service = content_service
    course(service)
    chapter(service, start=True)
    path = service.root / "content/notebooks/courses/example/01.ipynb"
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("# Chapter Title\n\n```markdown\n# Fake title\n```\n\nBody"), nbformat.v4.new_code_cell("# A Python comment", outputs=[nbformat.v4.new_output("stream", name="stdout", text="# Not a heading\n")])])
    nbformat.write(nb, path)
    service.validate()


def test_heading_match_compares_displayed_inline_text(content_service):
    service = content_service
    course(service)
    chapter(service, start=True)
    path = service.root / "content/notebooks/courses/example/01.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("# Chapter *Title*\n\nBody")]), path)
    service.validate()
    service.update("course/example/01", {"title": "Renamed Chapter"})
    out = nbformat.read(path, as_version=4)
    assert out.cells[0].source.startswith("# Renamed Chapter")
    assert "Body" in out.cells[0].source


def test_markdown_horizontal_rule_is_valid_authored_content(content_service):
    service = content_service
    post(service)
    service.start("post/example")
    path = service.root / "content/notebooks/posts/example.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("---\n\nOrdinary authored prose after a horizontal rule.")]), path)
    service.validate()


def test_title_only_scaffolds_do_not_count_as_authored_content(content_service):
    service = content_service
    post(service)
    path = service.root / "content/notebooks/posts/example.ipynb"
    path.parent.mkdir(parents=True)
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("# Example")]), path)
    service.validate()
    service.update("post/example", {"lifecycle": "draft"})
    assert not service.inspect("post/example")["has_authored_content"]
    with pytest.raises(ServiceError, match="Cannot publish: the notebook has no body content"):
        service.publish("post/example")
    course(service)
    chapter(service, start=True)
    chapter_source = service.root / "content/notebooks/courses/example/01.ipynb"
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("# Chapter Title")]), chapter_source)
    assert service.validate()["valid"]
    assert not service.inspect("course/example/01")["has_authored_content"]


@pytest.mark.parametrize("membership", ["duplicate", "foreign", "missing"])
def test_manual_course_toc_must_have_each_own_chapter_once(content_service, membership):
    service = content_service
    course(service)
    chapter_id = chapter(service)
    course(service, "other")
    foreign = chapter(service, "other")
    path = service.root / "backend/data/courses/example.yaml"
    data = yaml.safe_load(path.read_text())
    data["toc"][0]["chapters"] = {"duplicate": [chapter_id, chapter_id], "foreign": [chapter_id, foreign], "missing": []}[membership]
    path.write_bytes(yaml_bytes(data))
    with pytest.raises(ServiceError):
        service.validate()


def test_planned_parent_hides_all_children(content_service):
    service = content_service
    parent = course(service, published=True)
    planned = chapter(service, name="01")
    published = chapter(service, name="02", start=True)
    author_body(service, published)
    service.publish(published)
    parent_path = service.root / "content/notebooks/courses/example/index.ipynb"
    nbformat.write(nbformat.v4.new_notebook(), parent_path)
    service.update(parent, {"lifecycle": "planned"})
    state = service.snapshot().state
    visibility = {artifact.id: eligible(artifact, state.artifacts) for artifact in state.artifacts}
    assert not visibility[parent]
    assert not visibility[planned]
    assert not visibility[published]
    source = service.root / "content/notebooks/courses/example/01.ipynb"
    service.start(planned)
    before = source.read_bytes()
    with pytest.raises(ServiceError, match="parent course"):
        service.publish(planned)
    assert source.read_bytes() == before


@pytest.mark.parametrize("patch", [{"repository_url": "http://github.com/owner/repo"}, {"repository_url": "https://example.org/owner/repo"}, {"repository_url": "https://github.com/owner/repo?other=1"}, {"source_ref": "../main"}, {"source_ref": "main#fragment"}, {"timezone": "Invalid/Timezone"}])
def test_invalid_repository_settings_are_atomic(content_service, patch):
    service = content_service
    settings = service.read_data("settings")["data"]
    settings.update(patch)
    before = file_state(service)
    with pytest.raises(ServiceError):
        service.update_data("settings", settings)
    assert file_state(service) == before


def test_external_nonwrite_dependency_change_blocks_recovery(content_service):
    service = content_service
    post(service)
    def crash(stage, index):
        if stage == "installed" and index == 0:
            raise OSError("Crash before notebook install")
    service.store.fault = crash
    with pytest.raises(ServiceError, match="pending recovery"):
        service.start("post/example")
    profile = service.root / "backend/data/profile.yaml"
    content = profile.read_text() + "\n# External profile edit that must survive\n"
    profile.write_text(content)
    with pytest.raises(ServiceError) as conflict:
        ContentService(service.root).snapshot()
    assert conflict.value.code == "recovery_conflict"
    assert "backend/data/profile.yaml" in conflict.value.paths
    assert profile.read_text() == content
    assert not (service.root / "content/notebooks/posts/example.ipynb").exists()
    transactions = service.root / "backend/runtime/transactions"
    assert list(transactions.glob("*/preimage-0"))
    assert list(transactions.glob("*/candidate-1"))
