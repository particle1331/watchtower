# Step 01: Domain core

Status: Done
Git: see `git log` (commit message starts with "Step 01")

## Goal
Implement the pure domain layer: the `Habit` and `CheckIn` entities, the
duplicate-check-in rule, and streak calculation. No storage, no CLI, no clock.

## Plan

Files to create (all under `toy-project/`):

| File | Purpose |
|------|---------|
| `habits/__init__.py` | Package marker. Empty except a docstring. |
| `habits/domain/__init__.py` | Package marker. Empty except a docstring. |
| `habits/domain/errors.py` | `DomainError` base, `InvalidHabitName`, `DuplicateCheckIn`. |
| `habits/domain/habit.py` | `Habit` and `CheckIn` frozen dataclasses. `validate_habit_name()`. `record_check_in()` which raises `DuplicateCheckIn` if the habit already has a check-in for that day. |
| `habits/domain/streaks.py` | `current_streak(check_in_days, today) -> int`. |
| `tests/__init__.py`, `tests/domain/__init__.py` | Package markers. |
| `tests/domain/test_habit.py` | Tests for name validation and duplicate check-in. |
| `tests/domain/test_streaks.py` | Tests for streak calculation. |

Rules for this step:

- Domain imports only the standard library (`dataclasses`, `datetime`, `typing`).
- `Habit.name` is stripped of surrounding whitespace. Empty names, and names longer
  than 60 characters after stripping, raise `InvalidHabitName`.
- `Habit.id` is `Optional[int]` (`None` until storage assigns one).
- `CheckIn` has `habit_id: int` and `day: datetime.date`.
- `record_check_in(habit_id, day, existing)` takes an iterable of existing `CheckIn`
  values and returns a new `CheckIn`. It raises `DuplicateCheckIn` if one already
  exists for the same `habit_id` and `day`.
- `current_streak(check_in_days, today)`:
  - If `today` is in the set, count consecutive days backwards starting at `today`.
  - Otherwise, if yesterday is in the set, count backwards starting at yesterday.
    (A streak is not broken until a full day is missed.)
  - Otherwise return 0.
- Target Python 3.9. Use `typing.Optional`, and start annotated modules with
  `from __future__ import annotations`.

Out of scope: storage, use cases, CLI, `tests/test_architecture.py` (that comes in
step 02, once there are several layers to check).

## Approval
Plan drafted by the coordinator. Approved to proceed by the project owner (the user
requested this step-by-step build). Independent plan review: not run for this step.

## Changes
Implemented the plan as written, with these files:

- `habits/__init__.py`, `habits/domain/__init__.py`, `tests/__init__.py`,
  `tests/domain/__init__.py`: package markers.
- `habits/domain/errors.py`: `DomainError`, `InvalidHabitName`, `DuplicateCheckIn`.
- `habits/domain/habit.py`: `Habit`, `CheckIn`, `validate_habit_name`, `record_check_in`.
- `habits/domain/streaks.py`: `current_streak`.
- `tests/domain/test_habit.py` (14 tests), `tests/domain/test_streaks.py` (8 tests).

Deviations from the plan:

- `errors.py` was not in the plan's file table, but the code needs it. The plan
  should have listed it. It was added to `ARCHITECTURE.md` during this step.
- The plan did not say whether same-layer imports are allowed. The implementation
  needed them, so `ARCHITECTURE.md` now states that rule explicitly.

## Verification
Run from `toy-project/` on Python 3.9.6:

```
python3 -m unittest discover -s tests -t . -v
Ran 22 tests in 0.000s
OK
```

Coordinator re-ran the suite independently after the implementation step. Same result.

## Review
Self-report by the implementing agent, which listed three uncertainties (not an independent review):

1. **Architecture doc missing `errors.py`.** Resolved: `ARCHITECTURE.md` updated.
2. **Same-layer import rule was ambiguous.** Resolved: clarified in `ARCHITECTURE.md`.
3. **`record_check_in` accepts a `datetime.datetime` silently.** A `datetime` never
   equals a `date`, so the duplicate check would not fire. This is a real correctness
   risk, but it was outside this step's plan. **Open: carry to Step 02**, where a
   type guard and a test will be added.

An independent observer review of this step was not run. It is worth doing once there
is more code to review.

## Drift check
`ARCHITECTURE.md` matches the code after the two doc fixes above. No structural drift.
Architecture test (ADR-004) is not yet present, which is expected. It arrives in Step 02.

## Lessons
- Writing the file table before the code made the implementing agent's scope
  unambiguous. The one gap, `errors.py`, was caught because the agent reported it
  instead of silently adding it.
- The agent's report flagged a real correctness issue (item 3). The process worked
  because the report was required to include uncertainties.
- Process change: the plan template should require that every file the code needs is
  listed, and that import rules are stated for same-layer cases too.
