# Architecture: Habit Tracker

This document is the ground truth for the structure of the project. Agents and
humans must read it before changing code. If the code and this document disagree,
one of them is wrong and must be fixed in the same change.

## Purpose

A command-line tool for tracking daily habits. Users can:

- add a habit,
- check a habit in for today,
- list habits with their current streak,
- (later) export all data to JSON.

## Layers and dependency rule

```
   cli/  ───────────┐
                    ▼
            application/  ───────►  domain/
                    ▲
   adapters/ ───────┘
```

Read the arrows as "may import from". The rule is:

| Package        | May import from                          | Must NOT import from                  |
|----------------|------------------------------------------|---------------------------------------|
| `habits.domain`      | Python standard library only         | anything else in `habits`             |
| `habits.application` | `habits.domain`                      | `habits.adapters`, `habits.cli`       |
| `habits.adapters`    | `habits.domain`, `habits.application` | `habits.cli`                         |
| `habits.cli`         | `habits.application`, `habits.domain` | `habits.adapters`                    |
| `habits.main`        | everything (composition root only)   | —                                     |

`habits.main` is the only place where concrete adapters are wired to use cases.

Imports *within* the same layer are allowed (for example, `habit.py` importing
`errors.py`, both in `habits.domain`). The table constrains imports across layers only.

## Package layout

```
toy-project/
  habits/
    __init__.py
    __main__.py             # `python3 -m habits` entry point; calls main.main()
    main.py                 # composition root: reads the clock, picks adapters, builds services
    domain/
      __init__.py
      errors.py             # DomainError and rule-violation subclasses
      habit.py              # Habit and CheckIn entities, name validation, check-in rule
      streaks.py            # pure streak calculation
    application/
      __init__.py
      ports.py              # abstract repository interface (Protocol)
      habit_service.py      # use cases: add, check in, list with streaks
    adapters/
      __init__.py
      memory_repository.py  # in-memory port implementation (tests)
      sqlite_repository.py  # SQLite port implementation (real storage)
    cli/
      __init__.py
      commands.py           # argparse front end; takes `today` as a parameter
  tests/
    ...                     # mirrors package layout
  journal/
    ...                     # one file per process step
```

## Key decisions (ADRs, short form)

- **ADR-001: Standard library only.** No third-party dependencies. Adding one requires
  a new ADR and human approval. Target runtime: Python 3.9.
- **ADR-002: Storage behind a port.** Use cases depend on `HabitRepository`
  (a `Protocol` in `application/ports.py`). SQLite is one adapter; memory is another.
- **ADR-003: Dates are injected, never read from the clock inside domain or
  application code.** Callers pass `datetime.date` values. This keeps logic testable.
- **ADR-004: Layering is enforced by a test.** `tests/test_architecture.py` parses
  imports and fails if the dependency rule above is broken. It also enforces a
  per-layer standard-library allowlist, which is the concrete meaning of "standard
  library only" for each layer. The allowlist lives in that test file, so changing
  it is a visible, reviewable edit.

## Configuration and commands

- Database file: the `HABITS_DB` environment variable, or `habits.sqlite3` in the working directory.
- Commands: `add NAME`, `checkin ID [--date YYYY-MM-DD]`, `list`.
- Exit codes: 0 success, 1 domain error (printed to stderr), 2 usage error (argparse).

## Conventions

- Entities are immutable `dataclasses` (`frozen=True`) where practical.
- Errors: domain rule violations raise `habits.domain.errors.DomainError` subclasses.
- Every module that exports behaviour has tests in the mirrored path under `tests/`.
- Each file that uses annotations starts with `from __future__ import annotations`
  (Python 3.9 compatibility).
