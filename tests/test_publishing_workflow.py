"""Real installed notebook environment -> saved figure -> Quarto publication."""
import re
import shutil
from pathlib import Path

import nbformat
import pytest
from test_content_service import content_service as content_service

from watchtower import execute, notebook
from watchtower.services.build import BuildService


@pytest.mark.skipif(not shutil.which("quarto") or not shutil.which("xelatex"), reason="real publishing check requires Quarto and XeLaTeX")
def test_real_create_execute_preview_publish_workflow(content_service, monkeypatch):
    service = content_service
    monkeypatch.chdir(service.root)
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    for directory in ("assets", "templates"):
        shutil.copytree(frontend / directory, service.root / "frontend" / directory)
    service.create({"id": "post/figure", "kind": "post", "title": "Stored figure", "path": "content/notebooks/posts/figure.ipynb", "planned": {"content": "## Figure check\n\nDraw a figure with the installed notebook helpers."}, "tags": ["Verification"]})
    service.start("post/figure")
    notebook.append_cell("post/figure", source="#| echo: false\n#| label: fig-stored\n#| fig-cap: 'A stored figure.'\nfrom watchtower.core import Plot, Panel, set_format, set_seed\nimport matplotlib.pyplot as plt\nset_format('svg')\nplot = Plot()\nplt.plot([0, 1], [0, 1])\nplt.show()", cell_type="code")
    result = execute.run_notebook("post/figure")
    assert result["errors"] == []
    source = service.root / "content/notebooks/posts/figure.ipynb"
    authored = source.read_bytes()
    saved = nbformat.read(source, as_version=4)
    assert any("image/svg+xml" in output.get("data", {}) for output in saved.cells[-1].outputs)
    service.create({"id": "gallery/photos", "kind": "gallery", "title": "Personal", "path": "content/data/photos.yaml"})
    images = service.root / "content/assets/photos"
    images.mkdir(parents=True)
    for name in ("published", "draft"):
        (images / f"{name}.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="gray"/></svg>')
    service.update_gallery({"version": 1, "photos": [{"heading": f"{name.title()} photo", "path": f"content/assets/photos/{name}.svg", "caption": f"{name.title()} caption", "lifecycle": name, "width": "80%" if name == "published" else "50%"} for name in ("published", "draft")]})
    service.create({"id": "course/example", "kind": "course", "title": "Example course", "path": "content/notebooks/courses/example", "contract": {"purpose": "Teach", "audience": "Learners"}})
    service.start("course/example")
    service.create({"id": "course/example/01", "kind": "chapter", "title": "Chapter", "toc_title": "01. Chapter", "section": "main", "parent": "course/example", "path": "content/notebooks/courses/example/01.ipynb", "planned_content": "Topic", "planned_lab_and_evidence": "Check"})
    service.start("course/example/01")
    builds = BuildService(service.root)
    preview = builds.build("preview")
    assert preview["status"] == "succeeded", preview["error"]
    assert (Path(preview["output_location"]) / "nb/posts/figure.html").exists()
    gallery = (Path(preview["output_location"]) / "gallery.html").read_text()
    assert 'id="published-photo"' in gallery and "<h2" in gallery
    assert 'id="draft-photo"' in gallery
    assert "state:   draft" in gallery
    assert 'aria-label="Publication status"' in gallery
    assert "callout-caution" not in gallery
    assert "next:    Set Published in CMS" in gallery
    assert "callout-note" not in gallery
    for route in ["gallery.html", "personal.html"]:
        photo_page = (Path(preview["output_location"]) / route).read_text()
        assert 'id="TOC"' in photo_page
        toc = photo_page.split('<nav id="TOC"', 1)[1].split('</nav>', 1)[0]
        assert 'href="#published-photo"' in toc
        assert 'href="#draft-photo"' in toc
        image = re.search(r'<img[^>]*src="[^"]*photos/published.svg"[^>]*>', photo_page).group(0)
        assert re.search(r'width:\s*80(?:\.0+)?%', image), image
        image = re.search(r'<img[^>]*src="[^"]*photos/draft.svg"[^>]*>', photo_page).group(0)
        assert re.search(r'width:\s*50(?:\.0+)?%', image), image
    for route in ["nb/posts/figure.html", "nb/courses/example/index.html", "nb/courses/example/01.html"]:
        draft_page = (Path(preview["output_location"]) / route).read_text()
        assert 'id="quarto-draft-alert"' not in draft_page
        assert draft_page.count('aria-label="Publication status"') == 1
        assert "Review content, then publish in CMS" in draft_page
        assert "callout-note" not in draft_page
    course_page = (Path(preview["output_location"]) / "nb/courses/example/index.html").read_text()
    sidebar = course_page.split('<nav id="quarto-sidebar"', 1)[1].split('</nav>', 1)[0]
    assert sidebar.count('class="draft-badge"') == 2
    cards = (Path(preview["output_location"]) / "courses.html").read_text()
    assert 'class="draft-badge"' in cards
    assert 'quarto-grid-item card h-100 card-left' in cards
    assert 'nb/courses/example/index.html' in cards
    assert (Path(preview["output_location"]) / "assets/photos/draft.svg").exists()
    service.publish("post/figure")
    production = builds.build("production")
    assert production["status"] == "succeeded", production["error"]
    page = (Path(production["output_location"]) / "nb/posts/figure.html").read_text()
    assert "A stored figure." in page
    assert "plt.plot" not in page
    gallery = (Path(production["output_location"]) / "gallery.html").read_text()
    assert 'id="published-photo"' in gallery and "<h2" in gallery
    assert "Draft photo" not in gallery
    assert 'id="TOC"' in gallery
    toc = gallery.split('<nav id="TOC"', 1)[1].split('</nav>', 1)[0]
    assert 'href="#published-photo"' in toc
    assert 'href="#draft-photo"' not in toc
    image = re.search(r'<img[^>]*src="[^"]*photos/published.svg"[^>]*>', gallery).group(0)
    assert re.search(r'width:\s*80(?:\.0+)?%', image), image
    assert not (Path(production["output_location"]) / "assets/photos/draft.svg").exists()
    assert not (Path(production["output_location"]) / "nb/courses/example/index.html").exists()
    assert not (Path(production["output_location"]) / "nb/courses/example/01.html").exists()
    assert source.read_bytes() == authored
    service.draft("post/figure")
    removed = builds.generate("production")
    assert not (removed / "nb/posts/figure.ipynb").exists()
