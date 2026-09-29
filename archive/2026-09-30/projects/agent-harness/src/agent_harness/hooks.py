"""Hook system: run shell scripts at agent lifecycle points.

A hook is a small shell command (or inline bash script) that runs
synchronously at one of five lifecycle points. Hook failures and hangs are
contained so user configuration cannot break the agent loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import tempfile
from typing import TYPE_CHECKING, Any

from agent_harness.config import Config, HookConfig, HookTrigger

if TYPE_CHECKING:
    from agent_harness.tools.base import ToolResult

logger = logging.getLogger(__name__)


class HookSystem:
    """Executes configured hooks at agent lifecycle points.

    Construction is cheap: if ``config.hooks_enabled`` is false, the
    hook list is empty and all trigger methods are no-ops.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.hooks: list[HookConfig] = []
        if config.hooks_enabled:
            self.hooks = [hook for hook in config.hooks if hook.enabled]

    async def _run_hook(self, hook: HookConfig, env: dict[str, str]) -> None:
        try:
            if hook.command:
                await self._run_command(hook.command, hook.timeout_sec, env)
            else:
                script_path = await asyncio.to_thread(self._write_script, hook.script or "")
                try:
                    await self._run_command(script_path, hook.timeout_sec, env)
                finally:
                    os.unlink(script_path)
        except Exception as exc:  # noqa: BLE001 - hooks must never break the agent
            logger.warning("Hook %r failed: %s", hook.name, exc)

    @staticmethod
    def _write_script(body: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".sh")
        try:
            with os.fdopen(fd, "w") as file:
                file.write("#!/bin/bash\n")
                file.write(body)
            os.chmod(path, 0o755)
            return path
        except Exception:
            os.unlink(path)
            raise

    async def _run_command(
        self,
        command: str,
        timeout: float,
        env: dict[str, str],
    ) -> None:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.config.cwd),
            env=env,
            start_new_session=True,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
            logger.warning("Hook timed out after %.1fs: %s", timeout, command)

    def _build_env(
        self,
        trigger: HookTrigger,
        tool_name: str | None = None,
        user_message: str | None = None,
        response: str | None = None,
        tool_params: dict[str, Any] | None = None,
        tool_result: ToolResult | None = None,
        error: Exception | None = None,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env["AI_AGENT_TRIGGER"] = trigger.value
        env["AI_AGENT_CWD"] = str(self.config.cwd)
        if tool_name:
            env["AI_AGENT_TOOL_NAME"] = tool_name
        if user_message:
            env["AI_AGENT_USER_MESSAGE"] = user_message
        if response is not None:
            env["AI_AGENT_RESPONSE"] = response
        if tool_params is not None:
            env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
        if tool_result is not None:
            env["AI_AGENT_TOOL_RESULT"] = tool_result.to_model_output()
        if error is not None:
            env["AI_AGENT_ERROR"] = str(error)
        return env

    async def trigger_before_agent(self, user_message: str) -> None:
        env = self._build_env(HookTrigger.BEFORE_AGENT, user_message=user_message)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT:
                await self._run_hook(hook, env)

    async def trigger_after_agent(self, user_message: str, agent_response: str) -> None:
        env = self._build_env(
            HookTrigger.AFTER_AGENT,
            user_message=user_message,
            response=agent_response,
        )
        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_AGENT:
                await self._run_hook(hook, env)

    async def trigger_before_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
    ) -> None:
        env = self._build_env(
            HookTrigger.BEFORE_TOOL,
            tool_name=tool_name,
            tool_params=tool_params,
        )
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_TOOL:
                await self._run_hook(hook, env)

    async def trigger_after_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        tool_result: ToolResult,
    ) -> None:
        env = self._build_env(
            HookTrigger.AFTER_TOOL,
            tool_name=tool_name,
            tool_params=tool_params,
            tool_result=tool_result,
        )
        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_TOOL:
                await self._run_hook(hook, env)

    async def trigger_on_error(self, error: Exception) -> None:
        env = self._build_env(HookTrigger.ON_ERROR, error=error)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.ON_ERROR:
                await self._run_hook(hook, env)


HookDispatcher = HookSystem
