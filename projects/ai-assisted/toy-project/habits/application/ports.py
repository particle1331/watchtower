"""Repository port: the storage interface that use cases depend on (ADR-002)."""

from __future__ import annotations

from typing import List, Optional, Protocol

from habits.domain.habit import CheckIn, Habit


class HabitRepository(Protocol):
    """Storage for habits and check-ins. Adapters satisfy it structurally, without inheriting."""

    def save_habit(self, habit: Habit) -> Habit:
        """Insert a habit that has no id and return a copy with the assigned id.

        A habit that already has an id is not inserted again: the stored habit is returned.
        Raises KeyError if no stored habit has that id.
        """

    def get_habit(self, habit_id: int) -> Optional[Habit]:
        """Return the habit with this id, or None if there is none."""

    def list_habits(self) -> List[Habit]:
        """Return all habits, ordered by id ascending."""

    def save_check_in(self, check_in: CheckIn) -> None:
        """Store a check-in.

        Raises DuplicateCheckIn if a check-in for the same habit and day is already stored.
        Every adapter must enforce this, so the rule holds even if two requests race between
        the service's check_ins_for call and this save.
        """

    def check_ins_for(self, habit_id: int) -> List[CheckIn]:
        """Return the check-ins for a habit, ordered by day ascending."""
