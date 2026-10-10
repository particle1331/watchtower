# Step 03: Use cases (application layer)

Status: Done
Git: see `git log` (commit message starts with "Step 03")

## Goal
Add `HabitService`, the application-layer use cases that the CLI will call: add a habit,
check a habit in, and list habits with their current streaks. Tested against the
in-memory adapter.

## Plan

| File | Purpose |
|------|---------|
| `habits/domain/errors.py` | **Change:** add `HabitNotFound(DomainError)`. |
| `habits/application/habit_service.py` | `HabitService` and `HabitSummary`. |
| `tests/application/test_habit_service.py` | Use-case tests, using `InMemoryHabitRepository`. |
| `ARCHITECTURE.md` | **Change:** none expected. |

### `HabitService(repository: HabitRepository)`

- `add_habit(name: str) -> Habit`: validates the name by constructing `Habit(name=name)`,
  then calls `repository.save_habit`. Returns the stored habit with its id.
- `check_in(habit_id: int, day: date) -> CheckIn`:
  - raises `HabitNotFound` if `repository.get_habit(habit_id)` is `None`,
  - loads `repository.check_ins_for(habit_id)`,
  - calls `record_check_in(habit_id, day, existing)`, which raises `DuplicateCheckIn`
    if applicable,
  - saves the result and returns it.
- `list_habits(today: date) -> List[HabitSummary]`: one summary per habit, in id order.
  `HabitSummary` is a frozen dataclass with `habit: Habit` and `streak: int`. The streak
  is `current_streak(days, today)`, where `days` are the habit's check-in days.

### Rules for this step

- The service never reads the clock. `today` and `day` are always parameters.
- The service imports only from `habits.domain` and `habits.application`
  (the architecture test enforces this).
- Errors from the domain (`InvalidHabitName`, `DuplicateCheckIn`, `HabitNotFound`)
  propagate unchanged. The service does not wrap them.

### Tests

Cover at least: add returns an id; add rejects an invalid name and stores nothing;
check-in stores a check-in; check-in for a missing habit raises `HabitNotFound`;
duplicate check-in on the same day raises `DuplicateCheckIn`; list shows zero streak
for a new habit; list shows a streak counted to today; list is ordered by id.

## Approval
Standing instruction from the project owner to proceed through the full build without
per-step review. Plan drafted by the coordinator. Independent plan review: not run.

## Changes
- `habits/domain/errors.py`: added `HabitNotFound(DomainError)`.
- `habits/application/habit_service.py`: `HabitService` (`add_habit`, `check_in`,
  `list_habits(today)`) and frozen `HabitSummary(habit, streak)`.
- `tests/application/__init__.py`, `tests/application/test_habit_service.py`: 8 tests,
  run against `InMemoryHabitRepository`.

Deviation: the fixer subagent could not be used, because its provider usage limit was
reached. The coordinator implemented this step directly, following the same plan and
rules. Nothing in the plan changed.

## Verification
```
python3 -m unittest discover -s tests -t . -v
Ran 77 tests in 0.009s
OK
```

## Review
Coordinator self-review against the plan. Checked:
- The service reads no clock. `today` and `day` are always parameters.
- The service imports only `habits.domain` and `habits.application`. The architecture
  test passes.
- Domain errors propagate unchanged, with no wrapping.

No independent review yet. An observer review is planned for the end of the build.

## Drift check
`ARCHITECTURE.md` still matches the code. No structural change in this step.

## Lessons
- With the fixer unavailable, the coordinator did the work directly. The process still
  held, because the plan was written first and the tests check the plan's rules. The
  process does not depend on who types the code.
- The plan's test list was specific enough that the tests were straightforward to write.
