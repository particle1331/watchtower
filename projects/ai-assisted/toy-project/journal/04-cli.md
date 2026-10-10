# Step 04: Command-line interface and composition root

Status: Done
Git: see `git log` (commit message starts with "Step 04")

## Goal
Expose the use cases through a command-line interface, and wire the real adapters
together in the composition root (`habits/main.py`), the only place that reads the clock.

## Plan

| File | Purpose |
|------|---------|
| `habits/cli/__init__.py`, `habits/cli/commands.py` | argparse front end. `run(argv, service, today, out, err) -> int`. Commands: `add`, `checkin [--date]`, `list`. Domain errors go to stderr with exit 1. |
| `habits/main.py` | Composition root. Reads `HABITS_DB` (default `habits.sqlite3`), builds the SQLite repository and `HabitService`, reads `date.today()`, calls `commands.run`, closes the repository. |
| `habits/__main__.py` | Entry point for `python3 -m habits`. |
| `tests/cli/test_commands.py` | CLI behaviour against the in-memory adapter. |
| `tests/test_main.py` | End-to-end test with a temporary SQLite file, checking that data persists across invocations. |
| `tests/test_architecture.py` | **Change:** set the `cli` stdlib allowlist to `argparse` and `sys`. It was a placeholder in Step 02. |
| `ARCHITECTURE.md` | **Change:** add `__main__.py`, the configuration and commands section. |

Rules: only `main.py` reads the clock. `cli` takes `today` as a parameter. Exit codes are
0, 1 for domain errors, and 2 for usage errors (argparse).

## Approval
Standing instruction from the project owner to proceed through the full build without
per-step review. The decision to set the `cli` allowlist was deliberately deferred to this
step (see Step 02, finding D), and it is recorded here.

## Changes
- `habits/cli/__init__.py`, `habits/cli/commands.py`: argparse front end.
- `habits/main.py`: composition root.
- `habits/__main__.py`: `python3 -m habits` entry point.
- `tests/cli/__init__.py`, `tests/cli/test_commands.py`: 10 tests.
- `tests/test_main.py`: 1 end-to-end test.
- `tests/test_architecture.py`: `cli` allowlist set to `argparse`, `sys`.
- `ARCHITECTURE.md`: layout, configuration and commands section.

Deviations: none in behaviour. Implemented by the coordinator, because the fixer
subagent was unavailable (usage limit).

Issue found during testing and fixed: the first CLI test helper shared one output buffer
across calls, so an assertion saw earlier output too. This was a test bug, not a CLI bug.
The helper now creates fresh buffers per call.

## Verification
```
python3 -m unittest discover -s tests -t . -v
Ran 88 tests in 0.016s
OK
```
Smoke test with a temporary database:
```
python3 -m habits add "Read"               -> added habit 1: Read
python3 -m habits checkin 1 --date 2026-10-08 -> checked in habit 1 for 2026-10-08
python3 -m habits checkin 1                -> checked in habit 1 for 2026-10-09
python3 -m habits list                     ->   1  streak   2  Read
python3 -m habits checkin 9                -> error: no habit with id 9   (exit 1)
```

## Review
Self-review against the plan. Checked:
- Only `habits/main.py` calls `date.today()`. The architecture test enforces the layer
  rules, but does NOT check the clock rule. That rule currently rests on review alone.
  This is a gap; see Lessons.
- The `cli` allowlist is now explicit and minimal.

## Drift check
`ARCHITECTURE.md` updated in the same change: `__main__.py` added to the layout, and the
configuration and command section added. The code matches the document.

## Lessons
- Deferred decisions need an owner and a step. Finding D (the `cli` allowlist) was kept
  visible in the journal, and it was resolved on schedule, in the step that needed it.
- Found a real gap: the "no clock outside main" rule in `AGENTS.md` is not mechanically
  enforced. A rule that matters but has no check is just a hope. A guard test should be
  added (planned as a fix in the Step 06 audit).
- A shared mutable test fixture caused a false failure. Test helpers should create fresh state per call.
