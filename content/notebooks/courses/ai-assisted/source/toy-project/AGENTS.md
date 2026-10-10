# Agent Instructions: Habit Tracker

You are working on the Habit Tracker toy project. These rules are mandatory.

## Before you change anything

1. Read `ARCHITECTURE.md` in full.
2. Read the current step file in `journal/` (the highest-numbered file whose
   status is `In progress`). Work only on that step's scope.
3. Run the test suite to confirm the starting state is green.

## Hard rules

- **Respect the dependency rule** in `ARCHITECTURE.md`. Never import `adapters` from
  `application` or `domain`, and never import `cli` from anything except `main`.
- **Stop and ask the human** before any of the following:
  - adding a third-party dependency,
  - creating a new top-level package or a new layer,
  - changing an existing port (`application/ports.py`) signature,
  - changing layering or the dependency rule,
  - touching a file outside the scope of the current journal step.
- **Do not read the system clock** (`date.today()`, `datetime.now()`) outside
  `habits/main.py`. Pass dates in.
- **Keep the diff small.** One concern per change. If a change grows beyond what the
  step describes, stop and report instead of continuing.
- **Tests come with code.** Every new behaviour gets a test in the mirrored path
  under `tests/`.
- **Structure changes update `ARCHITECTURE.md` in the same change.**

## Compatibility

- Target Python 3.9. Do not use `match` statements, `X | Y` union syntax in runtime
  positions, or other 3.10+ features. Start annotated modules with
  `from __future__ import annotations`.
- Use `unittest` only. No pytest.

## Commands

- Run tests (from `toy-project/`):
  `python3 -m unittest discover -s tests -t . -v`
- Run the CLI (from `toy-project/`):
  `python3 -m habits --help` (available after step 4)

## Reporting back

When you finish a step, report:

1. Files created or changed (with a one-line reason each).
2. The exact test command and its result.
3. Any place where you were unsure, or where the architecture seemed to fall short.
   Do not silently work around architectural gaps. Report them.
