"""Conversation state for a single agent session.

Wires together the LLM client, tool registry, and message history.
The session is a data holder with convenience methods; it does NOT
drive the agentic loop (that responsibility belongs to the Agent class).

Sessions can be serialized to / from JSON for persistence::

    data = session.to_dict()
    Session.from_dict(data, config)   # restore from a saved dict

The default save directory is ``~/.cda/sessions/``.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_harness.client import LLMClient
from agent_harness.config import Config
from agent_harness.events import TokenUsage, ToolResultMessage
from agent_harness.prompts import build_system_prompt
from agent_harness.tools.base import ToolRegistry, create_default_registry

SESSIONS_DIR = Path.home() / ".cda" / "sessions"


class Session:
    """Manages conversation state for a single agent session.

    Parameters
    ----------
    config : Config
        Agent configuration (model settings, working directory, etc.).
    client : LLMClient | None
        LLM client for chat completions. A default is created from *config*
        when ``None``.
    registry : ToolRegistry | None
        Tool registry. The default builtin registry is created from *config*
        when ``None``.
    """

    def __init__(
        self,
        config: Config,
        client: LLMClient | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.config = config
        self.client = client if client is not None else LLMClient(config)
        self.registry = registry if registry is not None else create_default_registry(config)
        self._system_prompt = build_system_prompt(config, self.registry.get_tools())
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
        ]
        self.total_usage: TokenUsage = TokenUsage()
        self.turn_count: int = 0
        # Journal entries are append-only actions sufficient to reconstruct state.
        self.journal: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    #  Message helpers                                                     #
    # ------------------------------------------------------------------ #

    def add_user_message(self, content: str) -> None:
        """Append a user message to the conversation history."""
        self.messages.append({"role": "user", "content": content})
        self._record("user_message", content=content)

    def add_assistant_message(
        self,
        content: str,
        tool_calls: list[dict] | None = None,
    ) -> None:
        """Append an assistant message, optionally with tool calls.

        Each tool-call dict should contain ``id``, ``name``, and
        ``arguments``. Arguments may be a dict or an already serialized string.
        """
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls is not None:
            message["tool_calls"] = [
                {
                    "id": tool_call["id"],
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": (
                            json.dumps(tool_call["arguments"])
                            if isinstance(tool_call["arguments"], dict)
                            else tool_call["arguments"]
                        ),
                    },
                }
                for tool_call in tool_calls
            ]
        self.messages.append(message)
        self._record(
            "assistant_message",
            content=content,
            tool_calls=copy.deepcopy(tool_calls),
        )

    def add_tool_result(self, tool_result: ToolResultMessage) -> None:
        """Append a tool result message to the conversation history."""
        self.messages.append(tool_result.to_openai_message())
        self._record(
            "tool_result",
            tool_call_id=tool_result.tool_call_id,
            content=tool_result.content,
            is_error=tool_result.is_error,
        )

    # ------------------------------------------------------------------ #
    #  Accessors                                                           #
    # ------------------------------------------------------------------ #

    def get_messages(self) -> list[dict[str, Any]]:
        """Return the full message list."""
        return self.messages

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return tool schemas for the current registry."""
        return self.registry.get_schemas()

    @property
    def system_prompt(self) -> str:
        """Return the current system prompt (first message content)."""
        return self.messages[0]["content"]

    # ------------------------------------------------------------------ #
    #  Tracking                                                            #
    # ------------------------------------------------------------------ #

    def track_usage(self, usage: TokenUsage) -> None:
        """Accumulate token usage from a single LLM call."""
        self.total_usage = self.total_usage + usage
        self._record("usage", usage=copy.deepcopy(usage.__dict__))

    def start_turn(self) -> int:
        """Advance and journal the turn counter, returning its new value."""
        self.turn_count += 1
        self._record("turn", count=self.turn_count)
        return self.turn_count

    # ------------------------------------------------------------------ #
    #  Reset                                                               #
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Clear conversation back to the initial system prompt."""
        self.messages = [{"role": "system", "content": self._system_prompt}]
        self.turn_count = 0
        self.total_usage = TokenUsage()
        self._record("reset")

    # ------------------------------------------------------------------ #
    #  Journal replay                                                      #
    # ------------------------------------------------------------------ #

    def _record(self, event_type: str, **data: Any) -> None:
        self.journal.append({"type": event_type, **data})

    @classmethod
    def replay(
        cls,
        journal: list[dict[str, Any]] | dict[str, Any],
        config: Config,
        client: LLMClient | None = None,
        registry: ToolRegistry | None = None,
    ) -> Session:
        """Reconstruct a session from an append-only journal.

        A serialized session dict is accepted as a convenience; its ``journal``
        field is replayed. Unknown entries are ignored so newer journal records
        remain readable by older clients.
        """
        entries = journal.get("journal", []) if isinstance(journal, dict) else journal
        session = cls(config, client=client, registry=registry)
        session.messages = [{"role": "system", "content": session._system_prompt}]
        session.total_usage = TokenUsage()
        session.turn_count = 0
        for entry in entries:
            session._apply_journal_entry(entry)
        session.journal = copy.deepcopy(entries)
        return session

    @classmethod
    def from_journal(
        cls,
        journal: list[dict[str, Any]],
        config: Config,
        client: LLMClient | None = None,
        registry: ToolRegistry | None = None,
    ) -> Session:
        """Alias for :meth:`replay` with an explicit journal-oriented name."""
        return cls.replay(journal, config, client=client, registry=registry)

    def _apply_journal_entry(self, entry: dict[str, Any]) -> None:
        event_type = entry.get("type")
        if event_type == "user_message":
            self.messages.append({"role": "user", "content": entry.get("content", "")})
        elif event_type == "assistant_message":
            self._append_assistant_message(
                entry.get("content", ""),
                entry.get("tool_calls"),
            )
        elif event_type == "tool_result":
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": entry.get("tool_call_id", ""),
                    "content": entry.get("content", ""),
                }
            )
        elif event_type == "usage":
            usage = entry.get("usage", {})
            self.total_usage = self.total_usage + TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                cached_tokens=usage.get("cached_tokens", 0),
            )
        elif event_type == "turn":
            self.turn_count = entry.get("count", self.turn_count)
        elif event_type == "reset":
            self.messages = [{"role": "system", "content": self._system_prompt}]
            self.total_usage = TokenUsage()
            self.turn_count = 0

    def _append_assistant_message(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None,
    ) -> None:
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls is not None:
            message["tool_calls"] = [
                {
                    "id": tool_call["id"],
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": (
                            json.dumps(tool_call["arguments"])
                            if isinstance(tool_call["arguments"], dict)
                            else tool_call["arguments"]
                        ),
                    },
                }
                for tool_call in tool_calls
            ]
        self.messages.append(message)

    # ------------------------------------------------------------------ #
    #  Persistence                                                         #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Serialize session state to a JSON-compatible dict.

        The serialized form stores the full message history, token usage, and
        append-only journal. Configuration is not stored; it must be supplied
        again when restoring the session.
        """
        return {
            "version": 1,
            "saved_at": datetime.now(UTC).isoformat(),
            "turn_count": self.turn_count,
            "total_usage": {
                "prompt_tokens": self.total_usage.prompt_tokens,
                "completion_tokens": self.total_usage.completion_tokens,
                "total_tokens": self.total_usage.total_tokens,
                "cached_tokens": self.total_usage.cached_tokens,
            },
            "messages": self.messages,
            "journal": self.journal,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        config: Config,
        client: LLMClient | None = None,
        registry: ToolRegistry | None = None,
    ) -> Session:
        """Restore a session from a previously serialized dict.

        Older snapshots without a journal remain readable and retain their
        original full-message restore behavior.
        """
        session = cls(config, client=client, registry=registry)
        session.messages = data["messages"]
        session.turn_count = data.get("turn_count", 0)
        usage = data.get("total_usage", {})
        session.total_usage = TokenUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cached_tokens=usage.get("cached_tokens", 0),
        )
        session.journal = copy.deepcopy(data.get("journal", []))
        return session

    def save(self, name: str, directory: Path = SESSIONS_DIR) -> Path:
        """Persist this session to *directory*/<name>.json.

        Spaces in *name* are replaced with underscores and the directory is
        created when necessary.
        """
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = name.replace(" ", "_")
        path = directory / f"{safe_name}.json"
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(
        cls,
        name: str,
        config: Config,
        directory: Path = SESSIONS_DIR,
        client: LLMClient | None = None,
        registry: ToolRegistry | None = None,
    ) -> Session:
        """Load a previously saved session from *directory*/<name>.json.

        Raises :class:`FileNotFoundError` when the requested snapshot is absent.
        """
        safe_name = name.replace(" ", "_")
        path = directory / f"{safe_name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data, config, client=client, registry=registry)

    @staticmethod
    def list_saved(directory: Path = SESSIONS_DIR) -> list[str]:
        """Return a sorted list of saved session names in *directory*."""
        if not directory.exists():
            return []
        return sorted(path.stem for path in directory.glob("*.json"))
