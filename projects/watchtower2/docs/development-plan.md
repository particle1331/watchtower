# 4. Development stages

[Plan index](README.md) · Next: [prototype operations](migration-and-operations.md)

Build v2 as CLI-led working vertical slices. A vertical slice follows one
action through application rules, storage, the CLI, and then Flet. Reverse engineer
each v1 workflow before designing its prototype equivalent and explaining changes.
The existing system remains independent. Each stage may require
several small changes; the stage is a review boundary, not a request for one
large pull request.

The v2 CLI is named `wt2`, separate from the current `wt` entry point. Stage 2
implements its headless executable and command/output contract. Existing `wt`
examples remain v1 reference material. Keep prototype instructions separate;
switching existing agents/scripts to `wt2` is outside this prototype plan.

Recommend CLI v2 generally one slice ahead of Flet, with the first real Flet
screen integrated by stage 3. The CLI can become independently useful before
the complete GUI; do not defer all UI discovery until the CLI is finished.
See [CLI v2 and declarative Flet](cli-v2-and-flet.md).

## Before the first implementation

Use [the current-system walkthrough](current-system.md) together. Pick a real
chapter and card, inspect their context with the CLI, and trace a save through
the current code. Explain three different things: saving, committing, and
deploying. Collect questions in this plan rather than silently filling gaps
with more code.

Every stage records:

- A plain-language brief and one action diagram.
- A small implementation diff and updated source reading path.
- A demo transcript or screenshots, plus inspected rows/object versions where useful.
- Tests linked to named invariants, including a relevant failure case.
- An ADR if a durable architecture choice was made.
- Your questions, your explanation of the action, and the agreed next step.

Use an ADR with **Context / Options / Decision / Consequences / Evidence / Open
questions**. Keep the decision separate from its implementation. Do not mark a
stage complete solely because a test command exits successfully.

## Roadmap

### Stage 0 — Agree on the behavioral contract

**Learn:** models, adapters, services, the workspace gate, generated output,
and why Git history differs from local disk usage.

**Deliver:** these design documents, a current inventory, the parity checklist,
and three traced examples: edit notes, attach a file, build a page. Mark user
preferences and recommended defaults separately.

**Completion evidence:** you can point to the authoritative copy of a card,
notebook, image, publication state, and site output; explain a stale revision;
and identify what changes when you press Save. Update the checklist for any
behavior discovered during the walkthrough.

### Stage 1 — Prove the providers and Flet fit

**Learn:** SQL tables/keys/transactions, object keys/versions, consistency,
and the difference between a local test double and a hosted service.

**Deliver:** disposable provider experiments and a short capability report.
Choose the Turso engine/driver, database migration approach, B2 client, initial
bucket separation, and online/offline policy. Verify Python/runtime compatibility,
permissions, timeouts, backup/PITR capabilities, exact-version deletion, checksum
verification, and actual cost/usage limits before committing to configuration.
Record unresolved capabilities as blockers to the affected design, not guesses.

**Completion evidence:** two clients compete for the same revision; one wins.
A transaction rolls back. A timed-out request is resolved without duplication.
A private object uploads, verifies, downloads, and is permanently deleted by
exact version. No provider experiment uses live content or deletion credentials
for an existing bucket. Provisioning requires the appropriate account access;
the current documentation task does not create services.

Also make a small disposable declarative Flet prototype: dirty forms/dialogs,
conflict display, drag plus explicit Move, file upload, Markdown/math,
keyboard/focus, navigation, and a long job. Pin a compatible version and record
browser/OS behavior. Do not build the entire interface at this stage.

### Stage 2 — Deliver the first headless CLI v2 slice

**Learn:** application boundaries, schema migrations, conditional writes,
foreign keys, and tests that prove a rule.

**Deliver:** an isolated v2 application skeleton and a Kanban slice: create,
read, move, and remove a card with permanent numbering. Define help, typed inputs,
versioned JSON/readable output, errors, and environment selection. Preserve current
CLI intent through adapters. Add board revisions and request receipts. Avoid
attachments and artifact-linked context until the basic transaction is clear.

**Completion evidence:** inspect the exact rows changed by a move; a stale move
changes nothing; rollback leaves the counter and card consistent; removing a
card never reuses its number. Ordinary card mutations create no tracked Git diff.
The CLI works without Flet installed or running; domain code imports no UI framework.

### Stage 3 — Run that slice through Turso

**Learn:** network failure differs from application rejection; request identity
differs from edit revision; job retries need durable state.

**Deliver:** the production database adapter, transaction boundaries, version
tokens, error mapping, operation status queries, migration checks, and isolated
test configuration. Use the same use cases as stage 2.

**Completion evidence:** simultaneous real clients; lost response after commit;
database outage; expired request; wrong-environment configuration. Demonstrate
how the user learns whether a save happened. Unrelated content edits leave a
board token usable. Tests use isolated namespaces, never the authoring database.

Then connect a real declarative Flet card editor/move screen to the same use cases.
Demonstrate that CLI and Flet observe each other's changes and the same conflicts.
This establishes the shared interface contract before broad feature implementation.

### Stage 4 — Add verified B2 files and ownership

**Learn:** file bytes versus ownership, logical digest versus physical version,
upload finalization, and why cross-store work has intermediate states.

**Deliver:** upload intents, checksum verification, owner links, private download,
deduplication, image validation, and per-owner filenames. Support task-to-entity
promotion without copying bytes. Keep existing upload limits and metadata-save
behavior. Integrate one attachment action before adding all image forms.

**Completion evidence:** two owners share bytes; removing one leaves the other
working. Rejected metadata leaves a visible orphan candidate, never a broken
ready owner. A repeated or delayed upload cannot overwrite another attempt.
Display actual database ownership and B2 key/version identities together.

Implement upload/link/download through the CLI first, then Flet file selection,
progress, and failure recovery. The Flet callback delegates verification and
ownership finalization to the core; no separate GUI storage path is introduced.

### Stage 5 — Prove garbage collection and recovery

**Learn:** reachability, roots, quarantine, leases, retryable external effects,
and how a backup changes deletion eligibility.

**Deliver:** policy configuration, dry-run reports, deletion claims, exact-version
cleanup, reconciliation, job lease handling, accounting, and backup pinning.
Provide direct unlink/delete/purge actions and policy inspection/editing through
one backend deletion service. Demonstrate blocked/scheduled/completed outcomes
and why each object is retained or removed; policy workers use the same path.
Include managed purge of copied archive fixtures and out-of-band deletion diagnostics. A
missing referenced object must not silently disappear from ownership metadata;
demonstrate recovery or explicitly coordinated retirement.
Expose these operations and reports in CLI v2 first. GUI diagnostics can follow;
CLI-triggered collection works without Flet. Run startup/post-operation cleanup
and periodic tasks while the backend is active; no external GC scheduler is required.
Demonstrate bounded catch-up after a period with the application closed.
Implement the [failure demonstrations](retention-and-gc.md#required-failure-demonstrations).
Start with disposable objects and simulated time; enable no live destructive GC.

**Completion evidence:** walk through an attach/delete race and an interrupted
delete using actual records. Repeated lifecycle cycles settle to the declared
retained set. Restore a disposable backup after live owners are removed and
verify its file bytes. An unavailable root inventory stops deletion.

### Stage 6 — Preserve the remaining authoring features

**Learn:** domain invariants across several records and the filesystem;
different actions need different consistency boundaries.

Deliver these sub-slices separately, with their parity IDs checked off:

| Slice | Work | Essential demonstration |
| --- | --- | --- |
| 6a | Catalog identity, metadata, plans, entity notes/to-dos, relations, context, creation defaults | Planned/started restrictions, ordered links, notes absent from public DTOs. |
| 6b | Course home and outline operations, chapter summaries, parent rules | Reorder/transfer commits coherently; stale outline leaves every row unchanged. |
| 6c | Source-workspace operations: Start, scaffold/register, source moves/deletion, explicit notebook operations/execution | Crash at each file/database boundary; divergent IDE save preserved; seeding never repeated. |
| 6d | Portfolio/project references, profile/résumé, per-photo gallery and managed images | Image replacement and metadata finalization; active archived-code dependency; per-photo publication. |
| 6e | Full Kanban context, search, summary tasks, declarative Flet dialogs/forms, keyboard actions and return navigation | No stale retry, no lost submitted fields/uploads, no task-driven publication changes. |
| 6f | Batch/data repair, fixture import, deletion review/cascade and reservations | Bad inputs preserved for explicit repair; deletion cannot orphan a prototype dependency. |

For each sub-slice, establish CLI/core behavior, then implement its Flet surface.
**Completion evidence:** each slice has CLI/service/API coverage and Flet evidence
where behavior is visible. Preserve the palette and familiar workflows while
rebuilding controls. Verify the accepted HTML/no-JavaScript parity adjustment in
[the interface plan](cli-v2-and-flet.md#explicit-parity-adjustment). Update the
prototype's command reference/instructions as its surface evolves. Root AGENTS.md
and current agents/skills continue to describe the working v1 system.

### Stage 7 — Freeze releases and bound build storage

**Learn:** authoring state versus a release, public allowlists, dependency
snapshots, output promotion, cache eviction, and reproducibility limits.

**Deliver:** shared renderer input contracts, live preview hydration, validated
release export and pins, isolated CI experiments, source/asset digest checks, existing URL
projection, build status/logs, explicit render/export leases, and local GC.
Demonstrate the proposed GitHub Pages artifact workflow against a disposable test
target, preserving route behavior and keeping generated output out of Git history.
Record the configuration/permission requirements without changing the live site's
workflow, Pages source or domain. Follow [the deployment design](website-deployment.md).
Keep canonical content notebooks separate from generated frontend notebooks:
capture sources, project metadata/wrappers into ignored copies, then render.
Prove that building leaves canonical source bytes unchanged and that frontend
copies are reclaimed with their build stage.
Define how exported manifests are bound to Git commits and verified deployment
receipts. Reconcile interrupted exports. Agree on the supported historical
rebuild window and implement recorded release retirement before automating it.

**Completion evidence:** edit a card or internal note and rebuild the same
release: inputs remain unchanged. A fresh checkout plus manifest and permitted B2
inputs builds without Turso. Draft/private/parent filtering and no-internal-data
checks pass. A failed render/download preserves the current site. Stress builds
and a slow export remain within policy without deleting active output.

### Stage 8 — Evaluate the prototype and choose future work

**Learn:** compare behavior and failure recovery against v1, explain tradeoffs,
measure improvements, and identify what remains uncertain.

**Deliver:** read-only fixture/checksum reports, v1/v2 behavioral comparisons,
prototype restore and release demonstrations, startup/active-session GC evidence,
documented intentional differences, and a limitations/next-experiments report.

**Completion evidence:** demonstrate the features in isolated resources and
explain each checklist item as preserved, redesigned, or still incomplete.
You can follow the code and diagnose the demonstrated failures. Review the
results together, then decide whether to keep prototyping, reuse selected ideas,
or separately plan adoption. Migration/cutover is a future decision, not a stage
that follows automatically. No prototype test deletes live objects or changes
the current CMS/site configuration.

## Working and verification discipline

Use isolated Git worktrees and isolated data environments for implementation.
Preserve the dirty primary checkout. Keep managed v1 data untouched except through
supported services or explicitly reviewed repairs.

During implementation, run the repository's lint, type checks, and relevant
tests, then its full required behavior suite. Add provider contract checks in
disposable resources and UI checks for preserved interactions. This plan itself
changes documentation only; it does not require another production render.

Track progress by evidence, for example:

| Slice | Rule | Evidence | Result | Your understanding / questions |
| --- | --- | --- | --- | --- |
| 2 | Stale move changes nothing | Test name + demo + inspected row versions | Pending | Explain which revision was compared. |
| 5 | Backup protects an unowned object | Restore report + exact version/digest | Pending | Explain why it cannot yet be deleted. |
| 7 | CI ignores live CMS changes | Two builds from one frozen manifest | Pending | Identify every build input. |

The next practical step is the **stage 0 walkthrough**, followed by the provider
spike. Writing the complete v2 backend before those reviews would defeat the
learning goal.
