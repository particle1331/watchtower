from __future__ import annotations

import asyncio

from agent_harness.sandbox import Sandbox, SandboxConfig


def run(coroutine):
    return asyncio.run(coroutine)


def test_local_sandbox_runs_commands_and_preserves_workspace_boundary(tmp_path):
    sandbox = Sandbox(
        SandboxConfig(
            workspace=tmp_path,
            timeout=120.0,
            cpu_limit=None,
            pids_limit=None,
            max_output_bytes=100 * 1024,
        )
    )

    result = run(sandbox.run("printf '%s' \"$SANDBOX_TEST\"", env={"SANDBOX_TEST": "ok"}))
    escaped = run(sandbox.run("pwd", cwd=".."))

    assert result.success is True
    assert result.stdout == "ok"
    assert result.exit_code == 0
    assert escaped.success is False
    assert escaped.error is not None
    assert "escapes workspace" in escaped.error


def test_local_sandbox_reports_timeout_and_truncated_output(tmp_path):
    sandbox = Sandbox(
        SandboxConfig(
            workspace=tmp_path,
            timeout=0.05,
            cpu_limit=None,
            pids_limit=None,
            max_output_bytes=4,
        )
    )

    timed_out = run(sandbox.run("sleep 1"))
    truncated = run(sandbox.run("printf 123456"))

    assert timed_out.timed_out is True
    assert timed_out.success is False
    assert truncated.stdout == "1234"
    assert truncated.truncated is True
