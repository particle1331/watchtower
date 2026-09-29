from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

from openai import AsyncOpenAI

from agent_harness.client import LLMClient
from agent_harness.config import Config
from agent_harness.events import StreamEventType, TextDelta


def run(coroutine):
    return asyncio.run(coroutine)


def test_build_tools_uses_openai_function_schema(tmp_path):
    client = LLMClient(Config(cwd=tmp_path))

    result = client._build_tools(
        [{"name": "read_file", "description": "Read", "parameters": {"type": "object"}}]
    )

    assert result == [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read",
                "parameters": {"type": "object"},
            },
        }
    ]


def test_non_stream_response_translates_text_tool_calls_and_usage(tmp_path):
    client = LLMClient(Config(cwd=tmp_path))
    class Completions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="tool_calls",
                        message=SimpleNamespace(
                            content="checking",
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="read_file", arguments='{"path":"a.py"}'
                                    ),
                                )
                            ],
                        ),
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=4,
                    completion_tokens=3,
                    total_tokens=7,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=1),
                ),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    event = run(
        client._non_stream_response(cast(AsyncOpenAI, fake_client), {"messages": []})
    )

    assert event.type == StreamEventType.MESSAGE_COMPLETE
    assert event.tool_call is not None
    assert event.tool_call.name == "read_file"
    assert event.tool_call.arguments == {"path": "a.py"}
    assert event.usage is not None
    assert event.usage.cached_tokens == 1


def test_non_stream_response_uses_async_openai_shape(tmp_path):
    client = LLMClient(Config(cwd=tmp_path))

    class Completions:
        async def create(self, **kwargs):
            assert kwargs["stream"] is False
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content="done", tool_calls=None),
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=4,
                    completion_tokens=3,
                    total_tokens=7,
                    prompt_tokens_details=None,
                ),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    event = run(
        client._non_stream_response(
            cast(AsyncOpenAI, fake_client), {"messages": [], "stream": True}
        )
    )

    assert event.type == StreamEventType.MESSAGE_COMPLETE
    assert event.text_delta == TextDelta("done")
    assert event.finish_reason == "stop"
    assert event.usage is not None
    assert event.usage.total_tokens == 7


def test_stream_response_accumulates_deltas(tmp_path):
    client = LLMClient(Config(cwd=tmp_path))

    class Response:
        def __aiter__(self):
            chunks = [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="hi", tool_calls=None),
                            finish_reason=None,
                        )
                    ],
                    usage=None,
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(content="!", tool_calls=None),
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=2,
                        completion_tokens=2,
                        total_tokens=4,
                        prompt_tokens_details=None,
                    ),
                ),
            ]
            return _AsyncIterator(chunks)

    class Completions:
        async def create(self, **kwargs):
            return Response()

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    events = run(
        _collect(client._stream_response(cast(AsyncOpenAI, fake_client), {"stream": True}))
    )

    assert [event.type for event in events] == [
        StreamEventType.TEXT_DELTA,
        StreamEventType.TEXT_DELTA,
        StreamEventType.MESSAGE_COMPLETE,
    ]
    assert "".join(event.text_delta.content for event in events[:2]) == "hi!"
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens == 4


async def _collect(stream):
    return [event async for event in stream]


class _AsyncIterator:
    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc
