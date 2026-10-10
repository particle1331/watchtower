"""CheckIn itself must refuse a datetime, not only record_check_in (Step 02, review fix A)."""

from __future__ import annotations

import datetime
import unittest

from habits.domain.habit import CheckIn


class CheckInDayTest(unittest.TestCase):
    def test_accepts_a_plain_date(self) -> None:
        check_in = CheckIn(habit_id=1, day=datetime.date(2026, 10, 1))
        self.assertEqual(check_in.day, datetime.date(2026, 10, 1))

    def test_rejects_a_datetime(self) -> None:
        with self.assertRaises(TypeError):
            CheckIn(habit_id=1, day=datetime.datetime(2026, 10, 1, 9, 30))

    def test_rejects_a_string(self) -> None:
        with self.assertRaises(TypeError):
            CheckIn(habit_id=1, day="2026-10-01")  # type: ignore[arg-type]
