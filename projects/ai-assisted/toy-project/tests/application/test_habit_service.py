"""Use-case tests for HabitService, run against the in-memory adapter."""

import datetime
import unittest

from habits.adapters.memory_repository import InMemoryHabitRepository
from habits.application.habit_service import HabitService, HabitSummary
from habits.domain.errors import DuplicateCheckIn, HabitNotFound, InvalidHabitName
from habits.domain.habit import Habit

TODAY = datetime.date(2026, 10, 9)


def day_offset(days: int) -> datetime.date:
    return TODAY + datetime.timedelta(days=days)


class HabitServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryHabitRepository()
        self.service = HabitService(self.repo)

    def test_add_habit_returns_stored_habit_with_id(self):
        habit = self.service.add_habit("  Read  ")
        self.assertEqual(habit, Habit(name="Read", id=1))
        self.assertEqual(self.repo.get_habit(1), habit)

    def test_add_habit_rejects_invalid_name_and_stores_nothing(self):
        with self.assertRaises(InvalidHabitName):
            self.service.add_habit("   ")
        self.assertEqual(self.repo.list_habits(), [])

    def test_check_in_stores_check_in(self):
        habit = self.service.add_habit("Read")
        check_in = self.service.check_in(habit.id, TODAY)
        self.assertEqual(check_in.habit_id, habit.id)
        self.assertEqual(self.repo.check_ins_for(habit.id), [check_in])

    def test_check_in_for_missing_habit_raises_not_found(self):
        with self.assertRaises(HabitNotFound):
            self.service.check_in(42, TODAY)

    def test_duplicate_check_in_on_same_day_raises(self):
        habit = self.service.add_habit("Read")
        self.service.check_in(habit.id, TODAY)
        with self.assertRaises(DuplicateCheckIn):
            self.service.check_in(habit.id, TODAY)
        self.assertEqual(len(self.repo.check_ins_for(habit.id)), 1)

    def test_list_shows_zero_streak_for_new_habit(self):
        self.service.add_habit("Read")
        self.assertEqual(self.service.list_habits(TODAY), [
            HabitSummary(habit=Habit(name="Read", id=1), streak=0),
        ])

    def test_list_counts_streak_to_today(self):
        habit = self.service.add_habit("Read")
        for offset in (-2, -1, 0):
            self.service.check_in(habit.id, day_offset(offset))
        summaries = self.service.list_habits(TODAY)
        self.assertEqual(summaries[0].streak, 3)

    def test_list_is_ordered_by_id(self):
        first = self.service.add_habit("Read")
        second = self.service.add_habit("Run")
        ids = [summary.habit.id for summary in self.service.list_habits(TODAY)]
        self.assertEqual(ids, [first.id, second.id])


if __name__ == "__main__":
    unittest.main()


class ExportTest(unittest.TestCase):
    def test_export_includes_every_habit_with_sorted_check_in_days(self):
        repo = InMemoryHabitRepository()
        service = HabitService(repo)
        read = service.add_habit("Read")
        run = service.add_habit("Run")
        service.check_in(read.id, day_offset(-1))
        service.check_in(read.id, day_offset(-3))
        exported = service.export_all()
        self.assertEqual([item.habit.name for item in exported], ["Read", "Run"])
        self.assertEqual(exported[0].check_in_days, [day_offset(-3), day_offset(-1)])
        self.assertEqual(exported[1].check_in_days, [])
