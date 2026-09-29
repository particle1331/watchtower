"""Append-only write-ahead journal.

The journal is deliberately boring: JSON Lines, a flush, and an fsync. It is
the first durable boundary before the SQLite projection or an external side
effect is acknowledged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Journal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            # The caller can now safely retry projecting this event.
            import os

            os.fsync(handle.fileno())

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

    def compact(self, records: list[dict[str, Any]]) -> None:
        replacement = self.path.with_suffix(".compact")
        replacement.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        replacement.replace(self.path)
