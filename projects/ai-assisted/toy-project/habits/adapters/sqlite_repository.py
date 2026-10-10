"""SQLite implementation of the HabitRepository port. Days are stored as ISO-8601 text."""

from __future__ import annotations

import datetime
import sqlite3
from typing import List, Optional

from habits.domain.errors import DuplicateCheckIn
from habits.domain.habit import CheckIn, Habit

SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS check_ins (
    habit_id INTEGER NOT NULL REFERENCES habits(id),
    day TEXT NOT NULL,
    PRIMARY KEY (habit_id, day)
);
"""


class SqliteHabitRepository:
    """Stores habits and check-ins in a SQLite file, or in memory when given ":memory:"."""

    def __init__(self, path: str) -> None:
        self._connection = sqlite3.connect(path)
        # SQLite leaves foreign keys off by default; the schema's REFERENCES clause does nothing without this.
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def save_habit(self, habit: Habit) -> Habit:
        if habit.id is not None:
            stored = self.get_habit(habit.id)
            if stored is None:
                raise KeyError(habit.id)
            return stored
        with self._connection:
            cursor = self._connection.execute("INSERT INTO habits (name) VALUES (?)", (habit.name,))
        return Habit(name=habit.name, id=cursor.lastrowid)

    def get_habit(self, habit_id: int) -> Optional[Habit]:
        row = self._connection.execute(
            "SELECT id, name FROM habits WHERE id = ?", (habit_id,)
        ).fetchone()
        return None if row is None else Habit(name=row[1], id=row[0])

    def list_habits(self) -> List[Habit]:
        rows = self._connection.execute("SELECT id, name FROM habits ORDER BY id ASC").fetchall()
        return [Habit(name=row[1], id=row[0]) for row in rows]

    def save_check_in(self, check_in: CheckIn) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO check_ins (habit_id, day) VALUES (?, ?)",
                    (check_in.habit_id, check_in.day.isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            # The primary key (habit_id, day) is the database's duplicate rule. Other integrity
            # failures, such as a missing habit, are not duplicates and are re-raised unchanged.
            if "UNIQUE constraint failed" in str(exc):
                raise DuplicateCheckIn(
                    f"habit {check_in.habit_id} is already checked in for {check_in.day.isoformat()}"
                ) from exc
            raise

    def check_ins_for(self, habit_id: int) -> List[CheckIn]:
        rows = self._connection.execute(
            "SELECT habit_id, day FROM check_ins WHERE habit_id = ? ORDER BY day ASC", (habit_id,)
        ).fetchall()
        return [CheckIn(habit_id=row[0], day=datetime.date.fromisoformat(row[1])) for row in rows]
