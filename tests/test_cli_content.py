"""CLI plan creation/import and the same services exercised by HTTP."""
import json

import nbformat
import pytest
from test_content_service import author_body
from test_content_service import content_service as content_service
from typer.testing import CliRunner

from watchtower.cli import app
from watchtower.services.workspace import ServiceError

runner = CliRunner()


def invoke(monkeypatch, service, arguments):
    monkeypatch.chdir(service.root)
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, (result.output, result.exception)
    return json.loads(result.output)


def test_register_project_derives_id_and_rejects_old_id_argument(content_service, monkeypatch):
    service = content_service
    monkeypatch.chdir(service.root)
    project = service.root / "projects/existing.v2"
    project.mkdir(parents=True)
    result = runner.invoke(app, ["register", "project", "projects/existing.v2", "Existing project"])
    assert result.exit_code == 0, (result.output, result.exception)
    assert service.inspect("project/existing.v2")["artifact"]["path"] == "projects/existing.v2"
    before = service.list()["revision"]
    result = runner.invoke(app, ["register", "project", "project/custom", "projects/existing.v2", "Custom"])
    assert result.exit_code == 2
    assert service.list()["revision"] == before


def test_cli_post_plan_file_tags_start_publish_draft(content_service, monkeypatch):
    service = content_service
    plan = service.root / ".tmp/post.md"
    plan.parent.mkdir()
    plan.write_text("## Outline\n\nInvestigate the question.")
    record = invoke(monkeypatch, service, ["new", "post", "article", "--plan-file", ".tmp/post.md", "--tag", " Test ", "--tag", "test"])
    assert record["artifact"]["lifecycle"] == "planned"
    assert record["artifact"]["tags"] == ["Test"]
    plan.unlink()
    invoke(monkeypatch, service, ["start", "post/article"])
    author_body(service, "post/article")
    invoke(monkeypatch, service, ["publish", "post/article"])
    invoke(monkeypatch, service, ["draft", "post/article"])
    assert service.inspect("post/article")["artifact"]["lifecycle"] == "draft"


def test_chapter_inline_and_file_plans_match(content_service, monkeypatch):
    service = content_service
    invoke(monkeypatch, service, ["new", "course", "example", "Example"])
    invoke(monkeypatch, service, ["new", "chapter", "example", "01", "--title", "One", "--toc-title", "01. One", "--planned-content", "Explain topic.", "--planned-lab-and-evidence", "Check result."])
    plan = service.root / ".tmp/chapter.md"
    plan.parent.mkdir()
    plan.write_text("## Outline\n\nExplain topic.\n\n## Practice and evidence\n\nCheck result.\n")
    invoke(monkeypatch, service, ["new", "chapter", "example", "02", "--title", "Two", "--plan-file", ".tmp/chapter.md"])
    plans = service.read_data("course/example")["data"]["planned"]["chapters"]
    assert plans[0]["content"] == plans[1]["content"]
    assert plans[0]["lab_and_evidence"] == plans[1]["lab_and_evidence"]
    assert not (service.root / "content/notebooks/courses/example/01.ipynb").exists()


def test_course_and_chapter_cli_do_not_accept_tags(content_service, monkeypatch):
    service = content_service
    course = invoke(monkeypatch, service, ['new', 'course', 'example', 'Example'])
    chapter = invoke(monkeypatch, service, ['new', 'chapter', 'example', '01', '--title', 'One'])
    assert 'tags' not in course['artifact'] and 'tags' not in chapter['artifact']
    before = service.list()['revision']
    for args in (['new', 'course', 'another', 'Another'], ['new', 'chapter', 'example', '02']):
        rejected = runner.invoke(app, [*args, '--tag', 'NLP'])
        assert rejected.exit_code == 2
        help_result = runner.invoke(app, [*args[:2], '--help'])
        assert '--tag' not in help_result.output
    for identifier in ('course/example', 'course/example/01'):
        for flag in ('--tag', '--add-tag', '--remove-tag'):
            rejected = runner.invoke(app, ['update', identifier, flag, 'NLP'])
            assert rejected.exit_code == 1
            assert isinstance(rejected.exception, ServiceError)
            assert 'do not support tags' in str(rejected.exception)
    assert service.list()['revision'] == before


def test_chapter_import_discards_document_labels_and_preserves_cell_tags(content_service, monkeypatch):
    service = content_service
    invoke(monkeypatch, service, ['new', 'course', 'example', 'Example'])
    source = service.root / '.tmp/chapter.ipynb'
    source.parent.mkdir()
    code = nbformat.v4.new_code_cell('print(2)', metadata={'tags': ['exercise']}, outputs=[nbformat.v4.new_output('stream', name='stdout', text='2\n')], execution_count=2)
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('---\ntitle: Imported chapter\ncategories: [original]\ntags: [NLP]\n---\n\nBody'), code]), source)
    result = invoke(monkeypatch, service, ['import', str(source), 'courses', 'example', 'imported'])
    assert 'tags' not in result['artifact'] and 'categories' not in result['artifact']
    notebook = nbformat.read(service.root / result['artifact']['path'], as_version=4)
    assert [cell for cell in notebook.cells if cell.cell_type == 'code'] == [code]
    assert notebook.cells[0].source.startswith('# Imported chapter')


@pytest.mark.parametrize("body", ["## Outline\n\nTopic\n\n## Outline\n\nDuplicate\n\n## Practice and evidence\n\nCheck"])
def test_chapter_bad_plan_never_partially_registers(content_service, monkeypatch, body):
    service = content_service
    invoke(monkeypatch, service, ["new", "course", "example", "Example"])
    plan = service.root / ".tmp/chapter.md"
    plan.parent.mkdir()
    plan.write_text(body)
    before = service.list()["revision"]
    result = runner.invoke(app, ["new", "chapter", "example", "01", "--plan-file", ".tmp/chapter.md"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ServiceError)
    assert service.list()["revision"] == before


def test_cli_import_preserves_outputs_and_frontmatter_becomes_metadata(content_service, monkeypatch):
    service = content_service
    source = service.root / ".tmp/external.ipynb"
    source.parent.mkdir()
    code = nbformat.v4.new_code_cell("#| echo: false\nprint(2)", outputs=[nbformat.v4.new_output("stream", name="stdout", text="2\n")], execution_count=2)
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('---\ntitle: Imported\ncategories: [original]\ntags: [Existing, ORIGINAL]\n---\n\nBody'), code]), source)
    result = invoke(monkeypatch, service, ["import", str(source), "posts", "imported"])
    assert result["artifact"]["lifecycle"] == "draft"
    assert result["artifact"]["title"] == "Imported"
    assert result["artifact"]["tags"] == ["Existing", "ORIGINAL"]
    assert "categories" not in result["artifact"]
    notebook = nbformat.read(service.root / result["artifact"]["path"], as_version=4)
    assert notebook.cells[1] == code
    assert notebook.cells[0].source == "\nBody"


def test_cli_stale_revision_is_not_retried(content_service, monkeypatch):
    service = content_service
    result = invoke(monkeypatch, service, ["new", "post", "article", "--planned-content", "Body"])
    invoke(monkeypatch, service, ["update", "post/article", "--description", "Saved"])
    failed = runner.invoke(app, ["update", "post/article", "--title", "Stale", "--expected-revision", result["revision"]])
    assert failed.exit_code == 1
    assert isinstance(failed.exception, ServiceError)
    assert failed.exception.status == 412


def test_migration_refuses_to_replace_active_content(content_service, monkeypatch):
    service = content_service
    monkeypatch.chdir(service.root)
    before = service.snapshot().revision
    result = runner.invoke(app, ["migrate", "--apply"])
    assert isinstance(result.exception, ServiceError)
    assert result.exception.code == "already_migrated"
    assert service.snapshot().revision == before
