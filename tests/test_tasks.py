"""Make task ordering and external command boundaries."""

import os
import runpy
import shlex
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path
from unittest.mock import Mock

import pytest

preview_site = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/docs.py"))["preview_site"]
dev_script = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/dev.py"))
run_workspace = dev_script["run_workspace"]


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
    catalog = tmp_path / "backend/data/catalog.yaml"
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


@pytest.mark.parametrize("port,cms_port", [(0, 5200), (4200, 65536), (4200, 4200)])
def test_dev_rejects_invalid_ports_before_starting_servers(monkeypatch, port, cms_port):
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(ValueError):
        run_workspace(port, cms_port)
    launch.assert_not_called()


def test_dev_rejects_occupied_ports_before_starting_servers(monkeypatch):
    probe = Mock()
    probe.bind.side_effect = OSError("address already in use")
    context = Mock(__enter__=Mock(return_value=probe), __exit__=Mock(return_value=False))
    monkeypatch.setattr(dev_script["socket"], "socket", Mock(return_value=context))
    launch = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(ValueError, match="Port 4200 is unavailable"):
        run_workspace(4200, 5200)
    launch.assert_not_called()


@pytest.mark.parametrize("status,expected", [(200, True), (307, True), (503, False)])
def test_dev_readiness_accepts_cms_redirects(monkeypatch, status, expected):
    connection = Mock()
    connection.getresponse.return_value.status = status
    monkeypatch.setattr(dev_script["http"].client, "HTTPConnection", Mock(return_value=connection))
    assert dev_script["ready"](5200, "/cms/") is expected
    connection.request.assert_called_once_with("GET", "/cms/")
    connection.close.assert_called_once()


@pytest.fixture
def dev_processes(monkeypatch):
    cms = Mock(pid=101, poll=Mock(side_effect=[None, None, 7]))
    preview = Mock(pid=102, poll=Mock(return_value=None))
    launch = Mock(side_effect=[cms, preview])
    terminate = Mock()
    browser = Mock()
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(os, "killpg", terminate)
    monkeypatch.setattr(webbrowser, "open_new_tab", browser)
    monkeypatch.setitem(run_workspace.__globals__, "check_ports", Mock())
    monkeypatch.setitem(run_workspace.__globals__, "ready", Mock(side_effect=[True, False, True]))
    monkeypatch.setattr(dev_script["time"], "sleep", Mock())
    return cms, preview, launch, terminate, browser


def test_dev_opens_tabs_when_ready_and_stops_both_when_a_server_fails(dev_processes):
    cms, preview, launch, terminate, browser = dev_processes
    assert run_workspace(4300, 5300) == 7
    commands = [call.args[0] for call in launch.call_args_list]
    assert commands == [
        [sys.executable, "-m", "watchtower.cli", "serve", "--port", "5300"],
        [sys.executable, "-m", "watchtower.cli", "preview", "--port", "4300"],
    ]
    assert all(call.kwargs["start_new_session"] for call in launch.call_args_list)
    assert [call.args[0] for call in browser.call_args_list] == [
        "http://127.0.0.1:5300/cms/", "http://127.0.0.1:4300/",
    ]
    assert [call.args for call in terminate.call_args_list] == [
        (cms.pid, signal.SIGTERM), (preview.pid, signal.SIGTERM),
    ]
    cms.wait.assert_called_once_with(timeout=5)
    preview.wait.assert_called_once_with(timeout=5)


def test_dev_interrupt_stops_both_process_groups_without_opening_tabs(monkeypatch, dev_processes):
    cms, preview, _, terminate, browser = dev_processes
    monkeypatch.setattr(dev_script["time"], "sleep", Mock(side_effect=KeyboardInterrupt))
    assert run_workspace(4300, 5300, open_browser=False) == 130
    assert [call.args[0] for call in terminate.call_args_list] == [cms.pid, preview.pid]
    browser.assert_not_called()


def test_dev_partial_startup_failure_stops_the_started_server(dev_processes):
    cms, _, launch, terminate, _ = dev_processes
    launch.side_effect = [cms, OSError("cannot launch preview")]
    with pytest.raises(OSError, match="cannot launch preview"):
        run_workspace(4300, 5300)
    terminate.assert_called_once_with(cms.pid, signal.SIGTERM)
    cms.wait.assert_called_once_with(timeout=5)


def test_make_dev_passes_both_custom_ports(tmp_path):
    output = tmp_path / "args"
    stub = tmp_path / "python_stub.py"
    stub.write_text("import sys\nfrom pathlib import Path\nPath(" + repr(str(output)) + ").write_text('\\n'.join(sys.argv[1:]))\n")
    result = subprocess.run(
        ["make", "-s", "-f", str(Path(__file__).resolve().parents[1] / "Makefile"),
         "dev", "PORT=4300", "CMS_PORT=5300", f"PYTHON={shlex.quote(sys.executable)} {shlex.quote(str(stub))}"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text().splitlines() == ["scripts/dev.py", "--port", "4300", "--cms-port", "5300"]
