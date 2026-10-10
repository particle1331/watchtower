# Building With AI Agents Without Losing the Architecture

*A process for AI-assisted development that keeps the human in control of structure as a
project grows. Written from a worked example in this repository.*

---

## Abstract

AI coding agents make the first 85% of a feature fast. The remaining 15% (the edge cases,
the integration seams, the design choices that matter) gets harder as a project grows,
because the human's mental model of the code falls behind the code. The architecture
drifts silently, and every new change requires an agent to explain the system back to the
person who is supposed to own it.

This paper describes a process that reverses that trend. Its core is simple: **the human
owns the architecture, written down in a form the agent must obey, and the agent does the
typing under rules that are checked by machine rather than by memory.** The paper is
backed by a toy project, built in a scaffold (step 00) and seven journaled build steps (01 to 07), in this repository. Every claim
below can be checked against `toy-project/journal/` and the git history.

---

## 1. The problem

Three things happen as an AI-assisted project grows:

1. **Understanding erodes.** Code arrives faster than the human reads it. Each accepted change
   is a small loan against understanding, and the loans compound.
2. **Architecture drifts unnoticed.** An agent solves the immediate problem in the most
   local way: a shortcut import, a convenience default, a helper that duplicates one that
   already exists. None of these breaks a test, so none is noticed.
3. **Memory is the only enforcement.** The rules live in the human's head, or in a chat
   history that the next session does not have. A rule that exists only in memory is not a
   rule.

The result is a project that works, but that only the agent can change, and changes slowly
because the agent must re-learn the system each time.

---

## 2. The principles

| # | Principle | What it means in practice |
|---|-----------|---------------------------|
| P1 | **Write the architecture down, before the code.** | A short `ARCHITECTURE.md`: layers, the dependency rule, and key decisions as numbered ADRs. |
| P2 | **Give the agent rules, not just context.** | `AGENTS.md` lists hard rules and the conditions under which the agent must *stop and ask*. |
| P3 | **Plan before code, in a file.** | Each step has a plan (files, rules, tests) written and recorded before any code. |
| P4 | **Enforce rules mechanically.** | A rule that matters must have a test that fails when it is broken. Documentation is not enforcement. |
| P5 | **Test the defences, not only the code.** | Inject a violation on purpose and confirm the process catches it. |
| P6 | **Keep a record a human can read later.** | A journal entry per step, plus one git commit per step. The record is how a human rebuilds understanding. |
| P7 | **Audit on a schedule, separately from features.** | Drift is found in dedicated audit steps, not mixed into feature work. |

P4 and P5 are the ones most projects skip. The rest are cheap, but they only help if the
rules they produce are checked.

---

## 3. The process

Each step follows the same loop:

```
  plan  ──►  approve  ──►  implement  ──►  verify  ──►  review  ──►  record
  (file)    (human)       (agent,          (run the     (independent   (journal +
                           scoped)          suite)       check)         commit)
```

1. **Plan.** Write the step file before any code. It lists the files to change, the rules
   that apply, and the tests that prove the step. The plan is the unit of human review. It is
   far cheaper to fix a plan than a diff.
2. **Approve.** A human confirms the plan, or changes it. In this project the approval is a
   recorded line in the journal. Any decision deferred from an earlier step is named here.
3. **Implement.** The agent works within the plan's scope. It reports what it changed, what
   it was unsure of, and any gap in the architecture. It is required to report gaps rather
   than work around them silently.
4. **Verify.** The test suite runs. The human (or coordinator) re-runs it, rather than
   trusting the agent's summary.
5. **Review.** Findings are listed in a table, and each one is resolved or deliberately
   deferred with an owner.
6. **Record.** The journal entry is completed, including deviations from the plan. One commit
   per step.

### The artifacts

| Artifact | Audience | Purpose |
|----------|----------|---------|
| `ARCHITECTURE.md` | Human and agent | The ground truth for structure. Updated in the same change as any structural change. |
| `AGENTS.md` | Agent | Hard rules, scope, stop-and-ask conditions, and how to report back. |
| `journal/NN-*.md` | Human, later | The reasoning for each step: plan, changes, verification, review, drift check, lessons. |
| Architecture test | The build | Mechanically enforces the dependency rule and the clock rule. |
| Git history | Human | One commit per step, so any step can be inspected or reverted. |

---

## 4. The mechanical defences

Two rules in this project are enforced by an AST-based test in `tests/test_architecture.py`:

- **The dependency rule.** Each layer may import only from the layers its row in the table
  allows, and only the standard-library modules its allowlist names.
- **The clock rule.** Only the composition root may read the system clock. Everything
  else takes dates as parameters, which keeps logic deterministic and testable.

The test is itself tested. A self-test feeds the checker a violating snippet and asserts
that it reports a violation. A guardrail that has never been seen to fail is not evidence
of anything.

---

## 5. Case study: the toy project

The Habit Tracker is a CLI with `add`, `checkin`, `list`, and `export` commands. It was built in
a scaffold (step 00), then seven journaled build steps (01 to 07). The table summarises the record; each row links to the journal.

| Step | What was built | Tests after step | Notes |
|------|----------------|------------------|-------|
| 00 | Process scaffold: `ARCHITECTURE.md`, `AGENTS.md`, journal template | 0 | The ground truth exists before any code. |
| 01 | Domain core: entities, duplicate rule, streak calculation | 22 | Found that `ARCHITECTURE.md` omitted a file. Fixed in the same commit. |
| 02 | Repository port, memory and SQLite adapters, architecture test | 69 | Review found two real bugs the tests had missed: a `datetime` accepted as a date, and foreign keys off by default. |
| 03 | Use cases (`HabitService`) | 77 | The fixer subagent hit a usage limit, so the coordinator implemented the step against the same plan. |
| 04 | CLI and composition root | 88 | Found a test-helper bug (a shared buffer). Found that the clock rule was not enforced. |
| 05 | JSON export: a new feature with no port change | 91 | Confirmed the architecture absorbed a feature in two layers. |
| 06 | Drift experiment and audit | 94 | Injected two drifts. One was caught. The other exposed a gap, which was closed. |
| 07 | Independent review and fixes | 98 | An observer agent found an overclaim in this paper, a narrow clock rule, and a duplicate-check-in inconsistency. All were fixed or recorded. |

### What the record shows

- **The architecture test caught the layer bypass on the first run.** Structural drift
  is the kind a mechanical check handles well.
- **The clock rule was documented and not enforced.** Step 04's review flagged the gap, but
  nothing proved the suite was blind to it until a violation was injected in Step 06. That
  is the most important lesson in the paper: documentation is not enforcement, and the way to
  tell the difference is to break the rule on purpose.
- **A feature that needed no port change was the best evidence of good boundaries.** The
  export touched two layers and one allowlist line. Its commit stat shows no change to ports,
  domain, or adapters.
- **Two bugs were caught by review, not by the original tests.** Both were in the first
  two steps. Both were found because the implementation report had to list uncertainties,
  not just success.
- **Deferred decisions need an owner and a step.** The `cli` allowlist was a placeholder in
  Step 02, and it was resolved in Step 04, the step that needed it. A placeholder that is not
  tracked becomes a silent default.

---

## 6. Honest limitations

This is a toy project, and the paper does not claim more than the evidence supports.

- **The approval gate was largely self-approved.** The project owner was unavailable, so
  the coordinator recorded approvals on a standing instruction. In a real team, the
  approval line must be a real person. The journal's structure supports that, but it
  cannot enforce it.
- **The mechanical checks are narrow.** The architecture test sees static imports and direct
  attribute access to clock functions. It does not see dynamic imports (`importlib`), dynamic
  attribute access (`getattr` with a computed name), duplicated *concepts*, or poor naming.
  Those need human audit.
- **Most review was self-review.** The one fully independent review (an observer agent that
  did not write the code, reading the whole repository) was run at the end of the build. It
  found real issues, and they are recorded and resolved in Step 07. The reviewer had no shell
  access, so it could not run the tests itself; the coordinator ran them.
- **Open decisions are left open.** The toy accepts check-ins dated in the future. It is a
  product decision, so the review recorded it instead of deciding it (Step 07).
- **The toy is small.** Drift grows with size. Nothing here proves the process holds at 50,000
  lines. It shows the *mechanisms* work at small scale, which is the claim.
- **Subagent availability is a dependency.** When the delegated implementer was unavailable,
  the coordinator did the work. This worked because the plan carried the rules, but it means
  the process is only as robust as the tooling beneath it.

---

## 7. Adopting this process

A minimal starting kit, in order of leverage:

1. **Write `ARCHITECTURE.md`** (1–2 pages): layers, the dependency rule, and three to five
   decisions that you would not want an agent to change silently.
2. **Write `AGENTS.md`**: the rules, the stop-and-ask list, and how the agent reports back.
   Include the report format that asks for uncertainties.
3. **Turn the most important rule into a test.** Pick the rule you are most afraid of being
   broken, and write a failing-when-broken check for it. Then break it on purpose once,
   to prove the check works.
4. **Plan each feature in a file before coding.** List files, rules, and tests. Approve it
   before implementation.
5. **Keep one commit per step, and a journal entry per step**, including deviations.
6. **Schedule an audit every few features.** Run the mechanical checks, then read the code
   against the document. Fix drift in its own change.

The templates used here are in `toy-project/AGENTS.md`, `toy-project/ARCHITECTURE.md`, and
`toy-project/journal/README.md`. Copy them, then replace the content with your own project's.

---

## 8. What this paper does not yet show

- A human review. The independent review was done by an agent, which is useful but is not a
  substitute for a person who owns the system reading the code.
- The process at scale, with many contributors, long-lived branches, or a large legacy
  codebase.
- Quantitative measurement of time saved or understanding gained. The evidence is qualitative
  and comes from one small project.

---

## Appendix: the record

- Repository: this directory. The git history contains one commit per step.
- Toy project: `toy-project/`. Start at `toy-project/README.md`.
- Journal: `toy-project/journal/`, one file per step, in order.
