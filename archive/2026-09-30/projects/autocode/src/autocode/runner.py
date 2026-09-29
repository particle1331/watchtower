"""Agent runner ports used by the application service.

The deterministic runner keeps the complete web stack runnable without a
provider account.  The harness adapter translates the preceding course's
``AgentEvent`` values into the product event vocabulary.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class RunnerEvent:
    kind: str
    payload: dict[str, Any]


class AgentRunner(Protocol):
    def stream(self, session_id: str, message: str) -> AsyncIterator[RunnerEvent]: ...


class DemoAgentRunner:
    """Deterministic streaming agent used by tests and the default local app."""

    def __init__(self, *, delay: float = 0.0) -> None:
        self.delay = delay

    async def stream(self, session_id: str, message: str) -> AsyncIterator[RunnerEvent]:
        yield RunnerEvent("run_started", {"mode": "demo"})
        response = (
            "Demo agent received your task: "
            f"{message}. Switch AUTOCODE_AGENT_MODE to harness for a live model run."
        )
        for chunk in _chunks(response, 18):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield RunnerEvent("text_delta", {"content": chunk})
        yield RunnerEvent("assistant_message", {"content": response})
        yield RunnerEvent("run_finished", {"reason": "complete"})


class HarnessAgentRunner:
    """Adapter from ``agent_harness.Agent`` to product runner events."""

    def __init__(self, cwd: str | Path = ".") -> None:
        self.cwd = Path(cwd)
        self._agents: dict[str, Any] = {}

    async def stream(self, session_id: str, message: str) -> AsyncIterator[RunnerEvent]:
        from agent_harness import Agent, Config

        agent = self._agents.setdefault(session_id, Agent(Config(cwd=self.cwd)))
        async for event in agent.run(message):
            kind = event.type.value
            if kind == "tool_call_start":
                kind = "tool_started"
            elif kind == "tool_call_complete":
                kind = "tool_finished"
            elif kind == "text_complete":
                kind = "assistant_message"
            yield RunnerEvent(kind, dict(event.data))


def runner_for_mode(mode: str, *, cwd: str | Path = ".") -> AgentRunner:
    normalized = mode.strip().lower()
    if normalized == "demo":
        return DemoAgentRunner(delay=0.025)
    if normalized == "harness":
        return HarnessAgentRunner(cwd)
    raise ValueError(f"unknown agent mode: {mode}")


def _chunks(text: str, width: int) -> list[str]:
    return [text[index : index + width] for index in range(0, len(text), width)]
