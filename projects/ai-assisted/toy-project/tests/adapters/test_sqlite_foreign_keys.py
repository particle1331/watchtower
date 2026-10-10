"""Foreign keys must be enforced by the SQLite adapter (Step 02, review fix B)."""

from __future__ import annotations

import datetime
import sqlite3
import unittest

from habits.adapters.sqlite_repository import SqliteHabitRepository
from habits.domain.habit import CheckIn, Habit


class SqliteForeignKeyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = SqliteHabitRepository(":memory:")

    def tearDown(self) -> None:
        self.repo.close()

    def test_check_in_for_missing_habit_is_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.save_check_in(CheckIn(habit_id=999, day=datetime.date(2026, 10, 1)))

    def test_check_in_for_existing_habit_is_accepted(self) -> None:
        habit = self.repo.save_habit(Habit(name="Read"))
        self.repo.save_check_in(CheckIn(habit_id=habit.id, day=datetime.date(2026, 10, 1)))
        self.assertEqual(len(self.repo.check_ins_for(habit.id)), 1)
