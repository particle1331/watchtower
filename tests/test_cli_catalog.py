"""CLI contracts for catalog-backed discovery and explicit archive access."""

import json
from pathlib import Path

import nbformat
import yaml
from typer.testing import CliRunner

from watchtower import cli

runner = CliRunner()


def run(*args: str):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_course_cli_context_navigation_and_notebook_id(repo):
    run("new", "course", "signals", "Signals")
    run("new", "section", "signals", "Next Part")
    run("new", "chapter", "signals", "02-filtering", "--title", "Filtering", "--section", "Next Part")
    course = Path("nb/courses/signals/course.yaml")
    data = yaml.safe_load(course.read_text())
    data["purpose"] = "Teach signal filtering"
    data["planned"]["summary"] = "Build a filter"
    data["actualized"]["summary"] = "No completed chapters yet"
    course.write_text(yaml.safe_dump(data, sort_keys=False))

    assert "_course-context.md" in run("render-context")
    assert "knowledge catalog valid" in run("validate")
    course_map = json.loads(run("map"))
    assert course_map["courses"][0]["home"] == "nb/courses/signals/index.ipynb"
    assert course_map["courses"][0]["chapters"] == [
        "nb/courses/signals/01-introduction.ipynb",
        "nb/courses/signals/02-filtering.ipynb",
    ]
    assert "nb/courses/signals/index.ipynb" in run("ls", "courses")
    assert "[cell 0]" in run("find", "TODO: lesson content")

    context = json.loads(run("context", "course/signals/01-introduction"))
    assert context["course"]["planned"]["summary"] == "Build a filter"
    assert context["course"]["actualized"]["summary"] == "No completed chapters yet"
    assert context["reading_paths"]["course_home"] == "nb/courses/signals/index.ipynb"
    assert json.loads(run("context", "nb/courses/signals/01-introduction.ipynb"))["artifact"]["id"] == "course/signals/01-introduction"
    assert "TODO: lesson content" in run("cat", "course/signals/01-introduction")
    run("append-cell", "course/signals/01-introduction", "--content", "draft result")
    run("edit-cell", "course/signals/01-introduction", "--index", "1", "--content", "checked result")
    assert "checked result" in run("cat", "course/signals/01-introduction", "--index", "1")


def test_cli_register_validate_and_site_visibility(repo):
    portfolio = Path("nb/portfolio")
    portfolio.mkdir(parents=True)
    (portfolio / "public.qmd").write_text("# Public\n", encoding="utf-8")
    (portfolio / "private.qmd").write_text("# Private\n", encoding="utf-8")
    run("register", "portfolio", "nb/portfolio/public.qmd", "Public", "--summary", "Public work", "--lifecycle", "published")
    run("register", "portfolio", "nb/portfolio/private.qmd", "Private", "--summary", "Private work", "--visibility", "private", "--lifecycle", "published")
    run("validate")
    run("sync-site")
    config = yaml.safe_load(Path("_quarto.yml").read_text())
    assert "nb/portfolio/public.qmd" in config["project"]["render"]
    assert "nb/portfolio/private.qmd" not in config["project"]["render"]
    assert "portfolio.qmd" in config["project"]["render"]
    assert {"href": "portfolio.qmd", "text": "portfolio"} in config["website"]["navbar"]["left"]
    assert "nb/portfolio/public.qmd" in run("ls", "portfolio")

    (portfolio / "orphan.qmd").write_text("# Orphan\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["validate"])
    assert result.exit_code == 1
    assert "unregistered active path: nb/portfolio/orphan.qmd" in result.output


def test_register_chapter_derives_id_from_parent_and_source(repo):
    run("new", "course", "signals", "Signals")
    source = Path("nb/courses/signals/03-extra.ipynb")
    nbformat.write(nbformat.v4.new_notebook(), source)
    missing_parent = runner.invoke(cli.app, ["register", "chapter", str(source), "Extra"])
    assert missing_parent.exit_code == 2
    assert "requires --parent" in missing_parent.output
    run("register", "chapter", str(source), "Extra", "--parent", "course/signals")
    artifact = json.loads(run("context", "course/signals/03-extra"))["artifact"]
    assert artifact["path"] == str(source)
    assert artifact["parent"] == "course/signals"


def test_cli_scaffold_import_and_archive_are_separate(repo):
    run("new", "post", "active", "--title", "Active")
    source = Path("incoming.ipynb")
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("Imported source")]), source)
    run("import", str(source), "posts", "imported")
    run("new", "course", "signals", "Signals")
    run("import", str(source), "courses", "signals", "02-external")
    assert [a["id"] for a in json.loads(run("map"))["posts"]] == ["post/active", "post/imported"]
    assert "nb/courses/signals/02-external.ipynb" in json.loads(run("map"))["courses"][0]["chapters"]

    archived = Path("archive/2026-09-30/nb/posts/old.ipynb")
    archived.parent.mkdir(parents=True)
    nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("Archived marker")]), archived)
    assert "no sources match" in run("find", "Archived marker")
    assert "[cell 0]" in run("find", "Archived marker", "--archive")
    assert str(archived) in run("ls", "posts", "--archive")
    assert str(archived) in json.loads(run("map", "--archive"))["posts"]
    assert "Archived marker" in run("cat", str(archived))
