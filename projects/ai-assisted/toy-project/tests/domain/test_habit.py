"""Tests for habit name validation, Habit and CheckIn, duplicate check-ins, and the day guard."""

import dataclasses
import datetime
import unittest

from habits.domain.errors import DomainError, DuplicateCheckIn, InvalidHabitName
from habits.domain.habit import CheckIn, Habit, record_check_in, validate_habit_name

DAY = datetime.date(2026, 10, 9)


class ValidateHabitNameTests(unittest.TestCase):
    def test_strips_surrounding_whitespace(self):
        self.assertEqual(validate_habit_name("  Read books \t\n"), "Read books")

    def test_empty_name_is_rejected(self):
        with self.assertRaises(InvalidHabitName):
            validate_habit_name("")

    def test_whitespace_only_name_is_rejected(self):
        with self.assertRaises(InvalidHabitName):
            validate_habit_name(" \t  ")

    def test_sixty_characters_is_accepted(self):
        name = "a" * 60
        self.assertEqual(validate_habit_name(name), name)

    def test_sixty_one_characters_is_rejected(self):
        with self.assertRaises(InvalidHabitName):
            validate_habit_name("a" * 61)

    def test_length_limit_applies_after_stripping(self):
        self.assertEqual(validate_habit_name("  " + "a" * 60 + "  "), "a" * 60)
        with self.assertRaises(InvalidHabitName):
            validate_habit_name("  " + "a" * 61 + "  ")


class HabitTests(unittest.TestCase):
    def test_stores_stripped_name(self):
        self.assertEqual(Habit(name="  Meditate ").name, "Meditate")

    def test_new_habit_has_no_id(self):
        self.assertIsNone(Habit(name="Meditate").id)

    def test_invalid_name_is_rejected_on_construction(self):
        with self.assertRaises(InvalidHabitName):
            Habit(name="   ")

    def test_habit_is_immutable(self):
        habit = Habit(name="Meditate")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            habit.name = "Run"


class DomainErrorTests(unittest.TestCase):
    def test_rule_violations_derive_from_domain_error(self):
        self.assertTrue(issubclass(InvalidHabitName, DomainError))
        self.assertTrue(issubclass(DuplicateCheckIn, DomainError))


class RecordCheckInTests(unittest.TestCase):
    def test_duplicate_check_in_is_rejected(self):
        existing = [CheckIn(habit_id=1, day=DAY)]
        with self.assertRaises(DuplicateCheckIn):
            record_check_in(1, DAY, existing)

    def test_same_habit_on_a_different_day_is_allowed(self):
        existing = [CheckIn(habit_id=1, day=DAY)]
        next_day = DAY + datetime.timedelta(days=1)
        self.assertEqual(record_check_in(1, next_day, existing), CheckIn(habit_id=1, day=next_day))

    def test_different_habit_on_the_same_day_is_allowed(self):
        existing = [CheckIn(habit_id=1, day=DAY)]
        self.assertEqual(record_check_in(2, DAY, existing), CheckIn(habit_id=2, day=DAY))


class RecordCheckInDayTypeTests(unittest.TestCase):
    def test_datetime_is_rejected(self):
        with self.assertRaises(TypeError):
            record_check_in(1, datetime.datetime(2026, 10, 9, 8, 30), [])

    def test_datetime_is_rejected_even_when_its_date_is_already_checked_in(self):
        existing = [CheckIn(habit_id=1, day=DAY)]
        with self.assertRaises(TypeError):
            record_check_in(1, datetime.datetime(2026, 10, 9), existing)

    def test_string_day_is_rejected(self):
        with self.assertRaises(TypeError):
            record_check_in(1, "2026-10-09", [])

    def test_none_day_is_rejected(self):
        with self.assertRaises(TypeError):
            record_check_in(1, None, [])

    def test_date_is_accepted(self):
        self.assertEqual(record_check_in(1, DAY, []), CheckIn(habit_id=1, day=DAY))
