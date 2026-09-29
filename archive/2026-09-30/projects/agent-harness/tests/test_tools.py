from __future__ import annotations

import asyncio

from pydantic import BaseModel

from agent_harness import SubAgentParams
from agent_harness.config import Config
from agent_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolRegistry, ToolResult
from agent_harness.tools.files import EditTool, ReadFileTool, WriteFileTool
from agent_harness.tools.shell import ShellTool


def run(coroutine):
    return asyncio.run(coroutine)


def test_default_registry_round_trip_contains_only_ported_tools(tmp_path):
    from agent_harness.tools.base import create_default_registry

    registry = create_default_registry(Config(cwd=tmp_path))
    names = {tool.name for tool in registry.get_tools()}

    assert names == {
        "read_file",
        "write_file",
        "edit",
        "shell",
        "list_dir",
        "grep",
        "glob",
        "memory",
        "run_sub_agent",
    }
    assert all("parameters" in schema for schema in registry.get_schemas())
    assert registry.unregister("glob") is True
    assert registry.get("glob") is None


def test_sub_agent_params_are_available_from_the_package_root():
    params = SubAgentParams(task="Inspect the repository.", max_turns=4)

    assert params.role == "codebase_investigator"
    assert params.max_turns == 4


class EchoParams(BaseModel):
    text: str


class EchoTool(Tool):
    name = "echo_test"
    description = "Echo text"
    kind = ToolKind.READ
    schema = EchoParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        return ToolResult.success_result(EchoParams(**invocation.params).text)


def test_registry_validates_arguments_before_execution(tmp_path):
    registry = ToolRegistry(Config(cwd=tmp_path))
    registry.register(EchoTool(registry.config))

    invalid = run(registry.invoke("echo_test", {}, tmp_path))
    valid = run(registry.invoke("echo_test", {"text": "hello"}, tmp_path))

    assert invalid.success is False
    assert invalid.error is not None
    assert "Invalid parameters" in invalid.error
    assert valid.success is True
    assert valid.output == "hello"


def test_edit_requires_unique_match_unless_replace_all(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("one\none\n", encoding="utf-8")
    tool = EditTool(Config(cwd=tmp_path))

    ambiguous = run(
        tool.execute(
            ToolInvocation(
                {"path": "sample.txt", "old_string": "one", "new_string": "two"},
                tmp_path,
            )
        )
    )
    replaced = run(
        tool.execute(
            ToolInvocation(
                {
                    "path": "sample.txt",
                    "old_string": "one",
                    "new_string": "two",
                    "replace_all": True,
                },
                tmp_path,
            )
        )
    )

    assert ambiguous.success is False
    assert ambiguous.error is not None
    assert "found 2 times" in ambiguous.error
    assert replaced.success is True
    assert path.read_text(encoding="utf-8") == "two\ntwo\n"


def test_file_tools_confine_paths_to_workspace(tmp_path):
    outside = tmp_path.parent / "outside-agent-harness.txt"
    outside.write_text("secret", encoding="utf-8")
    config = Config(cwd=tmp_path)

    read_result = run(
        ReadFileTool(config).execute(ToolInvocation({"path": "../outside-agent-harness.txt"}, tmp_path))
    )
    write_result = run(
        WriteFileTool(config).execute(
            ToolInvocation({"path": "../should-not-exist.txt", "content": "x"}, tmp_path)
        )
    )

    assert read_result.success is False
    assert write_result.success is False
    assert read_result.error is not None
    assert "escapes working directory" in read_result.error
    assert not (tmp_path.parent / "should-not-exist.txt").exists()


def test_shell_surfaces_exit_code_and_timeout(tmp_path):
    tool = ShellTool(Config(cwd=tmp_path))
    failed = run(
        tool.execute(ToolInvocation({"command": "printf error >&2; exit 7"}, tmp_path))
    )
    timed_out = run(
        tool.execute(ToolInvocation({"command": "sleep 2", "timeout": 1}, tmp_path))
    )

    assert failed.success is False
    assert failed.exit_code == 7
    assert "Exit code: 7" in failed.output
    assert timed_out.success is False
    assert timed_out.metadata["timed_out"] is True
    assert timed_out.error is not None
    assert "timed out" in timed_out.error


def test_shell_working_directory_is_confined(tmp_path):
    result = run(
        ShellTool(Config(cwd=tmp_path)).execute(
            ToolInvocation({"command": "pwd", "cwd": ".."}, tmp_path)
        )
    )

    assert result.success is False
    assert result.error is not None
    assert "escapes working directory" in result.error
