# Watchtower CMS v2: prototype and reverse-engineering plan

[Project home](../README.md) · [Project-local agent instructions](../AGENTS.md)

**Status: separate prototype, 2026-10-15.** Reverse engineer the current CMS,
understand its behavior, and improve the design through small experiments.
Whether to adopt v2 or migrate is a future decision. This plan authorizes no
live migration, production configuration change, or provider provisioning.

The prototype explores today's features with a database for editable records,
object storage for managed files, and cleanup that is safe and measurable.
Current behavior is evidence to study; improvements are explained and reviewed
as we go. An equally important goal is that you can explain and maintain it yourself.

## Scope and isolation

- `wt` and the current CMS remain the working system.
- `wt2` and Flet are a separate prototype using isolated data, storage namespaces,
  source copies/worktrees, ports and output directories.
- Study v1 through read-only inspection and captured fixtures/exports. Prototype
  writes and destructive experiments never target the active v1 workspace.
- Keep prototype guidance in these documents and its own implementation docs.
  Do not redirect root AGENTS.md, current skills, scripts or deployment to v2.
- Evaluate the prototype before deciding whether to keep experimenting, reuse
  selected improvements, or plan adoption as a separately agreed project.

## Start here

Read these in order. The first walkthrough should happen before implementation.

| Document | What you should understand afterward |
| --- | --- |
| [1. The current system](current-system.md) | What exists, what happens during a save, and which features v2 must preserve. |
| [2. Target architecture](architecture.md) | What belongs in Turso, B2, Git, and local disk; how changes succeed or recover. |
| [Website deployment](website-deployment.md) | How content notebooks become frontend notebooks, rendered output, and a deployed website. |
| [CLI v2 and declarative Flet](cli-v2-and-flet.md) | How the interfaces share a backend, what changes in the UI, and why CLI-led development is recommended. |
| [3. Retention and garbage collection](retention-and-gc.md) | What is kept, what can disappear, and how deletion avoids damaging live work. |
| [4. Development stages](development-plan.md) | What we build first, what you learn, and what evidence completes each stage. |
| [5. Prototype operations and future adoption notes](migration-and-operations.md) | How the prototype recovers and operates; migration/cutover notes are deferred reference only. |

These documents describe a target, not an implemented API. Proposed table,
module, and file names are examples until their implementation stage. Existing
v1 commands use the repository-root `.venv/bin/wt`; the prototype executable will
be `wt2` in the project's own environment (`projects/watchtower2/.venv/bin/wt2`
from the repository root). Future commands are described in prose;
the `wt2` executable is not implemented yet.

## The central decision

| Storage | Its job |
| --- | --- |
| **Turso** | Editable CMS records: plans, metadata, notes, checklists, cards, relationships, file ownership, operations, revisions, and retention records. |
| **Backblaze B2** | Managed attachment and image bytes, retained exports, and protected backup objects. |
| **Git** | Authored notebooks and sidecars, project code, application code/templates/configuration, schema migrations, and deliberately exported publication manifests. |
| **Ignored local disk** | Download cache, generated frontend notebook copies and QMD pages, render projects, build outputs/logs, and recoverable filesystem staging. |

A notebook's stored outputs and inline attachments remain part of its authored
file. Moving context attachments into B2 does not remove those notebook bytes
from Git. Moving or clearing notebook outputs would be a separate authoring
decision.

Content notebooks and frontend notebooks are distinct: source files own authored
content; frontend copies receive generated metadata/wrappers and are rendered by
Quarto. They are regenerated in ignored build stages and follow build GC.
See [the notebook layers](architecture.md#content-notebooks-and-frontend-notebooks).

Ordinary card, note, plan, photo, or metadata saves should produce **no tracked
file changes**. Editing an authored notebook or deliberately preparing a release
can produce a Git diff. Local CMS saves continue to be separate from deployment.

## Decisions and assumptions

| Item | Status |
| --- | --- |
| Current features and routes as a reference | Reverse engineer the [behavior checklist](current-system.md#feature-parity-checklist), demonstrate the features in v2, and review intentional improvements. No live replacement is implied. |
| Turso for records; B2 for managed bytes | User direction. Exact Turso engine and Python driver require a capability spike. |
| Keep notebook bodies and project source in Git | Recommended boundary, preserving the current authoring workflow. |
| Declarative Flet CMS and CLI v2 | User direction for the prototype. Build a Flet interface and shared backend; study the existing API as a behavioral reference. |
| V2 command name | Confirmed by you: `wt2`. The current `wt` stays independent. Give the prototype its own documented command/output contract; adopting it is a later decision. |
| Flet interface tradeoff | Accepted by you: rebuild the CMS screens and replace the HTML/no-JavaScript fallback in favor of richer components and readable declarative code. Preserve functional behavior and accessibility. |
| Website build and deployment | Prototype frontend-notebook rendering and artifact deployment in an isolated target. The live site's workflow, Pages settings and domain stay outside prototype scope. |
| CLI-led implementation | Recommended. Build each use case through CLI v2, then its Flet screen; integrate a thin screen early rather than waiting for the entire CLI. |
| Run the CMS locally at first | Confirmed by you. The CMS stays local; Turso and B2 are remote. |
| Access the remote database directly at first | Recommended starting point: online writes with explicit failure handling. Offline writable replicas add a separate synchronization problem. |
| Guided implementation in small reviews | Confirmed by you. You inspect a working action and its failure case at each stage before we proceed. |
| Backend owns deletion and GC | Confirmed by you. Support straightforward direct deletion and configurable policies through one shared service, exposed by CLI v2 and Flet. |
| GC runs during active use | Confirmed by you. Run cleanup at startup, after relevant operations, periodically while the backend is active, or explicitly through CLI/CMS. No always-on worker is required while the laptop is closed. |
| Managed deletion uses backend entry points | Confirmed by you. CLI/CMS/API and policy workers coordinate removal; filesystem/B2-console deletion is an explicit repair path. Content notebook/code editing remains in normal editors. |
| Retention durations | Proposed defaults, reviewed before enabling physical deletion. |
| Historical release rebuilds | Recommend a bounded rebuild set, with explicit named pins for releases worth keeping longer. Review the retention tradeoff in stage 7. |

The backend should be one deployable application with clear internal modules.
A database and object store already introduce enough failure modes; this plan
does not require a collection of microservices.

The CLI and Flet application are interfaces to the same application core. The CLI
works without starting Flet. Recommend a local Python-backed browser application
initially; native desktop packaging is a separate delivery choice. The public
Quarto site stays separate from the CMS interface.

## Readiness review

**2026-10-15:** the architecture is sufficiently defined for the guided walkthrough
and disposable prototypes. The v2 backend and provider behavior remain unproven.
The following register makes remaining choices explicit; resolve them at the
listed stage, rather than treating every recommendation as an accepted contract.

| Open item | Decision/evidence required | Resolve by |
| --- | --- | --- |
| Provider implementation | Turso engine/driver, local test engine, transactions/constraints, consistent reads, unknown commits, B2 exact-version permissions, Python compatibility | Stage 1, before relying on provider semantics. |
| Flet delivery and editor behavior | Browser versus native target; full-size uploads; keyboard/math/navigation; unsaved-draft lifetime, crash behavior and connection loss | Stage 1 prototype, then real integration in stage 3. |
| CLI/API design and safe upgrades | Define the prototype's commands, JSON fields and API behavior, documenting differences from v1. Keep existing consumers unchanged. Define headless installation and version gates for prototype data. Full v1 command compatibility is not assumed. | Stages 2–3 prototype contracts and upgrades. |
| Workspace and branch binding | One writable authoring checkout initially; disposable dev/test environments; bootstrap on another machine; coordination of source files and remote metadata | Stages 2–3 configuration, source-operation proof in stage 6. |
| Recovery and retention | Prototype deletion/undo/release durations; whether metadata edits have bounded per-entity history; backup frequency, acceptable data loss and restore time; protection of required object versions | Decide history before stage 2 schema; demonstrate retention and restore in stage 5 isolated resources. |
| Active-session operation and budgets | Startup/post-operation/periodic cleanup, bounded catch-up after inactivity, visible failures, storage/transfer limits, measured latency and safe quota behavior. Backup timing remains part of the separate recovery decision. | Design in stage 5; demonstrate in stage 8 evaluation. |
| Release and live-site semantics | Manifest format, commit binding, release-only deployment trigger, historical rebuilds after ordinary merges, withdrawal of live content, and stale deployment prevention | Stage 7 before enabling the new deployment path. |

The [parity checklist](current-system.md#feature-parity-checklist) is a baseline
inventory. Its rows still need a v1 walkthrough and v2 evidence, including
integrity failures, lost responses, interrupted source operations, deletion
races, restore, and rollback. Document coverage is not proof of implementation.

Start with one complete disposable action: create/read/move a card through CLI
v2, reject a competing stale write, and inspect the resulting rows. Then connect
one Flet screen. Use that evidence to refine the next slice and estimates.

## How development stays understandable

Each stage produces a small learning packet alongside the code:

1. **Before:** a short explanation of the problem, inputs, stored changes,
   invariants, and likely failures. Define unfamiliar terms when they appear.
2. **Trace:** follow one action from the button or CLI through the use case to
   the rows, files, or objects it changes. Show the actual source locations.
3. **Build:** implement one coherent action with a reviewable diff.
4. **Demonstrate:** show success, a conflict, and a relevant interrupted or
   failed operation. Inspect real records without exposing credentials.
5. **Explain back:** you describe where the data lives and what happens if the
   action fails. Questions or disagreement become work for that stage.
6. **Record:** save the decision and evidence, including limitations. Move on
   when both behavior and explanation are accepted. Silence is not evidence
   that the explanation was understood.

Passing tests supports a claim; the review must also explain which rule each
important test proves. Avoid a large unexplained rewrite followed by a test count.

## What “prototype complete” means

- Every parity item has evidence, or an explicitly agreed change to its contract.
- Prototype CMS state and managed uploads produce no routine Git accumulation.
- Prototype production-mode builds consume a frozen release, without querying editable
  CMS records. Private plans, notes, cards, and context files stay out of it.
- Garbage has bounded retention, visible accounting, safe retries, and tested
  protection for live content, releases, and backups.
- Restoring a database also restores access to every required object version.
- Read-only fixture comparisons account for IDs, notebook bytes, routes, order,
  task numbers and reservations, with intentional differences explained.
- You can trace creating a plan, starting a notebook, attaching a file, resolving
  a stale save, deleting content, publishing a release, and diagnosing a failure.
- Evidence and remaining limitations support a future adoption decision; a live
  migration or cutover is not required to complete the prototype.

No fixed delivery estimate is attached to this plan. The provider spike and
feature inventory must establish the remaining work before estimating it.

## Small glossary

| Term | Meaning here |
| --- | --- |
| Source of truth | The authoritative copy of a particular kind of information. |
| Use case | One application action, such as Move card or Start chapter. |
| Transaction | A database change that commits together or does not commit. |
| Revision / compare-and-swap | Save only if the version you read is still current. |
| Idempotency key | A request identifier that lets a retry discover the original result without repeating its effect. |
| Blob | File bytes independent of their display filename or owner. |
| Root / pin | A retained reference that protects an object from garbage collection. |
| Lease | Temporary ownership of work, with expiry and renewal. |
| Fencing token | A generation checked before accepting a worker's changes, so an old worker cannot finalize newer work. |
| Tombstone | A small retained identity record for something removed. |
| Release manifest | A frozen description of the inputs needed to build a particular public site. |
| ADR | A short architecture decision record: context, options, choice, consequences, and evidence. |
