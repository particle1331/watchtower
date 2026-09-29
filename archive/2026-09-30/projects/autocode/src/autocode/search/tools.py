"""Harness-facing search functions; the agent loop does not need to change."""

from __future__ import annotations

from typing import Any

from autocode.search.index import LocalSearchIndex


def search_code(index: LocalSearchIndex, query: str, limit: int = 5) -> list[dict[str, Any]]:
    return [hit.__dict__ for hit in index.search(query, limit=limit, method="hybrid")]


def search_history(index: LocalSearchIndex, query: str, limit: int = 5) -> list[dict[str, Any]]:
    return [hit.__dict__ for hit in index.search(query, limit=limit, method="lexical")]
