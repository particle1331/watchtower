"""Async LLM client with streaming support.

Wraps AsyncOpenAI to talk to OpenRouter (or any OpenAI-compatible endpoint).
Produces StreamEvent objects that the agentic loop consumes.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from agent_harness.config import Config
from agent_harness.events import (
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallDelta,
    parse_tool_call_arguments,
)


class LLMClient:
    """Async streaming LLM client backed by an OpenAI-compatible API.

    Usage::

        client = LLMClient(config)
        async for event in client.chat_completion(messages):
            if event.type == StreamEventType.TEXT_DELTA:
                print(event.text_delta.content, end="")
    """

    def __init__(self, config: Config) -> None:
        self._client: AsyncOpenAI | None = None
        self._max_retries: int = 3
        self.config = config

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    # --------------------------------------------------------------------- #
    #  Public API                                                             #
    # --------------------------------------------------------------------- #

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize tool schemas into OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get(
                        "parameters",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
            for tool in tools
        ]

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> AsyncGenerator[StreamEvent]:
        """Send a chat completion request and yield StreamEvents.

        Retries on RateLimitError and APIConnectionError with exponential
        back-off (up to ``_max_retries``).
        """
        client = self.get_client()

        kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "stream": stream,
        }

        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        for attempt in range(self._max_retries + 1):
            try:
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event
                return
            except RateLimitError as exc:
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Rate limit exceeded: {exc}",
                    )
                    return
            except APIConnectionError as exc:
                if attempt < self._max_retries:
                    await asyncio.sleep(2**attempt)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Connection error: {exc}",
                    )
                    return
            except APIError as exc:
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    error=f"API error: {exc}",
                )
                return

    # --------------------------------------------------------------------- #
    #  Streaming implementation                                               #
    # --------------------------------------------------------------------- #

    async def _stream_response(
        self,
        client: AsyncOpenAI,
        kwargs: dict[str, Any],
    ) -> AsyncGenerator[StreamEvent]:
        # Chat Completions remains the OpenAI-compatible streaming API in openai 3.x.
        response = await client.chat.completions.create(**kwargs)

        finish_reason: str | None = None
        usage: TokenUsage | None = None
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in response:
            # Some providers send usage in a trailing chunk.
            if hasattr(chunk, "usage") and chunk.usage:
                cached = 0
                if (
                    hasattr(chunk.usage, "prompt_tokens_details")
                    and chunk.usage.prompt_tokens_details
                ):
                    cached = getattr(
                        chunk.usage.prompt_tokens_details, "cached_tokens", 0
                    ) or 0
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens or 0,
                    completion_tokens=chunk.usage.completion_tokens or 0,
                    total_tokens=chunk.usage.total_tokens or 0,
                    cached_tokens=cached,
                )

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    text_delta=TextDelta(delta.content),
                )

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }

                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls[idx]["name"] = tc_delta.function.name
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tc_delta.function.name,
                                ),
                            )

                        if tc_delta.function.arguments:
                            tool_calls[idx]["arguments"] += tc_delta.function.arguments
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_DELTA,
                                tool_call_delta=ToolCallDelta(
                                    call_id=tool_calls[idx]["id"],
                                    name=tc_delta.function.name,
                                    arguments_delta=tc_delta.function.arguments,
                                ),
                            )

        for tc in tool_calls.values():
            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(
                    call_id=tc["id"],
                    name=tc["name"],
                    arguments=parse_tool_call_arguments(tc["arguments"]),
                ),
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage,
        )

    # --------------------------------------------------------------------- #
    #  Non-streaming implementation                                           #
    # --------------------------------------------------------------------- #

    async def _non_stream_response(
        self,
        client: AsyncOpenAI,
        kwargs: dict[str, Any],
    ) -> StreamEvent:
        kwargs_copy = {**kwargs, "stream": False}
        response = await client.chat.completions.create(**kwargs_copy)
        choice = response.choices[0]
        message = choice.message

        text_delta = TextDelta(content=message.content) if message.content else None

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        call_id=tc.id,
                        name=tc.function.name,
                        arguments=parse_tool_call_arguments(tc.function.arguments),
                    )
                )

        usage = None
        if response.usage:
            cached = 0
            if (
                hasattr(response.usage, "prompt_tokens_details")
                and response.usage.prompt_tokens_details
            ):
                cached = getattr(response.usage.prompt_tokens_details, "cached_tokens", 0) or 0
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
                cached_tokens=cached,
            )

        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            finish_reason=choice.finish_reason,
            usage=usage,
            tool_call=(tool_calls[0] if len(tool_calls) == 1 else None),
        )
