"""Tests for pure streak calculation."""

import datetime
import unittest

from habits.domain.streaks import current_streak

TODAY = datetime.date(2026, 10, 9)


def days_ago(n):
    return TODAY - datetime.timedelta(days=n)


class CurrentStreakTests(unittest.TestCase):
    def test_no_check_ins_is_zero(self):
        self.assertEqual(current_streak([], TODAY), 0)

    def test_only_today_is_one(self):
        self.assertEqual(current_streak([days_ago(0)], TODAY), 1)

    def test_consecutive_days_ending_today_are_all_counted(self):
        self.assertEqual(current_streak([days_ago(0), days_ago(1), days_ago(2)], TODAY), 3)

    def test_only_yesterday_is_one(self):
        self.assertEqual(current_streak([days_ago(1)], TODAY), 1)

    def test_streak_ending_yesterday_still_counts_when_today_is_unchecked(self):
        self.assertEqual(current_streak([days_ago(1), days_ago(2)], TODAY), 2)

    def test_gap_breaks_the_streak(self):
        check_ins = [days_ago(0), days_ago(1), days_ago(3), days_ago(4)]
        self.assertEqual(current_streak(check_ins, TODAY), 2)

    def test_no_check_in_today_or_yesterday_is_zero(self):
        self.assertEqual(current_streak([days_ago(2), days_ago(3)], TODAY), 0)

    def test_repeated_days_are_counted_once(self):
        self.assertEqual(current_streak([days_ago(0), days_ago(0), days_ago(1)], TODAY), 2)
