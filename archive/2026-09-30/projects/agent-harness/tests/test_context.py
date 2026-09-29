from __future__ import annotations

import asyncio

from agent_harness.client import LLMClient
from agent_harness.compaction import ChatCompactor
from agent_harness.config import Config, ModelConfig
from agent_harness.context import ContextManager
from agent_harness.events import StreamEvent, StreamEventType, TextDelta, TokenUsage


def run(coroutine):
    return asyncio.run(coroutine)


def test_pruner_keeps_system_and_protected_tail(tmp_path):
    manager = ContextManager(
        Config(cwd=tmp_path, model=ModelConfig(context_window=100)),
        compaction_threshold=0.5,
        keep_last=2,
    )
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old user " + "x" * 80},
        {"role": "tool", "tool_call_id": "old", "content": "tool result " + "x" * 200},
        {"role": "assistant", "content": "old answer " + "x" * 80},
        {"role": "user", "content": "protected user"},
        {"role": "assistant", "content": "protected answer"},
    ]

    pruned = manager.prune_messages(messages)

    assert pruned[0] == messages[0]
    assert pruned[-2:] == messages[-2:]
    assert all(message.get("tool_call_id") != "old" for message in pruned)


def test_context_thresholds_use_prompt_tokens(tmp_path):
    manager = ContextManager(Config(cwd=tmp_path, model=ModelConfig(context_window=100)))
    manager.update_token_count(TokenUsage(prompt_tokens=91))

    assert manager.needs_compaction() is True
    assert manager.needs_pruning() is True
    assert manager.get_context_stats()["usage_percent"] == 91.0


class FakeSummaryClient(LLMClient):
    def __init__(self):
        self.calls = 0

    async def chat_completion(self, messages, stream=False):
        self.calls += 1
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=TextDelta("- kept fact"),
        )


def test_compaction_is_idempotent_for_an_existing_summary(tmp_path):
    client = FakeSummaryClient()
    compactor = ChatCompactor(client, Config(cwd=tmp_path))
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old fact"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "recent"},
    ]

    compacted = run(compactor.compact(messages, keep_last=1))
    compacted_again = run(compactor.compact(compacted, keep_last=1))

    assert compacted_again == compacted
    assert client.calls == 1
