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
    monkeypatch.setattr(build_module, "route_for", lambda a: str(Path(a.path.replace("content/notebooks/", "nb/")).with_suffix(".qmd")) if a.kind == "gallery" else a.path.replace("content/notebooks/", "nb/"))
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
    metadata = yaml.safe_load(generated.cells[0].source.split("---", 2)[1])
    assert metadata["categories"] == ["Attention"]
    assert "?tag=" not in generated.cells[0].source
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
    metadata = yaml.safe_load(listing.split("---", 2)[1])
    assert metadata["listing"]["contents"][0]["categories"] == ["Public"]
    assert "Private secret" not in listing
    assert "Draft secret" not in listing


def test_posts_listing_uses_native_categories_with_legacy_labels(workspace):
    from watchtower.models import Artifact
    root, snapshot = workspace
    entry = Artifact(id='post/tagged', kind='post', title='Tagged post', path='content/notebooks/posts/tagged.ipynb', lifecycle='draft', categories=['meta', 'dev'], tags=['Meta', 'NLP'], planned={'content': 'A planned post.'})
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell('Saved body')])
    stage = BuildService(root).generate('preview')
    listing = yaml.safe_load((stage / 'posts.qmd').read_text().split('---', 2)[1])['listing']
    assert listing['type'] == 'table'
    assert listing['categories'] is True
    assert listing['fields'] == ['date', 'title', 'description', 'categories', 'reading-time']
    assert listing['page-size'] == 10
    assert listing['sort-ui'] == ['date', 'title', 'reading-time']
    post = listing['contents'][0]
    assert post['categories'] == ['Meta', 'NLP', 'dev']
    assert 'tags' not in post
    assert post['path'] == '/nb/posts/tagged.ipynb'
    assert post['outputHref'] == '/nb/posts/tagged.html'
    assert post['reading-time'] == 1
    assert not (stage / 'assets/post-tags.js').exists()
    assert entry.model_dump()['tags'] == ['Meta', 'NLP', 'dev']


@pytest.mark.parametrize('kind', ['post', 'personal', 'portfolio'])
def test_generated_metadata_maps_tags_to_quarto_categories(workspace, kind):
    from watchtower.models import Artifact

    root, snapshot = workspace
    entry = Artifact(id=f'{kind}/tagged', kind=kind, title='Tagged entry', path=f'content/notebooks/{kind}/tagged.ipynb', lifecycle='draft', categories=['meta', 'dev'], tags=['Meta', 'NLP'], planned={'content': 'A planned entry.'})
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell('Saved body')])
    stage = BuildService(root).generate('preview')
    notebook = nbformat.read(stage / f'nb/{kind}/tagged.ipynb', as_version=4)
    metadata = yaml.safe_load(notebook.cells[0].source.split('---')[1])
    assert metadata['categories'] == ['Meta', 'NLP', 'dev']
    assert 'tags' not in metadata
    assert entry.model_dump()['tags'] == ['Meta', 'NLP', 'dev']


def test_native_posts_listing_preserves_draft_badges_only_in_preview(workspace):
    root, snapshot = workspace
    entry = artifact('posts/draft', lifecycle='draft', tags=['meta', 'dev'], description=None, date=None)
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell('Saved draft body.')])
    stage = BuildService(root).generate('preview')
    listing = yaml.safe_load((stage / 'posts.qmd').read_text().split('---', 2)[1])['listing']
    assert '<span class="draft-badge">draft</span>' in listing['contents'][0]['title']
    assert listing['contents'][0]['description'] == ''
    assert 'date' not in listing['contents'][0]
    production = BuildService(root).generate('production')
    listing = yaml.safe_load((production / 'posts.qmd').read_text().split('---', 2)[1])['listing']
    assert listing['contents'] == []


def test_planned_generation_uses_public_description_and_never_copies_optional_scaffold(workspace):
    root, snapshot = workspace
    entry = artifact("posts/plan", lifecycle="planned")
    entry.planned = {"content": "## A flexible outline\n\nSaved planning prose."}
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("")])
    for mode in ("preview", "production"):
        stage = BuildService(root).generate(mode)
        assert not (stage / "nb/posts/plan.ipynb").exists()
        assert "posts/plan" not in (stage / "posts.qmd").read_text()


@pytest.mark.parametrize("kind", ["post", "chapter", "course", "personal"])
@pytest.mark.parametrize("lifecycle", ["draft", "published"])
def test_shared_draft_panel_without_native_banner(workspace, kind, lifecycle):
    root, snapshot = workspace
    entry = artifact("courses/example/index" if kind == "course" else f"{kind}/example", kind=kind, lifecycle=lifecycle)
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("An authored page.")])
    if kind == "course":
        snapshot.state.courses[entry.id] = Record(purpose="A course purpose.", audience="Readers", planned={}, actualized={}, toc=[])
    if kind == "chapter":
        parent = artifact("courses/parent/index", kind="course")
        entry.parent = parent.id
        entry.toc_title = entry.title
        put_notebook(snapshot, parent, [nbformat.v4.new_markdown_cell("Course home")])
        snapshot.state.courses[parent.id] = Record(actualized={}, planned={}, toc=[Record(id="main", title="", chapters=[entry.id])])
    stage = BuildService(root).generate("preview")
    notebook = nbformat.read(stage / entry.path.replace("content/notebooks/", "nb/"), as_version=4)
    header = yaml.safe_load(notebook.cells[0].source.split("---", 2)[1])
    assert "draft" not in header
    assert header["lifecycle"] == lifecycle
    assert ('aria-label="Publication status"' in notebook.cells[0].source) == (lifecycle == "draft")
    if lifecycle == "draft":
        assert "Review content, then publish in CMS" in notebook.cells[0].source
    assert "callout-note" not in notebook.cells[0].source
    assert yaml.safe_load((stage / "_quarto.yml").read_text())["website"]["draft-mode"] == "visible"
    production = BuildService(root).generate("production")
    assert (production / entry.path.replace("content/notebooks/", "nb/")).exists() == (lifecycle == "published")
    assert yaml.safe_load((production / "_quarto.yml").read_text())["website"]["draft-mode"] == "gone"


def test_portfolio_order_eligibility_and_archived_source_link(workspace):
    root, snapshot = workspace
    for name, lifecycle in [("first", "published"), ("draft", "draft"), ("planned", "planned")]:
        entry = artifact(f"portfolio/{name}", kind="portfolio", lifecycle=lifecycle)
        put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("Historical notebook.")])
        snapshot.state.portfolio.append(Record(
            id=entry.id, abstract=f"Abstract {name}", figure_path=f"backend/assets/{name}.svg", figure_caption=f"Figure {name}",
            notebook_path=entry.path, project_path=f"archive/2026-09-30/projects/{name}", planned={},
        ))
        snapshot.files[f"backend/assets/{name}.svg"] = b"<svg/>"
    stage = BuildService(root).generate("production")
    page = (stage / "portfolio.qmd").read_text()
    assert ".portfolio-layout" in page and ".portfolio-sidebar" in page
    assert "Abstract first" in page
    assert "Abstract draft" not in page and "Abstract planned" not in page
    assert "[Source </>](https://github.com/example/site/tree/main/archive/2026-09-30/projects/first)" in page
    assert "[`first/`](https://github.com/example/site/tree/main/archive/2026-09-30/projects/first)" in page
    assert "Archived source" not in page
    assert "https://github.com/example/site/tree/main/archive/2026-09-30/projects/first" in page
    assert page.count("#portfolio-first") == 2
    assert "[Read the full project page →](nb/portfolio/first.ipynb)" in page
    assert "View notebook" not in page
    preview = BuildService(root).generate("preview")
    preview_page = (preview / "portfolio.qmd").read_text()
    assert preview_page.count('aria-label="Publication status"') == 1
    assert "callout-caution" not in preview_page
    for name in ("draft",):
        notebook = nbformat.read(preview / f"nb/portfolio/{name}.ipynb", as_version=4)
        assert 'aria-label="Publication status"' in notebook.cells[0].source
        assert "callout-" not in notebook.cells[0].source
        assert ('start:   wt start' in notebook.cells[0].source) == (name == "planned")
    assert "portfolio/planned" not in preview_page
    assert not (preview / "nb/portfolio/planned.ipynb").exists()
    assert not (preview / "assets/planned.svg").exists()


def test_started_draft_removes_duplicate_title_h1_and_preserves_body(workspace):
    root, snapshot = workspace
    entry = artifact("posts/started", lifecycle="draft", title="Started Draft")
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("# Started Draft\n\nBody content survives.")])
    original = snapshot.files[entry.path]

    stage = BuildService(root).generate("preview")
    generated = nbformat.read(stage / "nb/posts/started.ipynb", as_version=4)

    header = yaml.safe_load(generated.cells[0].source.split("---", 2)[1])
    assert header["title"] == entry.title
    assert sum(cell.source.count(entry.title) for cell in generated.cells) == 1
    assert "# Started Draft" not in "\n".join(cell.source for cell in generated.cells[1:])
    assert "Body content survives." in "\n".join(cell.source for cell in generated.cells[1:])
    assert snapshot.files[entry.path] == original


@pytest.mark.parametrize(
    ("abstract", "description", "expected_abstract"),
    [
        ("A project-specific abstract.", "Catalog description.", "A project-specific abstract."),
        ("", "Catalog fallback description.", "Catalog fallback description."),
        ("", None, "Project description not added yet."),
    ],
)
def test_portfolio_page_header_includes_figure_abstract_and_active_source(
    workspace, abstract, description, expected_abstract,
):
    root, snapshot = workspace
    entry = artifact(
        "portfolio/featured-project", kind="portfolio", lifecycle="draft",
        title="Featured project", description=description,
    )
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("Project details.")])
    figure_path = "backend/assets/featured-project.svg"
    snapshot.files[figure_path] = b"<svg/>"
    snapshot.state.portfolio.append(Record(
        id=entry.id, abstract=abstract, figure_path=figure_path, figure_caption="Featured figure",
        notebook_path=entry.path, project_path="projects/featured-project", planned={},
    ))
    original = snapshot.files[entry.path]

    stage = BuildService(root).generate("preview")
    generated = nbformat.read(stage / "nb/portfolio/featured-project.ipynb", as_version=4)
    header = generated.cells[0].source
    figure = "![Featured figure](../../assets/featured-project.svg)"
    source = "[Project source](https://github.com/example/site/tree/main/projects/featured-project)"

    assert figure in header
    assert f"**Abstract.** {expected_abstract}" in header
    assert f"[← Portfolio](../../portfolio.qmd) | {source}\n" in header
    # The abstract renders once: as labeled body content, not again in the title block.
    assert "description" not in yaml.safe_load(header.split("---", 2)[1])
    assert header.index('aria-label="Publication status"') < header.index("[← Portfolio]")
    assert header.index("[← Portfolio]") < header.index(figure)
    assert header.index(source) < header.index(figure)
    assert header.index(figure) < header.index(f"**Abstract.** {expected_abstract}")
    assert (stage / "assets/featured-project.svg").read_bytes() == b"<svg/>"
    assert snapshot.files[entry.path] == original


def test_portfolio_page_links_archived_code_under_archive(workspace):
    root, snapshot = workspace
    entry = artifact("portfolio/historical", kind="portfolio", lifecycle="published", title="Historical project", description=None)
    put_notebook(snapshot, entry, [nbformat.v4.new_markdown_cell("Project details.")])
    snapshot.state.portfolio.append(Record(
        id=entry.id, abstract="An archived project.", figure_path=None, figure_caption=None,
        notebook_path=entry.path, project_path="archive/2026-09-30/projects/historical", planned={},
    ))

    stage = BuildService(root).generate()
    header = nbformat.read(stage / "nb/portfolio/historical.ipynb", as_version=4).cells[0].source

    assert "[Project source](https://github.com/example/site/tree/main/archive/2026-09-30/projects/historical)" in header


def test_chapter_page_preserves_authored_title_h1(workspace):
    root, snapshot = workspace
    course = artifact("courses/example/index", kind="course", title="Example course")
    chapter = artifact(
        "courses/example/01-introduction", kind="chapter", title="Introduction",
        parent=course.id, toc_title="Introduction", section="main",
    )
    put_notebook(snapshot, course, [nbformat.v4.new_markdown_cell("Course introduction.")])
    put_notebook(snapshot, chapter, [nbformat.v4.new_markdown_cell("# Introduction\n\nChapter content.")])
    snapshot.state.courses[course.id] = Record(purpose="Learn.", audience="Readers", planned={}, actualized={}, toc=[])

    stage = BuildService(root).generate("preview")
    generated = nbformat.read(stage / "nb/courses/example/01-introduction.ipynb", as_version=4)

    assert generated.cells[1].source.startswith("# Introduction")
    assert "Chapter content." in generated.cells[1].source
    # The authored H1 supplies the title; the generated title block stays empty.
    header = yaml.safe_load(generated.cells[0].source.split("---", 2)[1])
    assert header["format"]["html"]["template-partials"] == ["/templates/title-block.html"]
    assert (stage / "templates/title-block.html").exists()


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


def test_preview_code_changes_rebuild_in_fresh_worker(tmp_path, monkeypatch):
    source = tmp_path / "src/watchtower/services/build.py"
    source.parent.mkdir(parents=True)
    source.write_text("# original build code\n")
    service = BuildService(tmp_path)
    ready = threading.Event()
    submitted = threading.Event()
    calls = []
    signature = service._preview_signature

    def read_signature():
        value = signature()
        ready.set()
        return value

    def submit(mode):
        calls.append(mode)
        submitted.set()

    class Server:
        def __init__(self, *args):
            pass

        def serve_forever(self):
            assert ready.wait(3)
            source.write_text("# updated build code using Jinja\n")
            assert submitted.wait(3)

        def server_close(self):
            pass

    monkeypatch.setattr(service, "build", lambda mode: {"status": "succeeded"})
    monkeypatch.setattr(service, "submit", submit)
    monkeypatch.setattr(service, "_preview_signature", read_signature)
    monkeypatch.setattr(build_module, "ThreadingHTTPServer", Server)

    service.preview()

    assert calls == ["preview"]


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
    listing = yaml.safe_load((first / "courses.qmd").read_text().split("---", 2)[1])["listing"]
    assert listing == {"contents": [{"path": "nb/courses/example/index.html", "outputHref": "nb/courses/example/index.html", "title": course.title, "description": course.description}], "type": "grid", "sort": False, "fields": ["title", "description", "image"]}
    config = yaml.safe_load((first / "_quarto.yml").read_text())
    sidebar = json.dumps(config["website"]["sidebar"])
    assert "01. Short title" in sidebar and "02. Private title" not in sidebar
    assert (first / "nb/courses/example/01-child.ipynb").exists()
    assert (first / "nb/courses/example/child.svg").exists()
    course.lifecycle = "draft"
    child.lifecycle = "draft"
    preview = BuildService(root).generate("preview")
    sidebar = yaml.safe_load((preview / "_quarto.yml").read_text())["website"]["sidebar"][0]["contents"]
    assert 'class="draft-badge"' in sidebar[0]["text"]
    assert 'class="draft-badge"' in sidebar[1]["contents"][0]["text"]
    assert 'class="draft-badge"' not in sidebar[1]["contents"][1]["text"]
    child.lifecycle = "published"
    withdrawn = BuildService(root).generate("production")
    assert yaml.safe_load((withdrawn / "courses.qmd").read_text().split("---", 2)[1])["listing"]["contents"] == []
    assert not (withdrawn / "nb/courses/example/01-child.ipynb").exists()
    assert not (withdrawn / "nb/courses/example/child.svg").exists()
    assert yaml.safe_load((withdrawn / "_quarto.yml").read_text())["website"]["sidebar"] == []
    assert contract.toc == original_toc
    assert child.lifecycle == "published"
    course.lifecycle = "published"
    restored = BuildService(root).generate("production")
    assert (restored / "nb/courses/example/01-child.ipynb").exists()
    assert not (restored / "nb/courses/example/02-private.ipynb").exists()


def test_planned_chapter_is_absent_from_frontend(workspace):

    root, snapshot = workspace
    course = artifact("courses/example/index", kind="course")
    chapter = artifact("courses/example/chapter", kind="chapter", lifecycle="planned", parent=course.id, toc_title="01. Short label", section="first")
    put_notebook(snapshot, course, [nbformat.v4.new_markdown_cell("A course home.")])
    put_notebook(snapshot, chapter, [nbformat.v4.new_markdown_cell(f"# {chapter.title}")])
    snapshot.state.courses[course.id] = Record(
        purpose="Understand plans.", audience="Readers", actualized={"summary": ""},
        planned={"summary": "A planned path", "chapters": [{"chapter_id": chapter.id, "content": "Explain the model.", "lab_and_evidence": "Check saved results.", "section": "first"}]},
        toc=[Record(id="first", title="First", chapters=[chapter.id])],
    )
    for mode in ("preview", "production"):
        stage = BuildService(root).generate(mode)
        assert not (stage / "nb/courses/example/chapter.ipynb").exists()
        assert "chapter.ipynb" not in (stage / "_quarto.yml").read_text()


def test_validation_failure_does_not_promote_and_is_visible_in_record(workspace, monkeypatch):
    root, snapshot = workspace
    monkeypatch.setattr(build_module.subprocess, "run", fake_quarto)
    service = BuildService(root)
    first = service.build()
    current = (root / "frontend/generated/preview").resolve()
    def invalid_snapshot():
        raise ValueError("backend/data/catalog.yaml: unknown relation post/missing")
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
    snapshot.state.photos = [Record(heading="A photo", path="backend/assets/a-photo.svg", caption="A caption.", lifecycle="published")]
    snapshot.files["backend/assets/a-photo.svg"] = b"<svg/>"
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


def test_personal_renders_once_from_jinja_at_the_gallery_route(workspace):
    from watchtower.models import Artifact, route_for

    legacy = Artifact(id="gallery/photos", kind="gallery", title="Personal", path="backend/data/photos.yaml", route="nb/photos/photos.ipynb")
    assert route_for(legacy) == "nb/photos/photos.qmd"
    root, snapshot = workspace
    template = "frontend/templates/site/personal.qmd.j2"
    snapshot.files[template] = snapshot.files[template].replace(b"A few snapshots from life beyond the desk.", b"Shared gallery introduction.")
    gallery = artifact("gallery/photos", kind="gallery", path="content/notebooks/photos/photos.ipynb", title="Personal")
    snapshot.state.artifacts.append(gallery)
    note = artifact("personal/notes", kind="personal", visibility="private", title="Private prose notebook")
    put_notebook(snapshot, note, [nbformat.v4.new_markdown_cell("Personal prose stays on its direct working page.")])
    snapshot.state.photos = [Record(heading="First photo", path="backend/assets/photos/first photo.svg", caption="A real photo caption.", lifecycle="published"), Record(heading="Unfinished photo", path="backend/assets/photos/draft.svg", caption="Draft caption.", lifecycle="draft")]
    snapshot.files["backend/assets/photos/first photo.svg"] = b"<svg/>"
    snapshot.files["backend/assets/photos/draft.svg"] = b"<svg/>"
    for mode in ["preview", "production"]:
        stage = BuildService(root).generate(mode)
        config = yaml.safe_load((stage / "_quarto.yml").read_text())
        personal_nav = next(entry for entry in config["website"]["navbar"]["left"] if entry["text"] == "personal")
        assert personal_nav["href"] == "nb/photos/photos.qmd"
        assert "personal.qmd" not in config["project"]["render"]
        assert "nb/photos/photos.ipynb" not in config["project"]["render"]
        assert not (stage / "personal.qmd").exists()
        assert not (stage / "nb/photos/photos.ipynb").exists()
        page = (stage / "nb/photos/photos.qmd").read_text()
        assert "Shared gallery introduction." in page
        assert page.index("![](") < page.index("\nA real photo caption.")
        assert "## First photo" in page
        assert ("Unfinished photo" in page) == (mode == "preview")
        assert ('aria-label="Publication status"' in page) == (mode == "preview")
        assert (stage / "assets/photos/draft.svg").exists() == (mode == "preview")
        assert "../../assets/photos/first%20photo.svg" in page
        assert "Private prose notebook" not in page
        assert "personal/notes" not in page
        header = yaml.safe_load(page.split("---", 2)[1])
        assert header["toc"] is True
        assert "page-layout" not in header
        assert "{.lightbox fig-alt=" in page
        assert (stage / "nb/personal/notes.ipynb").exists() == (mode == "preview")


@pytest.mark.parametrize("has_draft", [False, True])
def test_planned_gallery_preview_label_and_production_exclusion(workspace, has_draft):
    root, snapshot = workspace
    gallery = artifact("gallery/photos", kind="gallery", lifecycle="planned", path="content/notebooks/photos/photos.ipynb", title="Personal")
    snapshot.state.artifacts.append(gallery)
    if has_draft:
        snapshot.state.photos = [Record(heading="Draft afternoon", path="backend/assets/photos/draft.svg", caption="A draft caption.", lifecycle="draft")]
        snapshot.state.photos.append(Record(heading="Draft stub", path="", caption="A saved caption.", lifecycle="draft"))
        snapshot.files["backend/assets/photos/draft.svg"] = b"<svg/>"
    for mode in ["preview", "production"]:
        stage = BuildService(root).generate(mode)
        page = (stage / "nb/photos/photos.qmd").read_text()
        header, body = page.split("---", 2)[1:]
        show_draft = has_draft and mode == "preview"
        assert "callout-note" not in header
        assert 'aria-label="Publication status"' not in header
        assert ('aria-label="Publication status"' in body) == show_draft
        assert ("Draft afternoon" in body) == show_draft
        assert ('aria-label="No Photo"' in body) == show_draft
        assert ('image:   not uploaded' in body) == show_draft
        assert ('image:   uploaded' in body) == show_draft
        assert 'callout-caution' not in body
        assert ("Draft stub" in body) == show_draft
        assert (stage / "assets/photos/draft.svg").exists() == show_draft
        assert gallery.lifecycle == "planned"
        if has_draft:
            assert snapshot.state.photos[0].lifecycle == "draft"


def test_cms_palette_never_enters_reader_project(workspace):
    root, snapshot = workspace
    snapshot.files["frontend/templates/cms/static/theme.css"] = b":root { --wt-background: black; --wt-accent: violet; }"
    stage = BuildService(root).generate("production")
    assert not (stage / "assets/theme.css").exists()
    assert not (stage / "frontend/templates/cms").exists()
    assert not list(stage.rglob("theme.css"))
    config = yaml.safe_load((stage / "_quarto.yml").read_text())
    assert config["format"]["html"]["theme"] == "united"
    stylesheet = config["format"]["html"]["css"]
    assert stylesheet.startswith("assets/styles-")
    assert (stage / stylesheet).read_bytes() == snapshot.files["frontend/assets/styles.css"]


@pytest.mark.parametrize("css", ["assets/styles.css", ["assets/styles.css", "assets/extra.css"]])
def test_stylesheet_url_changes_with_saved_css(workspace, css):
    root, snapshot = workspace
    snapshot.state.settings.quarto["format"]["html"]["css"] = css
    first = BuildService(root).generate("preview")
    first_css = yaml.safe_load((first / "_quarto.yml").read_text())["format"]["html"]["css"]
    snapshot.files["frontend/assets/styles.css"] += b"\n.publication-meta { background: yellow; }\n"
    second = BuildService(root).generate("preview")
    second_css = yaml.safe_load((second / "_quarto.yml").read_text())["format"]["html"]["css"]
    assert first_css != second_css
    if isinstance(css, list):
        assert first_css[1:] == second_css[1:] == ["assets/extra.css"]
        second_css = second_css[0]
    assert (second / second_css).read_bytes() == snapshot.files["frontend/assets/styles.css"]


def test_resume_keeps_compact_lists_and_section_boundaries(workspace):
    root, snapshot = workspace
    snapshot.state.profile.employment[0]["bullets"] = ["First achievement.", "Second achievement."]
    snapshot.state.profile.skills = [{"name": "Engineering", "entries": ["Python", "SQL"]}]
    stage = BuildService(root).generate()
    resume = (stage / "resume.qmd").read_text()
    assert "- First achievement.\n- Second achievement.\n" in resume
    assert "- Python\n- SQL\n" in resume
    assert "- Second achievement.\n\n" in resume
    assert "## Employment History" in resume
    assert "## Skills" in resume
    assert ".resume-overview" in resume
