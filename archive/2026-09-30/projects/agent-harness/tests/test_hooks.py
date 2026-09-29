from __future__ import annotations

import asyncio
import time

from agent_harness.config import Config, HookConfig, HookTrigger
from agent_harness.hooks import HookSystem


def run(coroutine):
    return asyncio.run(coroutine)


def test_crashing_and_hanging_hooks_are_contained(tmp_path):
    config = Config(
        cwd=tmp_path,
        hooks_enabled=True,
        hooks=[
            HookConfig(
                name="crash",
                trigger=HookTrigger.BEFORE_AGENT,
                command="exit 1",
            ),
            HookConfig(
                name="hang",
                trigger=HookTrigger.BEFORE_AGENT,
                command="sleep 2",
                timeout_sec=0.05,
            ),
        ],
    )
    hooks = HookSystem(config)
    started = time.monotonic()

    run(hooks.trigger_before_agent("hello"))

    assert time.monotonic() - started < 1.5


def test_hook_environment_contains_trigger_and_context(tmp_path):
    config = Config(
        cwd=tmp_path,
        hooks_enabled=True,
        hooks=[
            HookConfig(
                name="before-tool",
                trigger=HookTrigger.BEFORE_TOOL,
                command="test \"$AI_AGENT_TRIGGER\" = before_tool && test \"$AI_AGENT_TOOL_NAME\" = shell",
            )
        ],
    )

    run(HookSystem(config).trigger_before_tool("shell", {"command": "pwd"}))
