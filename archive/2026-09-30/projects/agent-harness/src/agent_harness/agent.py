"""Core agent module: the agentic loop (think -> act -> observe -> repeat).

The Agent class orchestrates multi-turn conversations with an LLM,
processing streamed responses and invoking tools when requested.
It yields AgentEvent objects so callers can render output progressively.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from agent_harness.config import Config
from agent_harness.events import (
    AgentEvent,
    AgentEventType,
    EventBus,
    StreamEventType,
    ToolCall,
    ToolResultMessage,
)
from agent_harness.hooks import HookSystem
from agent_harness.session import Session

logger = logging.getLogger(__name__)


class Agent:
    """AI coding agent with an async agentic loop.

    Usage::

        agent = Agent(config)
        async for event in agent.run("Fix the bug in main.py"):
            if event.type == AgentEventType.TEXT_DELTA:
                print(event.data["content"], end="")
    """

    def __init__(
        self,
        config: Config | None = None,
        session: Session | None = None,
    ) -> None:
        self.config = config or Config()
        self.session = session or Session(self.config)
        self.hooks = HookSystem(self.config)
        self.events = EventBus()

    async def run(self, user_message: str) -> AsyncGenerator[AgentEvent]:
        """Run the agent on a user message, yielding lifecycle events.

        This is the main entry point. It wraps :meth:`_agentic_loop` with
        start / end / error bookkeeping so callers always get a clean
        event stream.
        """
        yield await self._publish_event(AgentEvent.agent_start(user_message))
        self.session.add_user_message(user_message)
        await self.hooks.trigger_before_agent(user_message)

        try:
            response: str | None = None
            async for event in self._agentic_loop():
                yield event
                if (
                    event.data.get("content") is not None
                    and event.type == AgentEventType.TEXT_COMPLETE
                ):
                    response = event.data["content"]

            yield await self._publish_event(AgentEvent.agent_end(response, self.session.total_usage))
            await self.hooks.trigger_after_agent(user_message, response or "")

        except Exception as exc:
            logger.exception("Agent run failed")
            await self.hooks.trigger_on_error(exc)
            yield await self._publish_event(AgentEvent.agent_error(str(exc)))

    async def _publish_event(self, event: AgentEvent) -> AgentEvent:
        """Publish an event to subscribers before returning it to the caller."""
        await self.events.emit(event)
        return event

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent]:
        """Multi-turn loop: call LLM, execute tools, repeat.

        Yields :class:`AgentEvent` objects for each meaningful step
        (text deltas, tool invocations, completions).
        """
        for _turn in range(self.config.max_turns):
            self.session.start_turn()
            logger.debug("Turn %d / %d", self.session.turn_count, self.config.max_turns)

            accumulated_text = ""
            tool_calls: list[ToolCall] = []
            error_message: str | None = None

            stream = self.session.client.chat_completion(
                self.session.get_messages(),
                tools=self.session.get_tool_schemas(),
            )

            async for event in stream:
                if event.type == StreamEventType.TEXT_DELTA:
                    content = event.text_delta.content if event.text_delta else ""
                    accumulated_text += content
                    yield await self._publish_event(AgentEvent.text_delta(content))

                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_call is not None:
                        tool_calls.append(event.tool_call)

                elif event.type == StreamEventType.MESSAGE_COMPLETE:
                    if event.usage is not None:
                        self.session.track_usage(event.usage)

                elif event.type == StreamEventType.ERROR:
                    error_message = event.error
                    yield await self._publish_event(
                        AgentEvent.agent_error(error_message or "Unknown LLM error")
                    )

            if error_message is not None:
                return

            if accumulated_text:
                yield await self._publish_event(AgentEvent.text_complete(accumulated_text))

            assistant_msg = self._build_assistant_message(accumulated_text, tool_calls)
            if tool_calls:
                self.session.add_assistant_message(
                    content=assistant_msg.get("content", ""),
                    tool_calls=[
                        {
                            "id": tool_call.call_id,
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        }
                        for tool_call in tool_calls
                    ],
                )
            else:
                self.session.add_assistant_message(content=assistant_msg.get("content", ""))

            if not tool_calls:
                return

            for tool_call in tool_calls:
                name = tool_call.name or ""
                yield await self._publish_event(
                    AgentEvent.tool_call_start(tool_call.call_id, name, tool_call.arguments)
                )

                await self.hooks.trigger_before_tool(name, tool_call.arguments)
                result = await self.session.registry.invoke(
                    name, tool_call.arguments, self.config.cwd
                )
                await self.hooks.trigger_after_tool(name, tool_call.arguments, result)

                yield await self._publish_event(
                    AgentEvent.tool_call_complete(tool_call.call_id, name, result)
                )

                tool_result_msg = ToolResultMessage(
                    tool_call_id=tool_call.call_id,
                    content=result.to_model_output(),
                    is_error=not result.success,
                )
                self.session.add_tool_result(tool_result_msg)

        yield await self._publish_event(
            AgentEvent.agent_error(
                f"Agent exceeded maximum number of turns ({self.config.max_turns})"
            )
        )

    @staticmethod
    def _build_assistant_message(
        text: str | None,
        tool_calls: list[ToolCall],
    ) -> dict[str, Any]:
        """Build an assistant message dict in OpenAI format.

        Parameters
        ----------
        text : str | None
            The text content of the assistant reply.
        tool_calls : list[ToolCall]
            Completed tool calls from the LLM response.

        Returns
        -------
        dict
            Message dict with ``role``, ``content``, and optionally
            ``tool_calls``.
        """
        message: dict[str, Any] = {
            "role": "assistant",
            "content": text or "",
        }
        if tool_calls:
            message["tool_calls"] = [
                {
                    "id": tool_call.call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                }
                for tool_call in tool_calls
            ]
        return message
