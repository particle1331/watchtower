"""In-memory key-value store with optional file persistence.

The agent can use this to remember facts, store intermediate results,
or pass data between turns without cluttering the conversation context.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from agent_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult

_DEFAULT_STORE_PATH = Path.home() / ".cda" / "memory.json"


def _load_store(path: Path) -> dict[str, str]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_store(path: Path, store: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


class MemoryParams(BaseModel):
    action: str = Field(
        ...,
        description=(
            "Operation to perform: 'set' (store a value), 'get' (retrieve a value), "
            "'delete' (remove a key), 'list' (show all keys), 'clear' (delete all entries)"
        ),
    )
    key: str | None = Field(None, description="The key to read or write (required for set/get/delete)")
    value: str | None = Field(None, description="The value to store (required for set)")


class MemoryTool(Tool):
    name = "memory"
    kind = ToolKind.MEMORY
    description = (
        "Persistent key-value memory store. Use 'set' to remember facts, 'get' to recall them, "
        "'list' to see all stored keys, 'delete' to remove one, 'clear' to reset. "
        "Memory persists across agent runs."
    )
    schema = MemoryParams

    def _store_path(self) -> Path:
        return _DEFAULT_STORE_PATH

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)
        path = self._store_path()
        store = _load_store(path)

        action = params.action.lower().strip()

        if action == "set":
            if not params.key:
                return ToolResult.error_result("'key' is required for action='set'")
            if params.value is None:
                return ToolResult.error_result("'value' is required for action='set'")
            store[params.key] = params.value
            _save_store(path, store)
            return ToolResult.success_result(f"Stored: {params.key!r} = {params.value!r}")

        if action == "get":
            if not params.key:
                return ToolResult.error_result("'key' is required for action='get'")
            if params.key not in store:
                return ToolResult.error_result(f"Key not found: {params.key!r}")
            return ToolResult.success_result(store[params.key])

        if action == "delete":
            if not params.key:
                return ToolResult.error_result("'key' is required for action='delete'")
            if params.key not in store:
                return ToolResult.error_result(f"Key not found: {params.key!r}")
            del store[params.key]
            _save_store(path, store)
            return ToolResult.success_result(f"Deleted key: {params.key!r}")

        if action == "list":
            if not store:
                return ToolResult.success_result("(memory is empty)")
            lines = [f"{key!r}: {value[:80]}{'…' if len(value) > 80 else ''}" for key, value in store.items()]
            return ToolResult.success_result("\n".join(lines), metadata={"count": len(store)})

        if action == "clear":
            count = len(store)
            _save_store(path, {})
            return ToolResult.success_result(f"Cleared {count} entr{'y' if count == 1 else 'ies'}")

        return ToolResult.error_result(
            f"Unknown action: {params.action!r}. Valid actions: set, get, delete, list, clear"
        )
