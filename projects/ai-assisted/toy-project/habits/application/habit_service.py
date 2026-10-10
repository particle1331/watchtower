"""Use cases for habits. The service never reads the clock: every date is a parameter."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List

from habits.application.ports import HabitRepository
from habits.domain.errors import HabitNotFound
from habits.domain.habit import CheckIn, Habit, record_check_in
from habits.domain.streaks import current_streak


@dataclass(frozen=True)
class HabitSummary:
    habit: Habit
    streak: int


@dataclass(frozen=True)
class HabitExport:
    habit: Habit
    check_in_days: List[datetime.date]


class HabitService:
    def __init__(self, repository: HabitRepository) -> None:
        self._repository = repository

    def add_habit(self, name: str) -> Habit:
        """Validate the name and store the habit. Raises InvalidHabitName for a bad name."""
        return self._repository.save_habit(Habit(name=name))

    def check_in(self, habit_id: int, day: datetime.date) -> CheckIn:
        """Record a check-in. Raises HabitNotFound or DuplicateCheckIn when it cannot be stored."""
        if self._repository.get_habit(habit_id) is None:
            raise HabitNotFound(f"no habit with id {habit_id}")
        existing = self._repository.check_ins_for(habit_id)
        check_in = record_check_in(habit_id, day, existing)
        self._repository.save_check_in(check_in)
        return check_in

    def list_habits(self, today: datetime.date) -> List[HabitSummary]:
        """Return every habit in id order, with its current streak as of today."""
        summaries = []
        for habit in self._repository.list_habits():
            days = [check_in.day for check_in in self._repository.check_ins_for(habit.id)]
            summaries.append(HabitSummary(habit=habit, streak=current_streak(days, today)))
        return summaries

    def export_all(self) -> List[HabitExport]:
        """Return every habit with all of its check-in days, in id order and day order."""
        return [
            HabitExport(
                habit=habit,
                check_in_days=[check_in.day for check_in in self._repository.check_ins_for(habit.id)],
            )
            for habit in self._repository.list_habits()
        ]
