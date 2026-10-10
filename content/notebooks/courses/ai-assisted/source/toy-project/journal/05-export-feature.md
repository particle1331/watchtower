# Step 05: JSON export (feature added to an existing architecture)

Status: Done
Git: see `git log` (commit message starts with "Step 05")

## Goal
Add an `export` command that prints every habit and its check-in days as a versioned
JSON document. The purpose of this step is to test whether the architecture absorbs a new
feature without structural change.

## Plan

Design decision: export is built from the **existing** port methods (`list_habits` and
`check_ins_for`). No port method is added or changed. That is why the human-approval gate
in `AGENTS.md` ("changing an existing port signature") is not triggered. The step is
designed to show a feature landing with no architectural change, and the review checks
that claim.

| File | Purpose |
|------|---------|
| `habits/application/habit_service.py` | Add frozen `HabitExport(habit, check_in_days)` and `HabitService.export_all()`. |
| `habits/cli/commands.py` | Add the `export` command and `export_document()`, which serialises with `json`. Format is versioned (`"version": 1`). |
| `tests/test_architecture.py` | Add `json` to the `cli` stdlib allowlist. A visible, deliberate edit. |
| `tests/application/test_habit_service.py` | Export use-case test. |
| `tests/cli/test_commands.py` | Export command tests: document shape, and an empty store. |

Not in scope: writing to a file (`--out`), importing, or filtering. The user can redirect
stdout.

## Approval
Standing instruction from the project owner to proceed. Port unchanged, so no port
approval was required. The `json` allowlist entry is a visible edit to the architecture
test, and it is recorded here for the final review.

## Changes
- `habits/application/habit_service.py`: `HabitExport` and `export_all()`.
- `habits/cli/commands.py`: `export` command, `export_document()`, `EXPORT_FORMAT_VERSION = 1`.
- `tests/test_architecture.py`: `cli` allowlist now `argparse`, `json`, `sys`.
- `tests/application/test_habit_service.py`: `ExportTest`, 1 test.
- `tests/cli/test_commands.py`: `ExportCommandTest`, 2 tests.

No file in `habits/application/ports.py`, `habits/domain/`, or `habits/adapters/` changed.
This is the key claim, and `git show --stat` for the commit confirms it.

## Verification
```
python3 -m unittest discover -s tests -t . -v
Ran 91 tests in 0.033s
OK
```
Smoke test: `python3 -m habits export` printed a valid JSON document with the version,
the habit, and its check-in day.

## Review
Self-review. Confirmed:
- No change to `ports.py`, `domain/`, or `adapters/`. Verified with `git show --stat` after
  commit `69882bc`: six files, all in `application/`, `cli/`, `tests/`, or the journal.
- The architecture test still passes. Its only change was the `json` allowlist entry.

## Drift check
The architecture held. A new feature touched only the application and CLI layers, as the
layer rules predict. `ARCHITECTURE.md` needed no change, because the document describes
layers and rules, not individual features. The `json` allowlist is recorded as a decision
in this journal, not hidden in the test.

## Lessons
- A feature that fits existing ports is the best evidence that the boundaries are right.
  Here, the export needed no port change.
- Adding a stdlib module to an allowlist is a real architectural decision, even though no
  dependency was added. The allowlist makes it visible. It was still a small edit to a
  test file, so it deserves a line in the journal.
- A versioned output format (`"version": 1`) costs one line now and avoids a breaking change later.
