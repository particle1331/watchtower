"""Tests for structured notebook output extraction."""

import base64

import nbformat
from typer.testing import CliRunner

from watchtower import cli, outputs

runner = CliRunner()


def _write_output_notebook(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    png = b"fake-png"
    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell("plot()")
    cell.outputs = [
        nbformat.NotebookNode(
            output_type="stream", name="stdout", text="done\n"
        ),
        nbformat.NotebookNode(
            output_type="display_data",
            data={
                "image/png": base64.b64encode(png).decode("ascii"),
                "text/plain": "<Figure>\n",
            },
            metadata={},
        ),
    ]
    nb.cells = [cell]
    nbformat.write(nb, path)
    return path, png


def test_get_cell_outputs_normalizes_text_and_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, png = _write_output_notebook(tmp_path / "notes" / "plot.ipynb")

    values = outputs.get_cell_outputs(path, 0)

    assert [value.output_type for value in values] == ["stream", "display_data"]
    assert values[0].text == "done\n"
    assert values[1].text == "<Figure>\n"
    assert values[1].image_data == {"image/png": png}
    assert values[1].is_image


def test_save_cell_images_writes_decoded_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(outputs, "ROOT_PATH", tmp_path)
    path, png = _write_output_notebook(tmp_path / "notes" / "plot.ipynb")

    saved = outputs.save_cell_images(path, 0)

    assert saved[0] == tmp_path / ".tmp" / "plot-cell-0-output-1.png"
    assert saved[0].read_bytes() == png


def test_markdown_cell_has_no_outputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "notes" / "plain.ipynb"
    path.parent.mkdir()
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("text")]
    nbformat.write(nb, path)

    assert outputs.get_cell_outputs(path, 0) == []


def test_get_cell_output_missing_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path, _ = _write_output_notebook(tmp_path / "notes" / "plot.ipynb")

    try:
        outputs.get_cell_output(path, 0, output_index=10)
    except IndexError as exc:
        assert "no output" in str(exc)
    else:
        raise AssertionError("expected IndexError")


def test_cli_output_extracts_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(outputs, "ROOT_PATH", tmp_path)
    _write_output_notebook(tmp_path / "notes" / "plot.ipynb")

    result = runner.invoke(cli.app, ["output", "plot", "--index", "0"])

    assert result.exit_code == 0
    expected = tmp_path / ".tmp" / "plot-cell-0-output-1.png"
    assert f"image: {expected}" in result.output
    assert expected.exists()
