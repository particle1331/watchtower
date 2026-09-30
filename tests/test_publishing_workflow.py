"""Real installed notebook environment -> saved figure -> Quarto publication."""
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
    service.update_gallery({"version": 1, "photos": [{"heading": f"{name.title()} photo", "path": f"content/assets/photos/{name}.svg", "caption": f"{name.title()} caption", "lifecycle": name} for name in ("published", "draft")]})
    builds = BuildService(service.root)
    preview = builds.build("preview")
    assert preview["status"] == "succeeded", preview["error"]
    assert (Path(preview["output_location"]) / "nb/posts/figure.html").exists()
    gallery = (Path(preview["output_location"]) / "gallery.html").read_text()
    assert 'id="published-photo"' in gallery and "<h2" in gallery
    assert "Draft photo" not in gallery
    assert not (Path(preview["output_location"]) / "assets/photos/draft.svg").exists()
    service.publish("post/figure")
    production = builds.build("production")
    assert production["status"] == "succeeded", production["error"]
    page = (Path(production["output_location"]) / "nb/posts/figure.html").read_text()
    assert "A stored figure." in page
    assert "plt.plot" not in page
    gallery = (Path(production["output_location"]) / "gallery.html").read_text()
    assert 'id="published-photo"' in gallery and "<h2" in gallery
    assert "Draft photo" not in gallery
    assert not (Path(production["output_location"]) / "assets/photos/draft.svg").exists()
    assert source.read_bytes() == authored
    service.draft("post/figure")
    removed = builds.generate("production")
    assert not (removed / "nb/posts/figure.ipynb").exists()
