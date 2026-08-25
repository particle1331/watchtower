from __future__ import annotations

import asyncio
import copy
from typing import cast

from agent_harness.agent import Agent
from agent_harness.client import LLMClient
from agent_harness.config import Config
from agent_harness.events import (
    EventBus,
    StreamEvent,
    StreamEventType,
    TextDelta,
    TokenUsage,
    ToolResultMessage,
)
from agent_harness.session import Session
from agent_harness.tools.base import ToolRegistry


def run(coroutine):
    return asyncio.run(coroutine)


def test_session_journal_replay_reconstructs_state(tmp_path):
    config = Config(cwd=tmp_path)
    registry = ToolRegistry(config)
    session = Session(config, registry=registry)
    session.start_turn()
    session.add_user_message("inspect the project")
    session.add_assistant_message(
        "I will inspect it",
        tool_calls=[{"id": "call-1", "name": "list_dir", "arguments": {"path": "."}}],
    )
    session.add_tool_result(ToolResultMessage("call-1", "file.py"))
    session.track_usage(TokenUsage(prompt_tokens=10, completion_tokens=4, total_tokens=14))
    journal = copy.deepcopy(session.journal)

    replayed = Session.replay(journal, config, registry=registry)

    assert replayed.messages == session.messages
    assert replayed.turn_count == session.turn_count
    assert replayed.total_usage == session.total_usage
    assert replayed.journal == journal


def test_event_bus_preserves_subscriber_and_emit_order():
    seen = []

    async def first(event):
        await asyncio.sleep(0.01)
        seen.append(("first", event))

    def second(event):
        seen.append(("second", event))

    async def exercise():
        bus = EventBus()
        bus.subscribe(first)
        bus.subscribe(second)
        await bus.emit("one")
        await bus.emit("two")

    run(exercise())

    assert seen == [("first", "one"), ("second", "one"), ("first", "two"), ("second", "two")]


def test_agent_publishes_and_yields_events_in_the_same_order(tmp_path):
    class FakeClient:
        async def chat_completion(self, messages, tools=None):
            yield StreamEvent(
                type=StreamEventType.TEXT_DELTA,
                text_delta=TextDelta("answer"),
            )
            yield StreamEvent(type=StreamEventType.MESSAGE_COMPLETE)

    config = Config(cwd=tmp_path, max_turns=1)
    session = Session(
        config,
        client=cast(LLMClient, FakeClient()),
        registry=ToolRegistry(config),
    )
    agent = Agent(config, session=session)
    published = []
    agent.events.subscribe(published.append)

    async def collect():
        return [event async for event in agent.run("hello")]

    yielded = run(collect())

    assert [event.type for event in published] == [event.type for event in yielded]
