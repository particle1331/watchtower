"""Saved plans have a read-only Markdown reader, independent of notebooks."""

import re

import pytest
from fastapi.testclient import TestClient
from test_api import author_workspace

from watchtower.api import create_app
from watchtower.api.cms_markdown import render_plan_markdown
from watchtower.services.content import ContentService


@pytest.fixture
def author(tmp_path):
    return ContentService(author_workspace(tmp_path))


@pytest.mark.parametrize("kind", ["post", "portfolio", "chapter", "course", "personal"])
def test_planned_editors_offer_reader_before_copy_source_and_hide_it_after_start(author, kind):
    identifier = f"{kind}/idea" if kind != "chapter" else "course/demo/idea"
    if kind == "chapter":
        author.create({"id": "course/demo", "kind": "course", "title": "Demo", "path": "content/notebooks/courses/demo"})
        author.start("course/demo")
    data = {"id": identifier, "kind": kind, "title": "Idea"}
    if kind == "course":
        data.update(path="content/notebooks/courses/idea", contract={"planned": {"description": "Saved **description**."}})
    elif kind == "chapter":
        data.update(path="content/notebooks/courses/demo/idea.ipynb", parent="course/demo", toc_title="Idea", section="main", plan={"content": "Saved **content**."})
    elif kind == "portfolio":
        data["detail"] = {"notebook_path": "content/notebooks/portfolio/idea.ipynb", "planned": {"content": "Saved **content**."}}
    else:
        data.update(path=f"content/notebooks/{'posts' if kind == 'post' else 'personal'}/idea.ipynb", planned={"content": "Saved **content**."})
    author.create(data)
    before = author.inspect(identifier)
    with TestClient(create_app(author.root)) as client:
        editor = client.get(f"/cms/artifact/{identifier}")
        tools = re.search(r'<div class="source-tools">(.*?)</div>', editor.text, re.S)[1]
        assert 'class="button plan-button"' in tools
        if before["source_path"]:
            assert tools.index("View plan") < tools.index("Copy source path")
        assert "Edit in VS Code" not in tools
        reader = client.get(f"/cms/plan/{identifier}")
        assert reader.status_code == 200, reader.text
        assert "<strong>" in reader.text
        assert 'href="/cms/courses/idea#course-brief"' in reader.text if kind == "course" else f'href="/cms/artifact/{identifier}"' in reader.text
        assert author.inspect(identifier)["revision"] == before["revision"]
        assert not author.inspect(identifier)["has_source"]
        author.start(identifier)
        editor = client.get(f"/cms/artifact/{identifier}")
        assert "data-plan-open" not in editor.text
        if kind != "course":
            assert "Edit in VS Code ↗" in editor.text
        assert client.get(f"/cms/plan/{identifier}").status_code == 404


def test_reader_renders_saved_sections_math_and_markdown_without_writes(author):
    author.create_post("idea", {"title": "Plan <title>", "description": "Public summary only", "planned": {
        "introduction": "Why **typesetting** matters with $\\alpha_i$.",
        "content": "## Example\n\n- One\n- Two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> A quotation\n\n```python\nx = '$not_math$'\n```\n\n$$\n\\frac{a_b}{c^2} < 1\n$$",
        "evidence": "A [reference](https://example.com).",
    }})
    before = author.inspect("post/idea")
    with TestClient(create_app(author.root)) as client:
        reader = client.get("/cms/plan/post/idea", headers={"HX-Request": "true"})
        assert reader.status_code == 200
        assert "<!doctype" not in reader.text
        assert "Plan &lt;title&gt;" in reader.text
        assert "Public summary only" not in reader.text
        assert reader.text.index("The problem") < reader.text.index("Planned content") < reader.text.index("Planned evidence")
        for tag in ["<strong>", "<ul>", "<table>", "<blockquote>", '<code class="language-python">', '<span class="math inline">', '<div class="math block">']:
            assert tag in reader.text
        assert "\\frac{a_b}{c^2} &lt; 1" in reader.text
        assert "<form" not in reader.text
        assert author.inspect("post/idea") == before


def test_partial_and_empty_plans_are_readable_and_unknown_or_unsupported_entries_are_rejected(author):
    author.create_post("empty", {"title": "Empty"})
    author.create_post("partial", {"title": "Partial", "planned": {"evidence": "Check results."}})
    author.create({"id": "gallery/photos", "kind": "gallery", "title": "Personal", "path": "backend/data/photos.yaml"})
    with TestClient(create_app(author.root)) as client:
        assert "No plan text yet" in client.get("/cms/plan/post/empty").text
        partial = client.get("/cms/plan/post/partial").text
        assert "Planned evidence" in partial and "Check results." in partial
        assert "The problem" not in partial and "Planned content" not in partial
        assert client.get("/cms/plan/post/missing").status_code == 404
        assert client.get("/cms/plan/gallery/photos").status_code == 404


def test_course_plan_lists_render_as_items_without_child_plans_or_notes(author):
    author.create({"id": "course/demo", "kind": "course", "title": "Demo", "path": "content/notebooks/courses/demo", "internal_notes": "Private execution notes", "contract": {"planned": {
        "description": "Course text.", "requirements": "Python\nA laptop", "prerequisites": "Algebra\nBasic coding", "references": "[A source](https://example.com)\nA book",
    }}})
    author.create({"id": "course/demo/first", "kind": "chapter", "title": "First", "toc_title": "First", "path": "content/notebooks/courses/demo/first.ipynb", "parent": "course/demo", "section": "main", "plan": {"content": "Child plan text"}})
    with TestClient(create_app(author.root)) as client:
        page = client.get("/cms/plan/course/demo", headers={"HX-Request": "true"})
        assert page.status_code == 200
        assert "<li>Python</li>" in page.text and "<li>A laptop</li>" in page.text
        assert "<li>Algebra</li>" in page.text
        assert '<li><a href="https://example.com">A source</a></li>' in page.text
        assert "Child plan text" not in page.text and "Private execution notes" not in page.text


def test_plan_markdown_escapes_html_unsafe_urls_and_math_but_keeps_code_literal():
    source = '<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))\n\n![unsafe](javascript:alert(1))\n\n$<img src=x onerror=alert(1)>$\n\n`$literal$`\n\n```\n$$code$$\n```'
    rendered = render_plan_markdown(source, "safe")
    assert "<script>" not in rendered and "<img" not in rendered
    assert 'href="javascript:' not in rendered and 'src="javascript:' not in rendered
    assert '&lt;script&gt;' in rendered and '&lt;img' in rendered
    assert '<code>$literal$</code>' in rendered and '<code>$$code$$' in rendered
    assert rendered.count('class="math') == 1
