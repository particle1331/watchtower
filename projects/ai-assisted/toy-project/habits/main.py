"""Composition root: the only place that reads the clock and chooses concrete adapters.

Configuration: the SQLite file is HABITS_DB, or habits.sqlite3 in the working directory.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
import sys
from typing import List, Optional

from habits.adapters.sqlite_repository import SqliteHabitRepository
from habits.application.habit_service import HabitService
from habits.cli import commands

DB_ENV_VAR = "HABITS_DB"
DEFAULT_DB_PATH = "habits.sqlite3"


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = os.environ.get(DB_ENV_VAR, DEFAULT_DB_PATH)
    try:
        repository = SqliteHabitRepository(path)
    except sqlite3.Error as exc:
        print(f"error: cannot open database {path!r}: {exc}", file=sys.stderr)
        return 1
    try:
        service = HabitService(repository)
        return commands.run(argv, service, datetime.date.today())
    finally:
        repository.close()
