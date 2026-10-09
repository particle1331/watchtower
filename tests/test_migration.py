"""Migration preserves authored notebooks and makes review decisions explicit."""

import copy

import nbformat
import pytest

from watchtower.notebook import read_notebook
from watchtower.services.migration import (
    Migration,
    document_header,
    extract_photos,
    h1_titles,
    load_yaml,
    normalize_notebook,
    read_source_notebook,
    yaml_bytes,
)


def notebook(*sources):
    return nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell(source) for source in sources])


def write_yaml(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(yaml_bytes(data))


def legacy_repo(root):
    artifacts = [{"id": "course/demo", "kind": "course", "title": "Demo", "path": "nb/courses/demo", "visibility": "public", "lifecycle": "published", "relations": []}, {"id": "course/demo/01-first", "kind": "chapter", "title": "First Chapter", "path": "nb/courses/demo/01-first.ipynb", "visibility": "public", "lifecycle": "draft", "relations": [], "parent": "course/demo"}]
    write_yaml(root, "knowledge/catalog.yaml", {"version": 1, "artifacts": artifacts})
    write_yaml(root, "knowledge/sidebar.yaml", {"website": {"sidebar": [{"id": "demo", "contents": [{"section": "Foundations", "contents": [{"text": "01. First", "href": "nb/courses/demo/01-first.ipynb"}]}]}]}})
    write_yaml(root, "nb/courses/demo/course.yaml", {"id": "course/demo", "purpose": "Learn", "audience": "Readers", "planned": {"summary": "A plan", "chapters": [{"01-first": "Introduce the first topic"}]}, "actualized": {"summary": "Checked earlier work"}})
    write_yaml(root, "assets/resume.yaml", {"name": "Example", "summary": "Résumé fact", "homepage_intro": ["Home fact"], "employment": [{"company": "Company", "bullets": ["Fact preserved"]}]})
    nbformat.write(notebook("---\ntitle: Demo\n---\n\nCourse body"), root / "nb/courses/demo/index.ipynb")
    nbformat.write(notebook("---\ntitle: First Chapter\ntoc: true\n---\n", "Chapter body"), root / "nb/courses/demo/01-first.ipynb")


def test_normalization_preserves_all_cell_and_notebook_fields():
    nb = notebook("---\ntitle: First Chapter\ncategories: [testing]\n---\n", "## Section\n\n![image](attachment:image.png)")
    nb.cells[1].attachments = {"image.png": {"image/png": "image-bytes"}}
    code = nbformat.v4.new_code_cell("#| code-fold: true\n#| label: fig-sample\nprint('result')", execution_count=12, outputs=[nbformat.v4.new_output("stream", name="stdout", text="result\n")])
    code.metadata["custom"] = {"keep": True}
    nb.cells.append(code)
    nb.metadata["execution"] = {"timing": "preserve"}
    original = copy.deepcopy(nb)
    result, header = normalize_notebook(nb, chapter_title="First Chapter")
    assert header == {"title": "First Chapter", "categories": ["testing"]}
    assert result.cells[0].source == "# First Chapter\n"
    assert result.cells[0].id == original.cells[0].id
    assert result.cells[1:] == original.cells[1:]
    assert result.metadata == original.metadata
    assert nb == original


def test_existing_h1_and_body_are_retained_exactly():
    nb = notebook("---\ntitle: First Chapter\n---\n\n# First Chapter\n\nAuthored body", "```python\n# A code comment\n```\n")
    out, _ = normalize_notebook(nb, chapter_title="First Chapter")
    assert out.cells[0].source == "\n# First Chapter\n\nAuthored body"
    assert out.cells[1] == nb.cells[1]
    assert h1_titles(out) == ["First Chapter"]


@pytest.mark.parametrize("body", ["# Wrong", "# First Chapter\n\n# Second"])
def test_conflicting_h1_fails_without_mutation(body):
    nb = notebook(body)
    original = copy.deepcopy(nb)
    with pytest.raises(ValueError, match="chapter H1"):
        normalize_notebook(nb, chapter_title="First Chapter")
    assert nb == original


def test_conflicting_frontmatter_and_catalog_is_not_silently_resolved():
    with pytest.raises(ValueError, match="conflicts with catalog"):
        normalize_notebook(notebook("---\ntitle: Other\n---\nBody"), chapter_title="First Chapter")


def test_h1_parser_ignores_fences_code_cells_and_outputs():
    nb = notebook("```markdown\n# Fake heading\n```\n\nFull *Title*\n=========\n")
    nb.cells.append(nbformat.v4.new_code_cell("# Another fake", outputs=[nbformat.v4.new_output("stream", name="stdout", text="# Output fake")]))
    assert h1_titles(nb) == ["Full Title"]


def test_horizontal_rule_and_cell_options_are_not_document_yaml():
    source = "---\nordinary prose\n---\n\n# Body"
    assert document_header(source) == ({}, source)
    cell_options = "#| echo: false\nprint('x')"
    assert document_header(cell_options) == ({}, cell_options)
    with pytest.raises(Exception, match="duplicate"):
        document_header("---\ntitle: One\ntitle: Two\n---\n")


def test_gallery_extracts_order_and_reports_prose_and_placeholders():
    nb = notebook('---\ntitle: Personal\n---\n\nIntro remains.\n\n![Caption](img/one.jpg)\n\n## Outdoors\n\n![](https://placehold.co/photo)\n\n<img src="img/two.jpg" alt="Second caption">')
    photos, prose = extract_photos(nb)
    assert photos == [{"path": "img/one.jpg", "caption": "Caption"}, {"path": "https://placehold.co/photo", "caption": ""}, {"path": "img/two.jpg", "caption": "Second caption"}]
    assert "Intro remains." in prose[0]["source"]
    assert "## Outdoors" in prose[0]["source"]
    assert "title: Personal" not in prose[0]["source"]


def test_qmd_supported_conversion_preserves_body_without_source_write(tmp_path):
    path = tmp_path / "project.qmd"
    source = "---\ntitle: Project\npage-layout: article\n---\n\n## Body\n\nAuthored text.\n"
    path.write_text(source)
    nb = read_source_notebook(path)
    nbformat.validate(nb)
    assert nb.nbformat_minor >= 5
    out, metadata = normalize_notebook(nb)
    assert "Authored text." in "\n".join(cell.source for cell in out.cells)
    assert metadata["title"] == "Project"
    assert path.read_text() == source
    assert all(cell.id for cell in out.cells)


def test_prepare_has_no_writes_and_preserves_ids_routes_resume_and_toc(tmp_path):
    legacy_repo(tmp_path)
    before = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    result = Migration(tmp_path).prepare()
    after = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after
    assert result["report"]["ready"]
    catalog = load_yaml(result["files"]["backend/data/catalog.yaml"].decode())
    chapter = catalog["artifacts"][1]
    assert chapter["id"] == "course/demo/01-first"
    assert chapter["route"] == "nb/courses/demo/01-first.ipynb"
    assert chapter["toc_title"] == "01. First"
    assert chapter["section"] == "foundations"
    assert chapter["lifecycle"] == "draft"
    course = load_yaml(result["files"]["backend/data/courses/demo.yaml"].decode())
    assert course["actualized"] == {"summary": "Checked earlier work"}
    assert course["toc"] == [{"id": "foundations", "title": "Foundations", "chapters": [chapter["id"]]}]
    assert course["planned"]["chapters"] == [{"chapter_id": chapter["id"], "section": "foundations", "summary": "Introduce the first topic"}]
    profile = load_yaml(result["files"]["backend/data/profile.yaml"].decode())
    assert profile["employment"][0]["bullets"] == ["Fact preserved"]
    assert result["report"]["presentation_exceptions"][0]["field"] == "toc"


def test_explicit_gallery_decision_preserves_body_in_personal_notebook(tmp_path):
    legacy_repo(tmp_path)
    target = tmp_path / "nb/photos/photos.ipynb"
    target.parent.mkdir(parents=True)
    nbformat.write(notebook("---\ntitle: Personal\n---\n\nAuthored intro\n\n![](https://placehold.co/photo)"), target)
    original = read_notebook(target)
    result = Migration(tmp_path, preserve_gallery_as_personal=True).prepare()
    assert result["report"]["ready"]
    personal = next(item for item in result["report"]["artifacts"] if item["kind"] == "personal")
    gallery = next(item for item in result["report"]["artifacts"] if item["kind"] == "gallery")
    normalized = nbformat.reads(result["files"][personal["path"]].decode(), as_version=nbformat.NO_CONVERT)
    assert normalized.cells[0].source == document_header(original.cells[0].source)[1]
    assert normalized.cells[0].id == original.cells[0].id
    assert personal["route"] == "nb/personal/photos-notes.ipynb"
    assert personal["visibility"] == "private"
    assert gallery["lifecycle"] == "planned"
    assert gallery["route"] == "nb/photos/photos.ipynb"
    assert load_yaml(result["files"]["backend/data/photos.yaml"].decode())["photos"] == []


def test_reviewed_historical_figures_are_copied_with_original_caption_and_mapping(tmp_path):
    legacy_repo(tmp_path)
    catalog = load_yaml((tmp_path / "knowledge/catalog.yaml").read_text())
    captions = []
    for name in ("autocode", "change-planner", "ml-platform"):
        source = f"nb/portfolio/{name}.qmd"
        catalog["artifacts"].append({"id": f"portfolio/{name}", "kind": "portfolio", "title": name, "path": source, "visibility": "public", "lifecycle": "published", "relations": [], "summary": f"Historical {name}"})
        target = tmp_path / source
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"---\ntitle: {name}\n---\n\nCurrent writeup remains.")
        archive = tmp_path / f"archive/2026-09-30/projects/{name}"
        archive.mkdir(parents=True)
        figure = tmp_path / f"archive/2026-09-30/nb/portfolio/img/{name}-flow.svg"
        figure.parent.mkdir(parents=True, exist_ok=True)
        figure.write_text(f"<svg><title>{name}</title></svg>")
        captions.append(f"![Original {name} caption.](img/{name}-flow.svg)")
    write_yaml(tmp_path, "knowledge/catalog.yaml", catalog)
    nbformat.write(notebook("\n\n".join(captions)), tmp_path / "archive/2026-09-30/nb/portfolio/portfolio.ipynb")
    assert len(Migration(tmp_path).inventory()["blockers"]) == 3
    result = Migration(tmp_path, reviewed_portfolio_figures=True).prepare()
    assert result["report"]["ready"]
    entries = load_yaml(result["files"]["backend/data/portfolio.yaml"].decode())["entries"]
    for entry in entries:
        name = entry["project_path"].rsplit("/", 1)[-1]
        assert entry["project_path"] == f"archive/2026-09-30/projects/{name}"
        assert not {"project_name", "project_source", "archive_date"}.intersection(entry)
        assert entry["figure_caption"] == f"Original {name} caption."
        assert entry["abstract"] == f"Historical {name}"
        assert result["files"][entry["figure_path"]] == (tmp_path / f"archive/2026-09-30/nb/portfolio/img/{name}-flow.svg").read_bytes()
        assert "Current writeup remains." in result["files"][entry["notebook_path"]].decode()
    assert not (tmp_path / "projects").exists()


def test_title_conflict_requires_exact_explicit_choice(tmp_path):
    legacy_repo(tmp_path)
    catalog = load_yaml((tmp_path / "knowledge/catalog.yaml").read_text())
    catalog["artifacts"].append({"id": "post/example", "kind": "post", "title": "Catalog title", "path": "nb/posts/example.ipynb", "visibility": "public", "lifecycle": "published", "relations": []})
    write_yaml(tmp_path, "knowledge/catalog.yaml", catalog)
    source = tmp_path / "nb/posts/example.ipynb"
    source.parent.mkdir(parents=True)
    nbformat.write(notebook("---\ntitle: Header title\n---\n\nBody stays."), source)
    assert not Migration(tmp_path).inventory()["ready"]
    assert not Migration(tmp_path, title_choices={"post/example": "Invented title"}).inventory()["ready"]
    result = Migration(tmp_path, title_choices={"post/example": "Header title"}).prepare()
    assert result["report"]["ready"]
    assert result["report"]["artifacts"][-1]["title"] == "Header title"
    assert result["report"]["warnings"][-1]["catalog_title"] == "Catalog title"
    assert read_notebook(source).cells[0].source.startswith("---\n")


def test_cover_and_sibling_assets_are_copied_and_references_preserved(tmp_path):
    legacy_repo(tmp_path)
    cover = tmp_path / "nb/courses/demo/img/cover.svg"
    cover.parent.mkdir(parents=True)
    cover.write_text("<svg><title>Original cover</title></svg>")
    appendix = tmp_path / "nb/courses/demo/appendix.md"
    appendix.write_text("Authored included appendix\n")
    source = tmp_path / "nb/courses/demo/index.ipynb"
    nbformat.write(notebook("---\ntitle: Demo\nimage: img/cover.svg\n---\n\n![Body caption](img/cover.svg)\n\n{{< include appendix.md >}}"), source)
    result = Migration(tmp_path).prepare()
    assert result["report"]["ready"]
    course = result["report"]["artifacts"][0]
    assert course["cover"] == "content/notebooks/courses/demo/img/cover.svg"
    assert result["files"][course["cover"]] == cover.read_bytes()
    assert result["files"]["content/notebooks/courses/demo/appendix.md"] == appendix.read_bytes()
    out = nbformat.reads(result["files"]["content/notebooks/courses/demo/index.ipynb"].decode(), as_version=4)
    assert "![Body caption](img/cover.svg)" in out.cells[0].source
    assert "{{< include appendix.md >}}" in out.cells[0].source
    assert len(result["report"]["assets"]) == 2
