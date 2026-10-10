# Step 07: Independent review, fixes, and documentation

Status: Done (with open items listed below, deliberately not changed)
Git: see `git log` (commit message starts with "Step 07")

## Goal
Review the whole repository with someone who did not write it, act on the findings, and
make the whitepaper's claims match the record. Documentation (the toy README and the
whitepaper) was written in the same step, and is reviewed here too.

## Plan
1. Ask an observer agent for a read-only review, with explicit checks: run the suite,
   test edge cases, check each whitepaper claim against the journal and git, look for
   process-honesty problems, and look for overclaiming.
2. Resolve each finding: fix it, or record it as an open decision with a reason.
3. Re-run the suite and the audit. Commit.

## Approval
Standing instruction from the project owner. The review was run as a read-only subagent.
Decisions with product impact are listed as open, not decided here.

## Review findings and resolutions

The observer reported: no blockers; several issues; and several notes. Summarised:

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| 1 | Issue | The whitepaper said "only the injected violation revealed" the clock gap. Step 04's self-review had already flagged it. The paper contradicted its own record. | **Fixed.** Corrected in the whitepaper and in Step 06's lessons. |
| 2 | Issue | The clock rule was narrower than stated. It checked only calls, not aliases, and it exempted `__main__.py`, which should not be exempt. | **Fixed.** The checker now flags any attribute access, calls or not. Only `main.py` is exempt. Tests cover an alias and `__main__.py`. A scratch run confirmed an injected alias now fails the suite. |
| 3 | Note | The audit in Step 06 was described as a script, but no script was committed. The claim could not be reproduced. | **Fixed.** Committed as `toy-project/tools/audit.py`. It runs clean. |
| 4 | Note | Step 05 claimed a diff check that was not in the record. | **Fixed.** Now cites `git show --stat` for commit `69882bc`. |
| 5 | Note | Step 01 called the implementer's self-report an "independent review". | **Fixed.** Relabelled as a self-report. |
| 6 | Note | A bad `HABITS_DB` path produced an uncaught `sqlite3.OperationalError` traceback. | **Fixed.** `main()` prints a clean error and exits 1. Test added. |
| 7 | Note | A concurrent duplicate check-in could escape the service's pre-check and surface as a raw `sqlite3.IntegrityError`. | **Fixed, with a design change.** See below. |
| 8 | Note | `checkin --date` accepts future dates. | **Open decision.** See below. Not changed. |

### Finding 7 in detail: a contract that differed by adapter
Reviewing finding 7 showed a deeper inconsistency. The port said a backend "may" reject
duplicates. The memory adapter stored them silently. SQLite raised a raw `IntegrityError`.
The same use case would behave differently depending on which adapter was wired in.

The fix makes the contract explicit:
- `ports.py`: `save_check_in` raises `DuplicateCheckIn` for a duplicate. Every adapter must
  enforce this. The signature is unchanged, so this is not a port-signature change.
- `memory_repository.py`: now raises `DuplicateCheckIn`.
- `sqlite_repository.py`: translates the SQLite `UNIQUE constraint failed` violation to
  `DuplicateCheckIn`. Other integrity failures (for example, a missing habit) are re-raised
  unchanged, because they are not duplicates. The two are distinguished by the message text.
- `tests/adapters/repository_contract.py`: one shared test checks that every adapter rejects
  the duplicate, so the two adapters cannot drift apart again.

This closes the race for real, not just in the happy path: the database's uniqueness check
is the final authority, and the adapter reports it in domain terms.

### Open decision: future-dated check-ins (finding 8)
`checkin --date` accepts a day in the future. A future check-in never counts toward a
streak, but it does appear in `list` and `export`. Whether that is wrong depends on the
product: it could be a planned check-in, or an input mistake. Blocking it is a one-line rule,
but it is a product decision, so it is **not changed**. The project owner should decide.

### Open limitation: the clock rule and dynamic access
The clock rule still cannot see `getattr(datetime.date, "to" + "day")()`. It is a
limitation of static checking, and it is recorded in the whitepaper. Closing it fully would
need a runtime check, which is not worth the cost in a project this size.

## Changes
- `habits/application/ports.py`: docstring of `save_check_in` (the duplicate contract).
- `habits/adapters/memory_repository.py`: enforces the duplicate rule.
- `habits/adapters/sqlite_repository.py`: translates the duplicate violation.
- `habits/main.py`: clean error for a database that cannot be opened.
- `tests/test_architecture.py`: clock rule tightened; new tests for aliases and `__main__.py`.
- `tests/adapters/repository_contract.py`: shared duplicate test for every adapter.
- `tests/adapters/test_memory_repository.py`: removed the test that asserted duplicates were
  stored (the opposite of the new contract), and its now-unused imports.
- `tests/adapters/test_sqlite_repository.py`: the duplicate test now expects `DuplicateCheckIn`.
- `tests/test_main.py`: test for the unopenable database.
- `tools/audit.py`: the committed drift audit from Step 06.
- `toy-project/README.md`, `WHITEPAPER.md` (corrections and the review's status), and
  Step 01, 02, 05, 06 journal wording.

## Verification
```
python3 -m unittest discover -s tests -t . -v
Ran 98 tests in 0.032s
OK

python3 tools/audit.py
audit: clean
```
The observer reported the suite as 94 tests (its static count, since it could not run the
suite). The run after the fixes gives 98. The four extra tests are the clock tests added in
this step, the clean-error test, and the contract test for duplicates.

## Review
- The observer could not run commands (no shell access), so its findings on behaviour were
  verified by the coordinator, by running the code. Every behavioural claim in the observer
  report was checked before it was acted on.
- The observer found no blockers. The core domain logic and streak edge cases were judged
  correct.

## Drift check
`ARCHITECTURE.md` still matches the code. The duplicate contract is a behaviour change,
not a structural one, and the layer rules are unchanged: the SQLite adapter imports the
domain error, which the table allows.

## Lessons
- **An independent review finds what self-review cannot.** The whitepaper overclaimed, and
  the author (the coordinator) could not see it, because it had written the claim. A reviewer
  with no stake in the story caught it at once.
- **Review the documentation as hard as the code.** Two of the eight findings were in the
  record and the paper, not the code.
- **A contract that differs by implementation is not a contract.** The memory and SQLite
  adapters disagreed about duplicates. Only the shared contract test, now extended, keeps
  them aligned.
- **Make audits reproducible.** An audit that is described but not committed cannot be
  checked by anyone else.
- **Know which findings are decisions.** The future-date question is not a bug to fix
  quietly. It is for the owner, and it is recorded as open.
