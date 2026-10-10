# Step 02: Persistence port, adapters, architecture test

Status: Done
Git: see `git log` (commit message starts with "Step 02")

## Goal
Add the repository port that use cases will depend on, two adapters (in-memory and
SQLite), the `datetime` guard deferred from Step 01, and the architecture test that
enforces the dependency rule (ADR-004).

## Plan

Files to create or change (all under `toy-project/`):

| File | Purpose |
|------|---------|
| `habits/application/__init__.py` | Package marker (docstring only). |
| `habits/application/ports.py` | `HabitRepository` as a `typing.Protocol` (see methods below). |
| `habits/adapters/__init__.py` | Package marker (docstring only). |
| `habits/adapters/memory_repository.py` | `InMemoryHabitRepository` implementing the port. |
| `habits/adapters/sqlite_repository.py` | `SqliteHabitRepository(path)` implementing the port. |
| `habits/domain/habit.py` | **Change:** `record_check_in` raises `TypeError` if `day` is not a `datetime.date`, or is a `datetime.datetime`. |
| `tests/application/__init__.py`, `tests/adapters/__init__.py` | Package markers. |
| `tests/adapters/repository_contract.py` | Shared contract test mixin, run against both adapters. |
| `tests/adapters/test_memory_repository.py` | Runs the contract against the in-memory adapter. |
| `tests/adapters/test_sqlite_repository.py` | Runs the contract against SQLite (`:memory:` or a temp file) and checks that data survives reopening a file. |
| `tests/domain/test_habit.py` | **Change:** add tests for the `TypeError` guard. |
| `tests/test_architecture.py` | Architecture test (ADR-004). |
| `ARCHITECTURE.md` | **Change:** none expected. Update only if the implementation forces it, and say so in the journal. |

### Port (`HabitRepository`)

- `save_habit(habit: Habit) -> Habit`: inserts when `habit.id is None` and returns a
  copy with the assigned id. Returns the stored habit when `id` is set.
- `get_habit(habit_id: int) -> Optional[Habit]`
- `list_habits() -> List[Habit]`: ordered by id ascending.
- `save_check_in(check_in: CheckIn) -> None`: stores the check-in. It does NOT enforce
  duplicates. Duplicate detection is a domain rule applied by the caller, using
  `check_ins_for`.
- `check_ins_for(habit_id: int) -> List[CheckIn]`: ordered by day ascending.

### SQLite adapter

- Schema created on construction when missing:
  `habits(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)` and
  `check_ins(habit_id INTEGER NOT NULL REFERENCES habits(id), day TEXT NOT NULL, PRIMARY KEY (habit_id, day))`.
  Days are stored as ISO-8601 text.
- Provides `close()`.
- The `PRIMARY KEY (habit_id, day)` is a second line of defence. A duplicate reaching
  the database surfaces as `sqlite3.IntegrityError`, which the adapter does not hide.

### Architecture test

`tests/test_architecture.py` parses every `.py` file under `habits/` with `ast`. For
each import it checks:

- Internal imports (`habits.<layer>`) must be in the allowed set for that layer, as in
  the table in `ARCHITECTURE.md`.
- External imports must be in the layer's standard-library allowlist. The allowlists
  are written out explicitly in the test, because Python 3.9 has no
  `sys.stdlib_module_names`.
- `habits/main.py` and `habits/__main__.py` may import anything (composition root).
  `main.py` does not exist yet, so the test must tolerate that.

The test also includes a self-test: it runs the same checker on a synthetic source
snippet that violates the rule, and asserts that a violation is reported. A
guardrail that has never been seen to fail is not evidence of anything.

## Approval
Plan drafted by the coordinator. The project owner asked for the full build to proceed
without per-step review (the owner was unavailable), so this step proceeds on that
standing instruction. Port method names above are the decisions a human should
confirm during the final review. Independent plan review: not run.

## Changes
Implemented by the fixer agent per the plan, then reviewed by the coordinator:

- `habits/application/ports.py`: `HabitRepository` Protocol, five methods.
- `habits/adapters/memory_repository.py`: `InMemoryHabitRepository`.
- `habits/adapters/sqlite_repository.py`: `SqliteHabitRepository` (schema, ISO-8601 days, `close()`).
- `tests/adapters/repository_contract.py`: one contract, run against both adapters.
- `tests/adapters/test_memory_repository.py`, `tests/adapters/test_sqlite_repository.py`:
  adapter tests, including reopen-persistence.
- `tests/test_architecture.py`: AST-based checker for the layer table and stdlib
  allowlists, with a self-test that feeds it a violating snippet.
- `habits/domain/habit.py`: `TypeError` guard, added in two places (see Review).
- `tests/domain/test_habit.py`: guard tests.

Deviations from the plan:

- The guard was placed in `record_check_in` only, as planned. Review found that
  `CheckIn` itself accepted a datetime. The check was moved into `CheckIn.__post_init__`
  (shared helper `_require_day`) so every path is covered.
- Not in the plan: the "unknown id" behaviour of `save_habit` (raises `KeyError`).
  This is now documented in the port docstring.

## Verification
```
python3 -m unittest discover -s tests -t . -v
Ran 69 tests in 0.010s
OK
```
Fixer's run: 64 tests, OK. The coordinator's review fixes raised this to 69.

## Review
Fixer report and coordinator review. Findings and resolutions:

| # | Finding | Resolution |
|---|---------|------------|
| A | `CheckIn` accepts a datetime; the guard only covered `record_check_in`. | Guard moved into `CheckIn.__post_init__`. Tests: `tests/domain/test_check_in_day.py`. |
| B | SQLite foreign keys were off, so the `REFERENCES` clause did nothing. A check-in for a missing habit was stored silently. | `PRAGMA foreign_keys = ON` added. Tests: `tests/adapters/test_sqlite_foreign_keys.py`. |
| C | `ARCHITECTURE.md` said "standard library only" but the enforced allowlist was narrower and undocumented. | ADR-004 now describes the allowlist and where it lives. |
| D | `cli` allowlist is a placeholder. | Resolved in Step 04. |
| E | The checker is static and cannot see `importlib` dynamic imports. | Accepted limitation. Noted for the whitepaper. |

## Drift check
`ARCHITECTURE.md` matches the code after the fixes above. The architecture test is now
live and passing. This is the first point where the process's drift defence is
mechanical, not a matter of memory.

## Lessons
- The fixer's "gaps" section was the most useful part of its report. Two of the three
  gaps (A and B) were real bugs that the tests did not catch. The process caught them
  only because the report was required to list uncertainties.
- A guard in one function is not a guard on the data. The rule belongs on the entity,
  so every construction path is covered.
- Enabling foreign keys is a single line, but it is off by default. A schema that
  looks like it enforces a rule may not. Test the rule, not the DDL.
