"""Habit and CheckIn entities, habit name validation, and the check-in rule."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Iterable, Optional

from habits.domain.errors import DuplicateCheckIn, InvalidHabitName

MAX_NAME_LENGTH = 60


def validate_habit_name(raw: str) -> str:
    """Return the name without surrounding whitespace, or raise InvalidHabitName."""
    name = raw.strip()
    if not name:
        raise InvalidHabitName("habit name must not be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidHabitName(f"habit name must be at most {MAX_NAME_LENGTH} characters")
    return name


@dataclass(frozen=True)
class Habit:
    name: str
    id: Optional[int] = None

    def __post_init__(self) -> None:
        # The dataclass is frozen, so the validated name is written via object.__setattr__.
        object.__setattr__(self, "name", validate_habit_name(self.name))


@dataclass(frozen=True)
class CheckIn:
    habit_id: int
    day: datetime.date

    def __post_init__(self) -> None:
        _require_day(self.day)


def _require_day(day: object) -> None:
    """Reject anything that is not a plain date. A datetime never equals a date, so it would
    silently bypass the duplicate check."""
    if not isinstance(day, datetime.date) or isinstance(day, datetime.datetime):
        raise TypeError(f"day must be a datetime.date, not {type(day).__name__}")


def record_check_in(habit_id: int, day: datetime.date, existing: Iterable[CheckIn]) -> CheckIn:
    """Return a new CheckIn, or raise DuplicateCheckIn if the habit already has one that day.

    Raises TypeError unless day is a datetime.date. A datetime is refused too: it never equals
    a date, so the duplicate check would silently miss it.
    """
    _require_day(day)
    if any(check_in.habit_id == habit_id and check_in.day == day for check_in in existing):
        raise DuplicateCheckIn(f"habit {habit_id} is already checked in for {day.isoformat()}")
    return CheckIn(habit_id=habit_id, day=day)
