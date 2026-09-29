"""Versioned schema seam for rehearsed upgrades and downgrades."""

from __future__ import annotations

import sqlite3
from typing import Protocol


class Migration(Protocol):
    version: int

    def upgrade(self, connection: sqlite3.Connection) -> None: ...

    def downgrade(self, connection: sqlite3.Connection) -> None: ...


class AddSessionSummary:
    version = 2

    def upgrade(self, connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE sessions ADD COLUMN summary TEXT NOT NULL DEFAULT ''")

    def downgrade(self, connection: sqlite3.Connection) -> None:
        # SQLite cannot drop a column on every supported version. A production
        # migration would rebuild the table; the downgrade must still be tested.
        connection.execute("CREATE TABLE sessions_v1 AS SELECT session_id, title, config_hash, version, updated_at FROM sessions")
        connection.execute("DROP TABLE sessions")
        connection.execute("ALTER TABLE sessions_v1 RENAME TO sessions")


MIGRATIONS: tuple[Migration, ...] = (AddSessionSummary(),)
