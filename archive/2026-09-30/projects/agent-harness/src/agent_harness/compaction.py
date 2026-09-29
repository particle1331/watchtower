"""Context compaction via LLM-powered conversation summarization.

When the conversation history grows too long, the compactor summarizes
older messages into a concise summary and replaces them, keeping the
system prompt and recent messages intact.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_harness.client import LLMClient
from agent_harness.config import Config
from agent_harness.events import StreamEventType

logger = logging.getLogger(__name__)

_MAX_MESSAGE_CHARS = 2000

_SUMMARIZER_SYSTEM_PROMPT = (
    "You are a conversation summarizer for a coding agent session. "
    "Your job is to produce a concise, accurate summary of a conversation "
    "between a user and an AI coding assistant.\n\n"
    "Guidelines:\n"
    "- Summarize the key actions taken, files modified, and decisions made.\n"
    "- Preserve important details like file paths, error messages, and short code snippets.\n"
    "- Note any unresolved issues or pending tasks.\n"
    "- Keep the summary under 500 words.\n"
    "- Use bullet points for clarity."
)

_SUMMARY_PREFIX = "[Context Summary]"


class ChatCompactor:
    """Compacts conversation history by summarizing old messages with the LLM.

    When the message list grows beyond a manageable size, :meth:`compact`
    replaces the middle portion of the conversation with a single summary
    message produced by the LLM, preserving the system prompt and recent
    messages.
    """

    def __init__(self, client: LLMClient, config: Config) -> None:
        self.client = client
        self.config = config

    async def compact(
        self,
        messages: list[dict[str, Any]],
        keep_last: int = 10,
    ) -> list[dict[str, Any]]:
        """Compact conversation history by summarizing older messages.

        Keeps the system message and the last *keep_last* messages. Everything
        in between is replaced with a single summary message.

        Parameters
        ----------
        messages : list[dict]
            Full conversation message list (system prompt at index 0).
        keep_last : int
            Number of recent messages to preserve verbatim.

        Returns
        -------
        list[dict]
            Compacted message list: ``[system_msg, summary_msg, ...tail]``.
        """
        if len(messages) <= keep_last + 1:
            logger.debug(
                "Not enough messages to compact (%d <= %d + 1); skipping.",
                len(messages),
                keep_last,
            )
            return messages

        system_msg = messages[0]
        tail = messages[-keep_last:] if keep_last else []
        middle_end = -keep_last if keep_last else None
        middle = messages[1:middle_end]

        if not middle:
            logger.debug("No middle messages to summarize; skipping compaction.")
            return messages

        # A previous compaction already represents this whole eligible span.
        if len(middle) == 1 and str(middle[0].get("content", "")).startswith(_SUMMARY_PREFIX):
            return messages

        logger.debug(
            "Compacting %d middle messages (keeping system + %d tail).",
            len(middle),
            len(tail),
        )

        summary = await self._summarize(middle)
        summary_msg: dict[str, Any] = {
            "role": "user",
            "content": (
                f"{_SUMMARY_PREFIX}\n\n{summary}\n\n"
                "[End of Summary — conversation continues below]"
            ),
        }

        return [system_msg, summary_msg, *tail]

    async def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """Summarize a list of messages using a non-streaming LLM call.

        On provider failure, a short fallback notice is returned so compaction
        does not erase the fact that earlier messages existed.
        """
        prompt = self._build_summarization_prompt(messages)

        summary = ""
        async for event in self.client.chat_completion(prompt, stream=False):
            if event.type == StreamEventType.MESSAGE_COMPLETE and event.text_delta is not None:
                summary = event.text_delta.content
            elif event.type == StreamEventType.ERROR:
                logger.error("Summarization LLM call failed: %s", event.error)
                summary = (
                    "Earlier conversation could not be summarized due to an error. "
                    f"The conversation included {len(messages)} messages."
                )

        return summary

    def _build_summarization_prompt(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build the message list for the summarization LLM call.

        Each original message is formatted as ``[role]: content`` and very
        long messages are truncated to keep the prompt reasonable.
        """
        formatted_parts: list[str] = []
        for message in messages:
            role = message.get("role", "unknown")
            content = message.get("content", "") or ""

            if not content and "tool_calls" in message:
                tool_names = [
                    tool_call.get("function", {}).get("name", "unknown")
                    for tool_call in message.get("tool_calls", [])
                ]
                content = f"[tool calls: {', '.join(tool_names)}]"

            if len(content) > _MAX_MESSAGE_CHARS:
                content = content[:_MAX_MESSAGE_CHARS] + " [... truncated]"

            formatted_parts.append(f"[{role}]: {content}")

        formatted_messages = "\n\n".join(formatted_parts)
        return [
            {"role": "system", "content": _SUMMARIZER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Summarize the following conversation:\n\n{formatted_messages}",
            },
        ]
