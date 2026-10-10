# Step 06: Drift audit and controlled drift experiment

Status: Done
Git: see `git log` (commit message starts with "Step 06")

## Goal
Test the process against deliberate drift, rather than assume it works. Two questions:

1. Does the mechanical defence (the architecture test) catch the drift we would expect
   most often?
2. What does the mechanical defence miss, and what does a human audit have to catch?

## Plan

Part A: controlled experiment, in a scratch copy of the project (not the real repo).
Inject two realistic drifts:

- **Drift 1, layer bypass:** the CLI imports the SQLite adapter directly, skipping the
  application layer. This is the most common drift in agent-written code.
- **Drift 2, hidden clock read:** a domain function calls `date.today()` as a "convenient
  default". This breaks ADR-003 and makes logic untestable.

Record which tests fail.

Part B: close any gap the experiment exposes, in the real repo.

Part C: an audit of the real codebase for drift that tests do not measure: unused
imports, duplicated logic, and documented modules that do not exist.

## Approval
Standing instruction from the project owner to proceed. Part B adds a test to
`tests/test_architecture.py`. This is a rule that was already stated in ADR-003 and
`AGENTS.md`, so it is an enforcement change, not a new rule.

## Changes

### Part A: experiment (scratch copy, before any fix)
| Injected drift | Caught by the existing suite? |
|----------------|-------------------------------|
| 1. `cli/commands.py` imports `habits.adapters.sqlite_repository` | **Yes.** `test_habits_package_follows_the_dependency_rule` fails. |
| 2. `domain/streaks.py` calls `date.today()` | **No.** All 91 tests pass. Nothing checks the clock rule. |

Drift 2 confirms the gap flagged in Step 04. The rule existed only in the documents, so
the suite could not see it being broken.

### Part B: fix
Added `find_clock_reads()` and `ClockRuleTests` to `tests/test_architecture.py`. The
checker uses `ast` to find any attribute access to `.today`, `.now`, or `.utcnow` in
`habits/`, calls or not, except `main.py`. Tests cover the real tree, a domain call, and
an alias without a call. The first version was narrower (calls only, and `__main__.py`
exempt). Step 07's review tightened it.

Re-running the experiment with the new rule: Drift 2 is now caught by
`test_only_the_composition_root_reads_the_clock`.

### Part C: audit of the real codebase
Mechanical checks, run from `tools/audit.py` (committed in Step 07 so the audit is reproducible):

| Check | Result |
|-------|--------|
| Unused imports in every `.py` file | None found. |
| The date-walk logic (`timedelta`) appears in one place only | Yes, `habits/domain/streaks.py`. No duplication. |
| Every module named in `ARCHITECTURE.md`'s layout exists | Yes. None missing. |
| Public functions with no callers | None found. Every named function is referenced. |

No drift beyond the clock gap was found. The audit found no code-level problems. That is
a finding in its own right: with the clock rule in place, the structure matched the document.

## Verification
```
python3 -m unittest discover -s tests -t . -v
Ran 94 tests in 0.022s
OK
```
Experiment, re-run after the fix:
```
FAIL: test_only_the_composition_root_reads_the_clock
  ['domain/streaks.py:20: reads the clock via .today()']
FAIL: test_habits_package_follows_the_dependency_rule
FAILED (failures=2)
```

## Review
Self-review of the audit method. Its limits:
- The mechanical checks are narrow. They find what they are written to find. The audit's
  real value is the experiment, which tested the defences against drift that was
  actually injected.
- A human reviewer would still need to judge duplicated *concepts*, such as two
  functions that compute the same streak differently. The script cannot see that. Not
  present here, but it would be missed by the tooling.
- An independent observer review of the whole codebase is planned for the final step.

## Drift check
After the Part B fix, `ARCHITECTURE.md` and the code agree. Nothing in the document needed
to change, because the clock rule was already documented in ADR-003.

## Lessons
- **Test the process, not just the code.** The clock rule was written down and believed to
  be enforced. Step 04's self-review flagged that it was not. Only an injected violation
  proved the suite could not see it. A rule without a check is a hope.
- **Mechanical defences catch structural drift well.** The layer bypass was caught on the
  first run. Semantic drift, such as duplicated logic, needs a human audit.
- **Make the experiment part of the record.** The before-and-after results are the evidence
  that the defence works, and they belong in the journal.
