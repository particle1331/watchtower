"""In-memory implementation of the HabitRepository port. Nothing is persisted."""

from __future__ import annotations

from typing import Dict, List, Optional

from habits.domain.errors import DuplicateCheckIn
from habits.domain.habit import CheckIn, Habit


class InMemoryHabitRepository:
    """Keeps habits and check-ins in Python objects."""

    def __init__(self) -> None:
        self._habits: Dict[int, Habit] = {}
        self._check_ins: List[CheckIn] = []
        self._next_id = 1

    def save_habit(self, habit: Habit) -> Habit:
        if habit.id is not None:
            return self._habits[habit.id]
        stored = Habit(name=habit.name, id=self._next_id)
        self._next_id += 1
        self._habits[stored.id] = stored
        return stored

    def get_habit(self, habit_id: int) -> Optional[Habit]:
        return self._habits.get(habit_id)

    def list_habits(self) -> List[Habit]:
        return [self._habits[habit_id] for habit_id in sorted(self._habits)]

    def save_check_in(self, check_in: CheckIn) -> None:
        if any(stored.habit_id == check_in.habit_id and stored.day == check_in.day for stored in self._check_ins):
            raise DuplicateCheckIn(f"habit {check_in.habit_id} is already checked in for {check_in.day.isoformat()}")
        self._check_ins.append(check_in)

    def check_ins_for(self, habit_id: int) -> List[CheckIn]:
        matching = [check_in for check_in in self._check_ins if check_in.habit_id == habit_id]
        return sorted(matching, key=lambda check_in: check_in.day)
