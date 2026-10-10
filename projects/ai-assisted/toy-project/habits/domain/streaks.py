"""Pure streak calculation. Dates are passed in; nothing here reads the clock."""

from __future__ import annotations

import datetime
from typing import Iterable


def current_streak(check_in_days: Iterable[datetime.date], today: datetime.date) -> int:
    """Count consecutive check-in days ending today, or yesterday; 0 if neither is checked in."""
    days = set(check_in_days)
    # A streak survives until a full day is missed, so an unchecked today does not break it yet.
    day = today if today in days else today - datetime.timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= datetime.timedelta(days=1)
    return streak
