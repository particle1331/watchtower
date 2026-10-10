"""Tests for the SQLite adapter: the shared contract, a duplicate backstop, and persistence."""

import os
import sqlite3
import tempfile
import unittest

from habits.adapters.sqlite_repository import SqliteHabitRepository
from habits.domain.habit import CheckIn, Habit
from tests.adapters.repository_contract import DAY, HabitRepositoryContract


class SqliteHabitRepositoryContractTests(HabitRepositoryContract, unittest.TestCase):
    def make_repository(self):
        repo = SqliteHabitRepository(":memory:")
        self.addCleanup(repo.close)
        return repo

    def test_duplicate_is_translated_not_leaked_as_integrity_error(self):
        from habits.domain.errors import DuplicateCheckIn

        repo = self.make_repository()
        habit = repo.save_habit(Habit(name="Read"))
        repo.save_check_in(CheckIn(habit_id=habit.id, day=DAY))
        with self.assertRaises(DuplicateCheckIn):
            repo.save_check_in(CheckIn(habit_id=habit.id, day=DAY))


class SqlitePersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "habits.db")

    def test_data_survives_closing_and_reopening_the_file(self):
        first = SqliteHabitRepository(self.path)
        habit = first.save_habit(Habit(name="Read"))
        first.save_check_in(CheckIn(habit_id=habit.id, day=DAY))
        first.close()

        reopened = SqliteHabitRepository(self.path)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.list_habits(), [habit])
        self.assertEqual(reopened.check_ins_for(habit.id), [CheckIn(habit_id=habit.id, day=DAY)])
        self.assertEqual(reopened.save_habit(Habit(name="Run")).id, habit.id + 1)

    def test_close_releases_the_connection(self):
        repo = SqliteHabitRepository(":memory:")
        repo.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            repo.list_habits()
