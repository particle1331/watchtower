"""Make task ordering and external command boundaries."""

import os
import runpy
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

preview_site = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/docs.py"))["preview_site"]


@pytest.mark.parametrize("resume_fails", [False, True])
def test_make_docs_rebuilds_before_preview(tmp_path, resume_fails):
    log = tmp_path / "calls"
    stub = tmp_path / "python_stub.py"
    stub.write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        "task = Path(sys.argv[-1]).stem\n"
        "with open(os.environ['TASK_LOG'], 'a') as f:\n"
        "    f.write(task + ':' + os.environ['PORT'] + '\\n')\n"
        "if task == 'resume' and os.environ['RESUME_FAIL'] == '1':\n"
        "    sys.exit(1)\n"
    )
    result = subprocess.run(
        ["make", "-s", "-f", str(Path(__file__).resolve().parents[1] / "Makefile"),
         "docs", "PORT=4300", f"PYTHON={shlex.quote(sys.executable)} {shlex.quote(str(stub))}"],
        cwd=tmp_path,
        env={**os.environ, "TASK_LOG": str(log), "RESUME_FAIL": str(int(resume_fails))},
        capture_output=True,
        text=True,
    )
    assert (result.returncode != 0) == resume_fails
    assert log.read_text().splitlines() == (
        ["resume:4300"] if resume_fails else ["resume:4300", "render-context:4300", "validate:4300", "sync-site:4300", "docs:4300"]
    )


def test_preview_passes_port_and_virtualenv_python(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    run = Mock()
    monkeypatch.setenv("PORT", "4300")
    monkeypatch.setattr(subprocess, "run", run)
    preview_site()
    args, kwargs = run.call_args
    assert args[0] == ["quarto", "preview", "--port", "4300"]
    assert kwargs["env"]["QUARTO_PYTHON"] == sys.executable
    assert kwargs["check"] is True
    assert "http://localhost:4300/" in capsys.readouterr().out


def test_migrated_preview_uses_saved_working_build(monkeypatch, tmp_path):
    from watchtower.services.build import BuildService
    catalog = tmp_path / "content/data/catalog.yaml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("version: 1\nartifacts: []\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "4300")
    preview = Mock()
    monkeypatch.setattr(BuildService, "preview", preview)
    preview_site()
    preview.assert_called_once_with(4300)


@pytest.mark.parametrize("port", ["0", "65536", "invalid"])
def test_preview_rejects_invalid_port(monkeypatch, port):
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ValueError):
        preview_site()
    run.assert_not_called()
