"""Stream-level and agent-level event types.

Two layers of events:
  - StreamEvent / StreamEventType: raw LLM streaming chunks (text deltas,
    tool-call deltas, usage). Produced by LLMClient.
  - AgentEvent / AgentEventType: higher-level lifecycle events (agent start/end,
    tool invocation, text completion). Produced by the Agent agentic loop.
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Stream-level events (from LLMClient)
# =============================================================================


class StreamEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    MESSAGE_COMPLETE = "message_complete"
    ERROR = "error"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETE = "tool_call_complete"


@dataclass
class TextDelta:
    content: str

    def __str__(self) -> str:
        return self.content


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


@dataclass
class ToolCallDelta:
    call_id: str
    name: str | None = None
    arguments_delta: str = ""


@dataclass
class ToolCall:
    call_id: str
    name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamEvent:
    """A single event from the LLM streaming response."""

    type: StreamEventType
    text_delta: TextDelta | None = None
    error: str | None = None
    finish_reason: str | None = None
    tool_call_delta: ToolCallDelta | None = None
    tool_call: ToolCall | None = None
    usage: TokenUsage | None = None


@dataclass
class ToolResultMessage:
    tool_call_id: str
    content: str
    is_error: bool = False

    def to_openai_message(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


def parse_tool_call_arguments(arguments_str: str) -> dict[str, Any]:
    """Parse JSON arguments string from tool call delta accumulation."""
    if not arguments_str:
        return {}
    try:
        return json.loads(arguments_str)
    except json.JSONDecodeError:
        return {"raw_arguments": arguments_str}


# =============================================================================
# Agent-level events (from Agent agentic loop)
# =============================================================================


class AgentEventType(StrEnum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"


@dataclass
class AgentEvent:
    """A high-level event from the agent's agentic loop."""

    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def agent_start(cls, message: str) -> AgentEvent:
        return cls(type=AgentEventType.AGENT_START, data={"message": message})

    @classmethod
    def agent_end(
        cls,
        response: str | None = None,
        usage: TokenUsage | None = None,
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_END,
            data={
                "response": response,
                "usage": usage.__dict__ if usage else None,
            },
        )

    @classmethod
    def agent_error(cls, error: str) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={"error": error},
        )

    @classmethod
    def text_delta(cls, content: str) -> AgentEvent:
        return cls(type=AgentEventType.TEXT_DELTA, data={"content": content})

    @classmethod
    def text_complete(cls, content: str) -> AgentEvent:
        return cls(type=AgentEventType.TEXT_COMPLETE, data={"content": content})

    @classmethod
    def tool_call_start(
        cls, call_id: str, name: str, arguments: dict[str, Any]
    ) -> AgentEvent:
        return cls(
            type=AgentEventType.TOOL_CALL_START,
            data={"call_id": call_id, "name": name, "arguments": arguments},
        )

    @classmethod
    def tool_call_complete(
        cls, call_id: str, name: str, result: Any
    ) -> AgentEvent:
        # result is a ToolResult, but we avoid importing it here to prevent circular deps.
        data: dict[str, Any] = {"call_id": call_id, "name": name}
        if hasattr(result, "success"):
            data.update(
                {
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "metadata": getattr(result, "metadata", {}),
                    "diff": (
                        result.diff.to_diff()
                        if getattr(result, "diff", None)
                        else None
                    ),
                    "truncated": getattr(result, "truncated", False),
                    "exit_code": getattr(result, "exit_code", None),
                }
            )
        return cls(type=AgentEventType.TOOL_CALL_COMPLETE, data=data)


EventHandler = Callable[[Any], Any]


class EventBus:
    """Dispatch events to subscribers in registration order.

    Handlers are awaited one at a time, so a slow subscriber cannot reorder
    observations made by later subscribers. A faulty subscriber is contained
    and logged rather than stopping the agent's event stream.
    """

    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        """Register *handler* once."""
        if handler not in self._subscribers:
            self._subscribers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> bool:
        """Remove *handler*, returning whether it was registered."""
        try:
            self._subscribers.remove(handler)
        except ValueError:
            return False
        return True

    async def emit(self, event: Any) -> None:
        """Deliver *event* to each subscriber in order."""
        for handler in tuple(self._subscribers):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001 - one subscriber must not break dispatch
                logger.exception("Event subscriber failed")

    publish = emit
