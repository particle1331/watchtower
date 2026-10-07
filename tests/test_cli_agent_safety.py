"""Regressions for stale agent decisions, execution concurrency and CLI plans."""
import json
import threading
from pathlib import Path

import nbformat
import pytest
from test_api import author_workspace
from typer.testing import CliRunner

from watchtower import execute, notebook
from watchtower.api import create_app
from watchtower.cli import app
from watchtower.services.content import ContentService
from watchtower.services.kanban import KanbanService
from watchtower.services.workspace import ServiceError, digest

runner = CliRunner()


@pytest.fixture
def agent_workspace(tmp_path, monkeypatch):
    root = author_workspace(tmp_path)
    monkeypatch.chdir(root)
    content = ContentService(root)
    content.create({"id": "post/example", "kind": "post", "title": "Example", "path": "content/notebooks/posts/example.ipynb", "planned": {}})
    content.start("post/example")
    notebook.append_cell("post/example", "print('original')", cell_type="code")
    return content, KanbanService(root)


def invoke(arguments):
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, (result.output, result.exception)
    return result.output


def token():
    return invoke(["cat", "post/example", "--index", "0", "--with-revision"]).splitlines()[0].removeprefix("> source-revision: ")


@pytest.mark.parametrize("arguments", [
    ["edit-cell", "post/example", "--index", "0", "--content", "Stale body"],
    ["append-cell", "post/example", "--content", "Stale addition"],
    ["insert-cell", "post/example", "--after", "0", "--content", "Stale insertion"],
    ["remove-cell", "post/example", "--index", "0"],
    ["tag", "post/example", "--index", "0", "--add", "stale"],
    ["clear-outputs", "post/example", "--index", "1"],
    ["run", "post/example"],
])
def test_stale_notebook_token_rejects_every_write_before_mutation(agent_workspace, arguments, monkeypatch):
    content, _ = agent_workspace
    stale = token()
    notebook.insert_cell("post/example", "Concurrent insertion", before=0)
    source = content.root / "content/notebooks/posts/example.ipynb"
    saved = source.read_bytes()
    monkeypatch.setattr(execute, "_execute", lambda *a, **k: pytest.fail("stale run launched execution"))
    failed = runner.invoke(app, [*arguments, "--expected-revision", stale])
    assert isinstance(failed.exception, ServiceError)
    assert failed.exception.status == 412
    assert source.read_bytes() == saved


def test_notebook_token_matches_displayed_source_and_ignores_other_content(agent_workspace):
    content, board = agent_workspace
    current = token()
    source = content.root / "content/notebooks/posts/example.ipynb"
    assert current == "notebook:" + digest(source.read_bytes())
    board.create({"title": "Unrelated task"})
    invoke(["edit-cell", "post/example", "--index", "0", "--content", "Fresh body", "--expected-revision", current])
    assert "Fresh body" in invoke(["cat", "post/example", "--index", "0"])
    assert token() != current
    notebook.edit_cell(name="post/example", source="Keyword update", index=0, expected_revision=token())
    assert "Keyword update" in notebook.cat_notebook("post/example", index=0)


def test_execution_releases_gate_and_survives_unrelated_board_write(agent_workspace, monkeypatch):
    _, board = agent_workspace
    card = board.create({"title": "Run example"})["card"]
    completed = threading.Event()
    errors = []

    def board_worker():
        try:
            board.update(card["id"], {"column": "in-progress"}, board.read()["board_revision"])
        except Exception as error:
            errors.append(error)
        finally:
            completed.set()

    thread = threading.Thread(target=board_worker, daemon=True)

    def fake_execute(nb, **kwargs):
        thread.start()
        assert completed.wait(3), "Kanban is blocked by the execution lock"
        nb.cells[1].outputs = [nbformat.v4.new_output("stream", name="stdout", text="Finished\n")]

    monkeypatch.setattr(execute, "_execute", fake_execute)
    try:
        result = execute.run_notebook("post/example")
    finally:
        thread.join(3)
    assert not errors
    assert result["ran"] == 1
    assert "Finished" in invoke(["cat", "post/example", "--index", "1", "--with-outputs"])
    assert board.read()["cards"][0]["column"] == "in-progress"


@pytest.mark.parametrize("index", [None, 1])
@pytest.mark.parametrize("change", ["edit", "delete"])
def test_execution_conflict_retains_results_without_overwriting_source(agent_workspace, monkeypatch, index, change):
    content, _ = agent_workspace
    source = content.root / "content/notebooks/posts/example.ipynb"

    def fake_execute(nb, **kwargs):
        nb.cells[1].outputs = [nbformat.v4.new_output("stream", name="stdout", text="Retained result\n")]
        if change == "edit":
            notebook.edit_cell("post/example", "print('newer')", index=1)
        else:
            content.delete("post/example")

    monkeypatch.setattr(execute, "_execute", fake_execute)
    with pytest.raises(ServiceError) as conflict:
        execute.run_notebook("post/example", index=index)
    assert conflict.value.status == 412
    retained = Path(conflict.value.paths[-1])
    assert retained.is_relative_to(content.root / ".tmp/execution-conflicts")
    result = nbformat.read(retained, as_version=4)
    assert result.cells[1].source == "print('original')"
    assert result.cells[1].outputs[0].text == "Retained result\n"
    if change == "edit":
        assert "newer" in notebook.cat_notebook("post/example", index=1)
        assert "Retained result" not in notebook.cat_notebook("post/example", index=1, with_outputs=True)
    else:
        assert not source.exists()


@pytest.mark.parametrize("transport", ["data", "batch"])
def test_whole_board_reset_preserves_high_water_mark(agent_workspace, transport):
    content, board = agent_workspace
    first = board.create({"title": "First"})["card"]
    board.remove(first["id"])
    board.create({"title": "Second"})
    payload = {"version": 1, "next_number": 1, "cards": []}
    if transport == "data":
        saved = content.update_data("kanban", payload)
        assert saved["data"]["next_number"] == 3
    else:
        saved = content.batch([], {"kanban": payload})
        assert saved["data"]["kanban"]["next_number"] == 3
    assert board.create({"title": "Third"})["card"]["ref"] == "card#3"


@pytest.mark.parametrize("transport", ["data", "batch"])
@pytest.mark.parametrize("patch", [{"ref": "card#100"}, {"id": "replacement"}])
def test_whole_board_cannot_reassign_existing_identity(agent_workspace, transport, patch):
    content, board = agent_workspace
    card = board.create({"title": "Stable card"})["card"]
    before = content.read_data("kanban")
    payload = {"version": 1, "cards": [{**card, **patch}]}
    with pytest.raises(ServiceError):
        if transport == "data":
            content.update_data("kanban", payload)
        else:
            content.batch([], {"kanban": payload})
    assert content.read_data("kanban") == before


def test_omitted_references_preserve_existing_identity(agent_workspace):
    content, board = agent_workspace
    card = board.create({"id": "stable", "title": "Stable card"})["card"]
    content.update_data("kanban", {"version": 1, "cards": [{"id": "stable", "title": "Updated card"}]})
    assert board.read()["cards"][0]["ref"] == card["ref"]
    assert board.create({"title": "Next"})["card"]["ref"] == "card#2"


def test_scoped_board_revision_survives_content_but_rejects_board_changes(agent_workspace):
    content, board = agent_workspace
    card = board.create({"title": "Unrelated wording"})["card"]
    read = board.read()
    notebook.edit_cell("post/example", "Changed independently", index=0)
    with pytest.raises(ServiceError) as workspace_conflict:
        board.update(card["ref"], {"column": "in-progress"}, read["revision"])
    assert workspace_conflict.value.status == 412
    moved = board.update(card["ref"], {"column": "in-progress"}, read["board_revision"])
    assert moved["board_revision"] != read["board_revision"]
    with pytest.raises(ServiceError) as board_conflict:
        board.remove(card["id"], read["board_revision"])
    assert board_conflict.value.status == 412
    assert content.inspect("post/example")["artifact"]["lifecycle"] == "draft"
    for identifier in (card["id"], card["ref"]):
        assert board.read(query=identifier)["cards"][0]["id"] == card["id"]


def test_http_accepts_scoped_kanban_revision(agent_workspace):
    from fastapi.testclient import TestClient
    content, board = agent_workspace
    token = board.read()["board_revision"]
    notebook.edit_cell("post/example", "Independent edit", index=0)
    with TestClient(create_app(content.root)) as client:
        created = client.post("/api/kanban", headers={"If-Match": token}, json={"title": "HTTP task"})
        assert created.status_code == 201
        assert created.json()["board_revision"].startswith("kanban:")
        assert client.post("/api/kanban", headers={"If-Match": token}, json={"title": "Stale"}).status_code == 412


def test_planning_flags_update_effective_chapter_and_course_plans(agent_workspace):
    content, _ = agent_workspace
    invoke(["new", "course", "example", "Example course"])
    invoke(["new", "chapter", "example", "one", "--planned-content", "Old content", "--planned-lab-and-evidence", "Old lab"])
    content.update("course/example/one", {"plan": {"summary": "Keep summary", "references": "Keep reference"}})
    invoke(["update", "course/example/one", "--planned-content", "New content", "--planned-lab-and-evidence", "New lab"])
    chapter = content.inspect("course/example/one")
    assert chapter["chapter_plan"]["content"] == "New content"
    assert chapter["chapter_plan"]["lab_and_evidence"] == "New lab"
    assert chapter["chapter_plan"]["summary"] == "Keep summary"
    assert chapter["artifact"]["planned"] == {}
    content.update("course/example", {"contract": {"purpose": "Purpose", "audience": "Audience", "planned": {"summary": "Old summary"}, "actualized": {"summary": "Checked evidence"}}})
    invoke(["update", "course/example", "--planned-content", "New course summary"])
    course = content.inspect("course/example")
    assert course["contract"]["planned"]["summary"] == "New course summary"
    assert course["contract"]["actualized"]["summary"] == "Checked evidence"
    content.start("course/example/one")
    assert "New content" in notebook.cat_notebook("course/example/one")
    assert "New content" in content.inspect("course/example/one")["build_brief"]


def test_plan_file_update_uses_same_sections_as_creation(agent_workspace):
    content, _ = agent_workspace
    invoke(["new", "course", "example", "Example"])
    invoke(["new", "chapter", "example", "one"])
    scratch = content.root / ".tmp"
    scratch.mkdir()
    (scratch / "chapter.md").write_text("## Planned content\n\nRevised content\n\n## Planned lab and evidence\n\nRevised lab")
    invoke(["update", "course/example/one", "--plan-file", ".tmp/chapter.md"])
    assert content.inspect("course/example/one")["chapter_plan"]["content"] == "Revised content"
    invoke(["new", "portfolio", "example", "--introduction", "Old intro", "--what-it-contains", "Old contents", "--scope-notes", "Keep scope"])
    (scratch / "portfolio.md").write_text("Revised intro\n\n## What it contains\n\nRevised contents")
    invoke(["update", "portfolio/example", "--plan-file", ".tmp/portfolio.md"])
    plan = content.inspect("portfolio/example")["detail"]["planned"]
    assert plan == {"introduction": "Revised intro", "what_it_contains": "Revised contents", "scope_notes": "Keep scope"}
    before = content.list()["revision"]
    failed = runner.invoke(app, ["update", "portfolio/example", "--planned-content", "Ambiguous text"])
    assert isinstance(failed.exception, ServiceError)
    assert content.list()["revision"] == before


@pytest.mark.parametrize("file_args", [["--file", ".tmp/batch.json"], [".tmp/batch.json"]])
def test_documented_and_legacy_batch_forms(agent_workspace, file_args):
    content, _ = agent_workspace
    scratch = content.root / ".tmp"
    scratch.mkdir()
    payload = {"updates": [{"id": "post/example", "patch": {"description": "Batch description"}}], "data": {}}
    (scratch / "batch.json").write_text(json.dumps(payload))
    invoke(["batch", *file_args, "--expected-revision", content.list()["revision"]])
    assert content.inspect("post/example")["artifact"]["description"] == "Batch description"


def test_conflicting_link_options_do_not_save(agent_workspace):
    _, board = agent_workspace
    card = board.create({"title": "Links", "artifact_ids": ["post/example"]})["card"]
    before = board.read()
    failed = runner.invoke(app, ["kanban", "update", card["ref"], "--link", "post/example", "--clear-links"])
    assert isinstance(failed.exception, ServiceError)
    assert board.read() == before
