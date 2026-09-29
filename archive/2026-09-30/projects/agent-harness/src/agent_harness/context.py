"""Context window management for the coding agent.

Tracks token usage, detects when the context window is getting full,
and prunes old messages to stay within limits. The actual compaction
logic (LLM-based summarization) lives in ``compaction.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_harness.config import Config
from agent_harness.events import TokenUsage

logger = logging.getLogger(__name__)

_DEFAULT_KEEP_LAST: int = 10


class ContextManager:
    """Tracks context window usage and triggers pruning/compaction.

    Parameters
    ----------
    config : Config
        Agent configuration; ``config.context_window`` gives the model's
        maximum context length in tokens.
    compaction_threshold : float
        Fraction of the context window at which compaction is suggested.
    pruning_threshold : float
        Fraction of the context window at which hard pruning is triggered.
    keep_last : int
        Number of most-recent messages that are always preserved.
    """

    def __init__(
        self,
        config: Config,
        compaction_threshold: float = 0.8,
        pruning_threshold: float = 0.9,
        keep_last: int = _DEFAULT_KEEP_LAST,
    ) -> None:
        self.config = config
        self.token_count: int = 0
        self.compaction_threshold: float = compaction_threshold
        self.pruning_threshold: float = pruning_threshold
        self.keep_last: int = keep_last

    def update_token_count(self, usage: TokenUsage) -> None:
        """Update the current token count from LLM usage stats."""
        self.token_count = usage.prompt_tokens
        logger.debug(
            "Context token count updated: %d / %d (%.1f%%)",
            self.token_count,
            self.config.context_window,
            self._usage_percent(),
        )

    def needs_compaction(self) -> bool:
        """Return ``True`` if the context exceeds the compaction threshold."""
        return self.token_count > self.compaction_threshold * self.config.context_window

    def needs_pruning(self) -> bool:
        """Return ``True`` if the context exceeds the hard-pruning threshold."""
        return self.token_count > self.pruning_threshold * self.config.context_window

    @staticmethod
    def estimate_message_tokens(message: dict[str, Any]) -> int:
        """Estimate token count using one token per four characters plus overhead."""
        content = str(message.get("content", ""))
        return len(content) // 4 + 10

    def prune_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a pruned copy of *messages* that fits the context budget.

        Strategy
        --------
        1. The system message (index 0) is always kept.
        2. The last ``keep_last`` messages are always kept.
        3. Among the remaining middle messages, tool-result messages are
           removed first, then old assistant messages.
        4. Removal continues until the estimated total drops below the
           compaction threshold, or there is nothing left to remove.
        """
        if len(messages) <= 1 + self.keep_last:
            logger.debug("Too few messages to prune (%d), returning as-is.", len(messages))
            return list(messages)

        system = messages[:1]
        tail = messages[-self.keep_last :] if self.keep_last else []
        middle_end = -self.keep_last if self.keep_last else None
        middle = messages[1:middle_end]
        target_tokens = int(self.compaction_threshold * self.config.context_window)

        def total_estimate(items: list[dict[str, Any]]) -> int:
            return sum(self.estimate_message_tokens(message) for message in items)

        kept_middle: list[dict[str, Any]] = []
        for message in middle:
            if message.get("role") == "tool":
                logger.debug("Pruning tool message (call_id=%s).", message.get("tool_call_id", "?"))
                continue
            kept_middle.append(message)

        current = total_estimate(system + kept_middle + tail)
        if current <= target_tokens:
            return system + kept_middle + tail

        pruned_middle = list(kept_middle)
        while pruned_middle and total_estimate(system + pruned_middle + tail) > target_tokens:
            assistant_index = next(
                (
                    index
                    for index, message in enumerate(pruned_middle)
                    if message.get("role") == "assistant"
                ),
                None,
            )
            if assistant_index is None:
                break
            logger.debug("Pruning old assistant message.")
            pruned_middle.pop(assistant_index)

        result = system + pruned_middle + tail
        logger.debug(
            "Pruning finished: %d -> %d messages (~%d tokens est.).",
            len(messages),
            len(result),
            total_estimate(result),
        )
        return result

    def get_context_stats(self) -> dict[str, Any]:
        """Return a snapshot of context-window usage."""
        return {
            "token_count": self.token_count,
            "context_window": self.config.context_window,
            "usage_percent": round(self._usage_percent(), 2),
            "needs_compaction": self.needs_compaction(),
            "needs_pruning": self.needs_pruning(),
        }

    def _usage_percent(self) -> float:
        """Context usage as a percentage (0-100)."""
        window = self.config.context_window
        if window <= 0:
            return 0.0
        return (self.token_count / window) * 100.0
