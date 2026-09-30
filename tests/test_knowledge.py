"""The catalog controls active discovery and course context."""

from pathlib import Path

import nbformat
import pytest
import yaml

from watchtower import inspect, knowledge, scaffold


def test_course_contract_is_shared_by_context_and_render(repo):
    scaffold.new_course("signals", "Signals")
    course = Path("nb/courses/signals/course.yaml")
    data = yaml.safe_load(course.read_text())
    data["purpose"] = "Explain signals."
    data["audience"] = "Python readers"
    data["planned"]["summary"] = "Build a filter."
    data["actualized"]["summary"] = "The first exercise is checked."
    course.write_text(yaml.safe_dump(data, sort_keys=False))
    assert any("generated course include is stale" in error for error in knowledge.validate())
    knowledge.render_course_includes()

    result = knowledge.context("course/signals/01-introduction")
    assert result["course"]["planned"]["summary"] == "Build a filter."
    assert result["reading_paths"]["course_home"] == "nb/courses/signals/index.ipynb"
    assert "actualized work\n\nthe first exercise is checked." in (Path("nb/courses/signals") / knowledge.INCLUDE_NAME).read_text().lower()
    assert inspect.repo_map()["courses"][0]["chapters"] == ["nb/courses/signals/01-introduction.ipynb"]
    assert knowledge.validate() == []


def test_active_search_uses_registry_and_validation_finds_unregistered(repo):
    Path("nb/posts").mkdir(parents=True)
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell("unique planned source")])
    nbformat.write(notebook, "nb/posts/orphan.ipynb")
    assert inspect.find_in_src("unique planned source") == ""
    assert "unregistered active path: nb/posts/orphan.ipynb" in knowledge.validate()
    knowledge.add_artifact("post/orphan", "post", Path("nb/posts/orphan.ipynb"), "Orphan")
    assert "[cell 0]" in inspect.find_in_src("unique planned source")
    assert knowledge.validate() == []


def test_archive_search_is_explicit(repo):
    archive = knowledge.ARCHIVE_PATH / "nb/posts"
    archive.mkdir(parents=True)
    (archive / "source.md").write_text("archived signal\n")
    assert inspect.find_in_src("archived signal") == ""
    assert "source.md:1" in inspect.find_in_src("archived signal", archive=True)


def test_site_uses_only_public_published_catalog_entries(repo):
    Path("nb/posts").mkdir(parents=True)
    for name in ("ready", "draft", "private"):
        nbformat.write(nbformat.v4.new_notebook(), f"nb/posts/{name}.ipynb")
    knowledge.add_artifact("post/ready", "post", Path("nb/posts/ready.ipynb"), "Ready", lifecycle="published")
    knowledge.add_artifact("post/draft", "post", Path("nb/posts/draft.ipynb"), "Draft")
    knowledge.add_artifact("post/private", "post", Path("nb/posts/private.ipynb"), "Private", visibility="private", lifecycle="published")
    knowledge.sync_site()
    site = yaml.safe_load(Path("_quarto.yml").read_text())
    render = site["project"]["render"]
    assert "posts.qmd" in render
    assert "nb/posts/ready.ipynb" in render
    assert "nb/posts/draft.ipynb" not in render
    assert "nb/posts/private.ipynb" not in render
    assert "!archive/**" in render


def test_portfolio_summary_and_related_work_drive_home(repo):
    Path("nb/portfolio").mkdir(parents=True)
    Path("nb/portfolio/example.qmd").write_text("# Example\n")
    Path("nb/posts").mkdir(parents=True)
    nbformat.write(nbformat.v4.new_notebook(), "nb/posts/note.ipynb")
    nbformat.write(nbformat.v4.new_notebook(), "nb/posts/private.ipynb")
    knowledge.add_artifact("post/note", "post", Path("nb/posts/note.ipynb"), "A note", lifecycle="published")
    knowledge.add_artifact(
        "post/private", "post", Path("nb/posts/private.ipynb"), "Private note",
        visibility="private", lifecycle="published",
    )
    scaffold.new_course("signals", "Signals")
    artifacts = knowledge.load_catalog()
    for item in artifacts:
        if item["id"] in {"course/signals", "course/signals/01-introduction"}:
            item["lifecycle"] = "published"
    knowledge.save_catalog(artifacts)

    with pytest.raises(ValueError, match="portfolio summary is required"):
        knowledge.add_artifact("portfolio/example", "portfolio", Path("nb/portfolio/example.qmd"), "Example")
    knowledge.add_artifact(
        "portfolio/example", "portfolio", Path("nb/portfolio/example.qmd"), "Example",
        summary="A short account of the project.",
        relations=["post/note", "course/signals", "course/signals/01-introduction", "post/private"],
        lifecycle="published",
    )
    assert knowledge.validate() == []
    knowledge.sync_site()

    home = Path("portfolio.qmd").read_text()
    assert "A short account of the project." in home
    assert "[A note](nb/posts/note.ipynb)" in home
    assert "[Signals](nb/courses/signals/index.ipynb)" in home
    assert "[Introduction](nb/courses/signals/01-introduction.ipynb)" in home
    assert "Private note" not in home
    site = yaml.safe_load(Path("_quarto.yml").read_text())
    assert "portfolio.qmd" in site["project"]["render"]
    assert "nb/portfolio/example.qmd" in site["project"]["render"]

    artifacts = knowledge.load_catalog()
    portfolio = next(item for item in artifacts if item["id"] == "portfolio/example")
    portfolio["relations"].append("post/missing")
    knowledge.save_catalog(artifacts)
    assert "portfolio/example: unknown relation post/missing" in knowledge.validate()


def test_published_course_gets_grid_card_and_courses_navbar(repo):
    scaffold.new_course("ready", "Ready Course")
    scaffold.new_course("draft", "Draft Course")
    artifacts = knowledge.load_catalog()
    for item in artifacts:
        if item["id"] == "course/ready" or item["id"].startswith("course/ready/"):
            item["lifecycle"] = "published"
    knowledge.save_catalog(artifacts)

    knowledge.sync_site()

    site = yaml.safe_load(Path("_quarto.yml").read_text())
    render = site["project"]["render"]
    navbar = site["website"]["navbar"]["left"]
    listing = Path("courses.qmd").read_text()
    assert "courses.qmd" in render
    assert "nb/courses/ready/index.ipynb" in render
    assert "nb/courses/ready/01-introduction.ipynb" in render
    assert "nb/courses/draft/index.ipynb" not in render
    assert {"href": "courses.qmd", "text": "courses"} in navbar
    assert "type: grid" in listing
    assert '"nb/courses/ready/index.ipynb"' in listing
    assert "nb/courses/draft/index.ipynb" not in listing
