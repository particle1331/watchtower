"""Publishing tests use an immutable input snapshot and a fake Quarto executable."""

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import nbformat
import pytest
import yaml

import watchtower.services.build as build_module
from watchtower.services.build import BuildService


class Record(SimpleNamespace):
    def model_dump(self, mode="json", **kwargs):
        return copy.deepcopy(vars(self))


def artifact(identifier, kind="post", lifecycle="published", visibility="public", **extra):
    data = dict(
        id=identifier, kind=kind, title=identifier.split("/")[-1].replace("-", " "),
        lifecycle=lifecycle, visibility=visibility,
        path=f"content/notebooks/{identifier}.ipynb", description="A saved description",
        date="2026-10-01", tags=[], categories=[], relations=[], planned={"content": "A plan"},
    )
    data.update(extra)
    return Record(**data)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    templates = Path(__file__).resolve().parents[1] / "frontend"
    files = {
        str(path.relative_to(templates.parent)): path.read_bytes()
        for path in templates.rglob("*") if path.is_file() and "generated" not in path.parts
    }
    profile = Record(
        name="A Reader", contact={"github": "reader", "linkedin": "linkedin.com/in/reader", "phone": "123", "email": "reader@example.com"},
        summary="engineer", homepage_intro=["A notebook collection."], employment=[{"title": "Engineer", "company": "Example", "dates": "2026", "bullets": []}],
        early_employment=[], skills=[], education=[], projects=[],
    )
    state = Record(artifacts=[], courses={}, portfolio=[], profile=profile, photos=[], settings=Record(
        repository_url="https://github.com/example/site", source_ref="main", timezone="Asia/Manila", quarto=yaml.safe_load(files["frontend/site.yaml"])["quarto"],
    ))
    snapshot = SimpleNamespace(state=state, files=files, revision="saved-revision")
    monkeypatch.setattr(build_module, "ContentService", lambda root: SimpleNamespace(snapshot=lambda: snapshot))
    monkeypatch.setattr(build_module, "source_path", lambda a, state: a.path if a.kind != "project" else None)
    monkeypatch.setattr(build_module, "route_for", lambda a: a.path.replace("content/notebooks/", "nb/"))
    monkeypatch.setattr(build_module, "eligible", lambda a, artifacts, mode: mode == "preview" or (a.visibility == "public" and a.lifecycle in {"planned", "published"}))
    monkeypatch.setattr(build_module, "plan_body", lambda a, state: a.planned["content"])
    def pdf(stage):
        (stage / "assets/resume.pdf").write_bytes(b"%PDF-1.7\n")
    monkeypatch.setattr(build_module, "build_resume_pdf", pdf)
    return tmp_path, snapshot


def put_notebook(snapshot, entry, cells):
    notebook = nbformat.v4.new_notebook(cells=cells)
    snapshot.files[entry.path] = nbformat.writes(notebook).encode()
    snapshot.state.artifacts.append(entry)
    return notebook


def test_generation_preserves_notebook_cells_outputs_and_attachments(workspace):
    root, snapshot = workspace
    entry = artifact("posts/output", tags=["Attention"])
    code = nbformat.v4.new_code_cell("#| echo: false\n#| code-fold: true\nprint('saved')", execution_count=4,
        outputs=[nbformat.v4.new_output("stream", name="stdout", text="saved\n")])
    markdown = nbformat.v4.new_markdown_cell("![inline](attachment:figure.png)\n![relative](images/chart.svg)")
    markdown.attachments = {"figure.png": {"image/png": "aW1hZ2U="}}
    original = put_notebook(snapshot, entry, [markdown, code])
    snapshot.files["content/notebooks/posts/images/chart.svg"] = b"<svg></svg>"
    before = snapshot.files[entry.path]
    stage = BuildService(root).generate()
    generated = nbformat.read(stage / "nb/posts/output.ipynb", as_version=4)
    assert generated.cells[1:] == original.cells
    assert snapshot.files[entry.path] == before
    assert (stage / "nb/posts/images/chart.svg").read_bytes() == b"<svg></svg>"
    assert "tag=Attention" in generated.cells[0].source
    config = yaml.safe_load((stage / "_quarto.yml").read_text())
    assert config["execute"] == {"enabled": False}
    assert "nb/posts/images/chart.svg" in config["project"]["resources"]
    assert not (stage / "frontend/templates/cms").exists()


def test_production_omits_private_draft_notebooks_assets_and_tags(workspace):
    root, snapshot = workspace
    for identifier, lifecycle, visibility, tag in [
        ("posts/public", "published", "public", "Public"),
        ("posts/private", "published", "private", "Private secret"),
        ("posts/draft", "draft", "public", "Draft secret"),
    ]:
        entry = artifact(identifier, lifecycle=lifecycle, visibility=visibility, tags=[tag])
        put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell(f"![asset]({tag}.svg)")])
        snapshot.files[f"content/notebooks/posts/{tag}.svg"] = tag.encode()
    stage = BuildService(root).generate("production")
    assert (stage / "nb/posts/public.ipynb").exists()
    assert not (stage / "nb/posts/private.ipynb").exists()
    assert not (stage / "nb/posts/draft.ipynb").exists()
    assert not (stage / "nb/posts/Private secret.svg").exists()
    listing = (stage / "posts.qmd").read_text()
    assert "Public (1)" in listing
    assert "Private secret" not in listing
    assert "Draft secret" not in listing


def test_planned_generation_uses_plan_and_never_copies_optional_scaffold(workspace):
    root, snapshot = workspace
    entry = artifact("posts/plan", lifecycle="planned")
    entry.planned = {"content": "## A flexible outline\n\nSaved planning prose."}
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("")])
    stage = BuildService(root).generate("production")
    notebook = nbformat.read(stage / "nb/posts/plan.ipynb", as_version=4)
    assert notebook.cells[1].source == entry.planned["content"]
    assert "**Planned**" in notebook.cells[0].source
    assert len(notebook.cells) == 2


def test_portfolio_order_eligibility_and_archived_source_link(workspace):
    root, snapshot = workspace
    for name, lifecycle in [("first", "published"), ("draft", "draft"), ("planned", "planned")]:
        entry = artifact(f"portfolio/{name}", kind="portfolio", lifecycle=lifecycle)
        put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("Historical notebook.")])
        snapshot.state.portfolio.append(Record(
            id=entry.id, abstract=f"Abstract {name}", figure_path=f"content/assets/{name}.svg", figure_caption=f"Figure {name}",
            notebook_path=entry.path, project_name=name, project_source="archived", archive_date="2026-09-30", planned={},
        ))
        snapshot.files[f"content/assets/{name}.svg"] = b"<svg/>"
    stage = BuildService(root).generate("production")
    page = (stage / "portfolio.qmd").read_text()
    assert ".portfolio-layout" in page and ".portfolio-sidebar" in page
    assert "Abstract first" in page
    assert "Abstract draft" not in page and "Abstract planned" not in page
    assert "Archived source" in page
    assert "https://github.com/example/site/tree/main/archive/2026-09-30/projects/first" in page
    assert page.count("#portfolio-first") == 2


def fake_quarto(command, cwd, **kwargs):
    assert command == ["quarto", "render", "--no-execute"]
    output = Path(cwd) / "_site"
    output.mkdir()
    (output / "index.html").write_text("Last successful site")
    return SimpleNamespace(returncode=0)


def test_failed_build_preserves_previous_success_and_fresh_success_removes_stale_output(workspace, monkeypatch):
    root, snapshot = workspace
    service = BuildService(root)
    monkeypatch.setattr(build_module.subprocess, "run", fake_quarto)
    first = service.build()
    assert first["status"] == "succeeded"
    target = root / "frontend/generated/preview"
    original = target.resolve()
    (original / "_site/stale.html").write_text("stale")
    monkeypatch.setattr(build_module.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    failed = service.build()
    assert failed["status"] == "failed" and "Quarto exited" in failed["error"]
    assert target.resolve() == original
    assert (target / "_site/index.html").read_text() == "Last successful site"
    monkeypatch.setattr(build_module.subprocess, "run", fake_quarto)
    last = service.build()
    assert last["status"] == "succeeded" and target.resolve() != original
    assert not (target / "_site/stale.html").exists()
    assert service.get(last["id"]) == last


def test_multiple_service_clients_serialize_rendering(workspace, monkeypatch):
    root, snapshot = workspace
    counter = {"active": 0, "peak": 0}
    lock = threading.Lock()
    def run(command, cwd, **kwargs):
        with lock:
            counter["active"] += 1
            counter["peak"] = max(counter["active"], counter["peak"])
        time.sleep(0.05)
        result = fake_quarto(command, cwd, **kwargs)
        with lock:
            counter["active"] -= 1
        return result
    monkeypatch.setattr(build_module.subprocess, "run", run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: BuildService(root).build(), range(2)))
    assert all(r["status"] == "succeeded" for r in results)
    assert counter["peak"] == 1


def test_submit_returns_queued_record_before_worker_finishes(workspace, monkeypatch):
    root, snapshot = workspace
    calls = []
    monkeypatch.setattr(build_module.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    service = BuildService(root)
    result = service.submit()
    assert result["status"] == "queued"
    assert calls[0][1]["start_new_session"] is True
    assert json.loads((root / f"backend/runtime/builds/{result['id']}.json").read_text()) == result


def test_course_withdrawal_suppresses_descendants_and_keeps_authored_toc(workspace, monkeypatch):
    from watchtower.models import eligible

    root, snapshot = workspace
    monkeypatch.setattr(build_module, "eligible", eligible)
    course = artifact("courses/example/index", kind="course")
    child = artifact("courses/example/01-child", kind="chapter", parent=course.id, toc_title="01. Short title", section="first")
    private = artifact("courses/example/02-private", kind="chapter", visibility="private", parent=course.id, toc_title="02. Private title", section="first")
    put_notebook(snapshot, course, [nbformat.v4.new_markdown_cell("An authored course home.")])
    put_notebook(snapshot, child, [nbformat.v4.new_markdown_cell("# A chapter\n\n![asset](child.svg)")])
    put_notebook(snapshot, private, [nbformat.v4.new_markdown_cell("# A private chapter\n\nPrivate content.")])
    snapshot.files["content/notebooks/courses/example/child.svg"] = b"<svg/>"
    contract = Record(purpose="Understand selection.", audience="Readers", planned={"summary": "A course path"}, actualized={"summary": ""}, toc=[Record(id="first", title="First", chapters=[child.id, private.id])])
    snapshot.state.courses[course.id] = contract
    original_toc = copy.deepcopy(contract.toc)
    first = BuildService(root).generate("production")
    config = yaml.safe_load((first / "_quarto.yml").read_text())
    sidebar = json.dumps(config["website"]["sidebar"])
    assert "01. Short title" in sidebar and "02. Private title" not in sidebar
    assert (first / "nb/courses/example/01-child.ipynb").exists()
    assert (first / "nb/courses/example/child.svg").exists()
    course.lifecycle = "draft"
    withdrawn = BuildService(root).generate("production")
    assert not (withdrawn / "nb/courses/example/01-child.ipynb").exists()
    assert not (withdrawn / "nb/courses/example/child.svg").exists()
    assert yaml.safe_load((withdrawn / "_quarto.yml").read_text())["website"]["sidebar"] == []
    assert contract.toc == original_toc
    assert child.lifecycle == "published"
    course.lifecycle = "published"
    restored = BuildService(root).generate("production")
    assert (restored / "nb/courses/example/01-child.ipynb").exists()
    assert not (restored / "nb/courses/example/02-private.ipynb").exists()


def test_planned_chapter_body_matches_shared_start_template_and_preserves_one_h1(workspace, monkeypatch):
    from watchtower.models import plan_body

    root, snapshot = workspace
    monkeypatch.setattr(build_module, "plan_body", plan_body)
    course = artifact("courses/example/index", kind="course")
    chapter = artifact("courses/example/chapter", kind="chapter", lifecycle="planned", parent=course.id, toc_title="01. Short label", section="first")
    put_notebook(snapshot, course, [nbformat.v4.new_markdown_cell("A course home.")])
    put_notebook(snapshot, chapter, [nbformat.v4.new_markdown_cell(f"# {chapter.title}")])
    snapshot.state.courses[course.id] = Record(
        purpose="Understand plans.", audience="Readers", actualized={"summary": ""},
        planned={"summary": "A planned path", "chapters": [{"chapter_id": chapter.id, "content": "Explain the model.", "lab_and_evidence": "Check saved results.", "section": "first"}]},
        toc=[Record(id="first", title="First", chapters=[chapter.id])],
    )
    stage = BuildService(root).generate()
    notebook = nbformat.read(stage / "nb/courses/example/chapter.ipynb", as_version=4)
    assert notebook.cells[1].source == plan_body(chapter, snapshot.state)
    assert notebook.cells[1].source.count(f"# {chapter.title}") == 1
    assert "## Planned content" in notebook.cells[1].source
    assert "## Planned lab and evidence" in notebook.cells[1].source
    assert "template-partials" in notebook.cells[0].source


def test_validation_failure_does_not_promote_and_is_visible_in_record(workspace, monkeypatch):
    root, snapshot = workspace
    monkeypatch.setattr(build_module.subprocess, "run", fake_quarto)
    service = BuildService(root)
    first = service.build()
    current = (root / "frontend/generated/preview").resolve()
    def invalid_snapshot():
        raise ValueError("content/data/catalog.yaml: unknown relation post/missing")
    monkeypatch.setattr(build_module, "ContentService", lambda root: SimpleNamespace(snapshot=invalid_snapshot))
    failed = service.build()
    assert failed["status"] == "failed"
    assert "unknown relation" in failed["error"]
    assert "unknown relation" in service.get(failed["id"])["logs"]
    assert (root / "frontend/generated/preview").resolve() == current
    assert service.last_successful()["id"] == first["id"]


def test_generated_sources_are_byte_identical_for_unchanged_snapshot(workspace):
    root, snapshot = workspace
    planned = artifact("posts/plan", lifecycle="planned")
    snapshot.state.artifacts.append(planned)
    authored = artifact("posts/authored")
    put_notebook(snapshot, authored, [nbformat.v4.new_markdown_cell("Saved authored content.")])
    gallery = artifact("photos/gallery", kind="gallery")
    snapshot.state.artifacts.append(gallery)
    snapshot.state.photos = [Record(heading="A photo", path="content/assets/a-photo.svg", caption="A caption.", lifecycle="published")]
    snapshot.files["content/assets/a-photo.svg"] = b"<svg/>"
    service = BuildService(root)
    first, second = service.generate(), service.generate()
    config = yaml.safe_load((first / "_quarto.yml").read_text())
    for route in ["_quarto.yml", *config["project"]["render"]]:
        assert (first / route).read_bytes() == (second / route).read_bytes(), route
    authored_ids = nbformat.reads(snapshot.files[authored.path].decode(), as_version=4).cells
    generated = nbformat.read(first / "nb/posts/authored.ipynb", as_version=4)
    assert generated.cells[1:] == authored_ids


def test_missing_authored_image_fails_before_quarto_and_keeps_success(workspace, monkeypatch):
    root, snapshot = workspace
    entry = artifact("posts/assets")
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("![Result](images/result.svg)")])
    asset = "content/notebooks/posts/images/result.svg"
    snapshot.files[asset] = b"<svg/>"
    monkeypatch.setattr(build_module.subprocess, "run", fake_quarto)
    service = BuildService(root)
    success = service.build()
    previous = (root / "frontend/generated/preview").resolve()
    assert success["status"] == "succeeded"
    del snapshot.files[asset]
    def must_not_render(*args, **kwargs):
        raise AssertionError("Quarto must not run with a missing source asset")
    monkeypatch.setattr(build_module.subprocess, "run", must_not_render)
    failed = service.build()
    assert failed["status"] == "failed"
    assert "referenced asset does not exist: images/result.svg" in failed["error"]
    assert (root / "frontend/generated/preview").resolve() == previous
    assert service.last_successful()["id"] == success["id"]


def test_personal_navigation_and_alias_show_only_rows_of_photos(workspace):
    root, snapshot = workspace
    gallery = artifact("gallery/photos", kind="gallery", path="content/notebooks/photos/photos.ipynb", title="Personal")
    snapshot.state.artifacts.append(gallery)
    note = artifact("personal/notes", kind="personal", visibility="private", title="Private prose notebook")
    put_notebook(snapshot, note, [nbformat.v4.new_markdown_cell("Personal prose stays on its direct working page.")])
    snapshot.state.photos = [Record(heading="First photo", path="content/assets/photos/first photo.svg", caption="A real photo caption.", lifecycle="published"), Record(heading="Unfinished photo", path="content/assets/photos/draft.svg", caption="Draft caption.", lifecycle="draft")]
    snapshot.files["content/assets/photos/first photo.svg"] = b"<svg/>"
    snapshot.files["content/assets/photos/draft.svg"] = b"<svg/>"
    for mode in ["preview", "production"]:
        stage = BuildService(root).generate(mode)
        config = yaml.safe_load((stage / "_quarto.yml").read_text())
        personal_nav = next(entry for entry in config["website"]["navbar"]["left"] if entry["text"] == "personal")
        assert personal_nav["href"] == "nb/photos/photos.ipynb"
        alias = (stage / "personal.qmd").read_text()
        assert ".photo-rows" in alias
        assert "![A real photo caption.]" in alias
        assert "## First photo" in alias
        assert "Unfinished photo" not in alias
        assert not (stage / "assets/photos/draft.svg").exists()
        assert "assets/photos/first%20photo.svg" in alias
        assert "Private prose notebook" not in alias
        assert "personal/notes" not in alias
        notebook = nbformat.read(stage / "nb/photos/photos.ipynb", as_version=4)
        assert ".photo-rows" in notebook.cells[1].source
        assert "## First photo" in notebook.cells[1].source
        assert "Unfinished photo" not in notebook.cells[1].source
        assert "Private prose notebook" not in notebook.cells[1].source
        assert "personal/notes" not in notebook.cells[1].source
        assert (stage / "nb/personal/notes.ipynb").exists() == (mode == "preview")


def test_cms_palette_never_enters_reader_project(workspace):
    root, snapshot = workspace
    snapshot.files["frontend/templates/cms/static/theme.css"] = b":root { --wt-background: black; --wt-accent: violet; }"
    stage = BuildService(root).generate("production")
    assert not (stage / "assets/theme.css").exists()
    assert not (stage / "frontend/templates/cms").exists()
    assert not list(stage.rglob("theme.css"))
    config = yaml.safe_load((stage / "_quarto.yml").read_text())
    assert config["format"]["html"]["theme"] == "united"
    assert config["format"]["html"]["css"] == "assets/styles.css"
