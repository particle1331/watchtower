"""Contract every HabitRepository adapter must satisfy.

Adapter test modules mix HabitRepositoryContract into a unittest.TestCase and implement
make_repository(). This module is not named test*.py, so unittest does not run it directly.
"""

import abc
import datetime

from habits.domain.habit import CheckIn, Habit

DAY = datetime.date(2026, 10, 9)


class HabitRepositoryContract(metaclass=abc.ABCMeta):
    """Test methods shared by all adapters. It is not a TestCase, so it cannot run on its own."""

    @abc.abstractmethod
    def make_repository(self):
        """Return a new, empty repository for one test."""

    def test_save_habit_without_an_id_assigns_one(self):
        repo = self.make_repository()
        habit = Habit(name="Read")
        saved = repo.save_habit(habit)
        self.assertIsNotNone(saved.id)
        self.assertEqual(saved.name, "Read")
        self.assertIsNone(habit.id)

    def test_saved_habit_can_be_fetched_by_id(self):
        repo = self.make_repository()
        saved = repo.save_habit(Habit(name="Read"))
        self.assertEqual(repo.get_habit(saved.id), saved)

    def test_get_habit_with_an_unknown_id_is_none(self):
        self.assertIsNone(self.make_repository().get_habit(999))

    def test_save_habit_with_an_id_returns_the_stored_habit_without_inserting(self):
        repo = self.make_repository()
        saved = repo.save_habit(Habit(name="Read"))
        self.assertEqual(repo.save_habit(saved), saved)
        self.assertEqual(repo.list_habits(), [saved])

    def test_save_habit_with_an_unknown_id_raises_key_error(self):
        repo = self.make_repository()
        with self.assertRaises(KeyError):
            repo.save_habit(Habit(name="Read", id=999))

    def test_list_habits_is_empty_for_a_new_repository(self):
        self.assertEqual(self.make_repository().list_habits(), [])

    def test_list_habits_is_ordered_by_id_ascending(self):
        repo = self.make_repository()
        first = repo.save_habit(Habit(name="Read"))
        second = repo.save_habit(Habit(name="Run"))
        third = repo.save_habit(Habit(name="Meditate"))
        self.assertEqual(repo.list_habits(), [first, second, third])

    def test_saved_check_in_is_returned_for_its_habit(self):
        repo = self.make_repository()
        habit = repo.save_habit(Habit(name="Read"))
        check_in = CheckIn(habit_id=habit.id, day=DAY)
        self.assertIsNone(repo.save_check_in(check_in))
        self.assertEqual(repo.check_ins_for(habit.id), [check_in])

    def test_check_ins_are_returned_only_for_their_habit(self):
        repo = self.make_repository()
        read = repo.save_habit(Habit(name="Read"))
        run = repo.save_habit(Habit(name="Run"))
        read_in = CheckIn(habit_id=read.id, day=DAY)
        repo.save_check_in(read_in)
        repo.save_check_in(CheckIn(habit_id=run.id, day=DAY))
        self.assertEqual(repo.check_ins_for(read.id), [read_in])

    def test_check_ins_are_ordered_by_day_ascending(self):
        repo = self.make_repository()
        habit = repo.save_habit(Habit(name="Read"))
        for day in [DAY, datetime.date(2026, 1, 5), datetime.date(2025, 12, 31)]:
            repo.save_check_in(CheckIn(habit_id=habit.id, day=day))
        self.assertEqual(
            [check_in.day for check_in in repo.check_ins_for(habit.id)],
            [datetime.date(2025, 12, 31), datetime.date(2026, 1, 5), DAY],
        )

    def test_habit_without_check_ins_has_none(self):
        repo = self.make_repository()
        habit = repo.save_habit(Habit(name="Read"))
        self.assertEqual(repo.check_ins_for(habit.id), [])
        self.assertEqual(repo.check_ins_for(999), [])

    def test_duplicate_check_in_is_rejected_by_every_adapter(self):
        from habits.domain.errors import DuplicateCheckIn

        repo = self.make_repository()
        habit = repo.save_habit(Habit(name="Read"))
        repo.save_check_in(CheckIn(habit_id=habit.id, day=DAY))
        with self.assertRaises(DuplicateCheckIn):
            repo.save_check_in(CheckIn(habit_id=habit.id, day=DAY))
        self.assertEqual(len(repo.check_ins_for(habit.id)), 1)
