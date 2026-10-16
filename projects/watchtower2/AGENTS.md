# Watchtower2 prototype instructions

These instructions apply inside `projects/watchtower2/`. Follow the repository's
general safety and tooling rules. This project is an independent prototype,
not an approved migration or replacement of the working CMS.

## Orientation

- Start with [the plan](docs/README.md), then the relevant v1 walkthrough/source
  path and [development stage](docs/development-plan.md).
- Existing `.venv/bin/wt` commands run from the repository root and inspect v1.
  Use them for read-only reverse engineering. They are not aliases for `wt2`.
- The future prototype executable is `wt2`. It is not implemented in the initial
  scaffold; do not imply a command exists before it does.
- This is an independent uv project, excluded from the root workspace. Run its
  dependency/environment commands from this directory. Keep its own `uv.lock`
  and `.venv/`; do not add prototype providers to v1's dependencies.
- Canonical prototype documents live in this project's `docs/`.

## Guided implementation

For each workflow: inspect v1 code and observed behavior, explain its data flow
and failure cases, propose a specific improvement, then implement a small slice.
Show the user the relevant diff, stored changes and evidence. Record questions
and decisions locally. Acceptance of behavior and understanding drives progress;
avoid an unexplained backend rewrite.

Build the application use case and CLI behavior before its full Flet surface,
with an early thin Flet integration. Preserve useful domain behavior and explain
intentional differences. Keep components small, editor state explicit, and
event handlers thin. Domain code must not depend on Flet, SQL clients or storage
SDKs. Keep GUI dependencies outside the headless CLI/core boundary.

## Data and publishing isolation

- Require an explicit prototype environment, database, B2 namespace and content
  workspace before enabling writes. Do not infer active v1 stores as defaults.
- Use verified copies/fixtures or a dedicated worktree for source experiments.
  Never run prototype mutations against the active `content/notebooks/`, managed
  backend data/assets/attachments, or current deleted archives.
- Use separate ports, runtime/generated directories, credentials and publishing
  targets. Keep secrets in the OS keyring; never print or commit values.
- Content notebooks are authored source; frontend notebooks are disposable
  generated projections. Builds must not write generated metadata into content.
- Managed deletion and GC go through the prototype backend. Run GC during active
  sessions/startup or explicit requests; no always-on worker is required.
- Prototype CI/release experiments must not alter the live website workflow,
  Pages configuration or domain.

## Scope and housekeeping

Keep implementation and notes under this project. Use ignored `.tmp/` for scratch,
`.runtime/` for local state, and `generated/` for disposable build output. Do not
copy managed payloads into tracked experiment folders.

Follow the repository's required checks for code changes. Document-only changes
need link/format review. Do not create empty test/service/module hierarchies or
install providers just to make the scaffold look complete.

Root AGENTS.md, existing skills, scripts and `wt` remain about the working system.
Any adoption/migration decision is separate future work. Reusable fixes to v1
must be deliberately scoped rather than slipped into a prototype slice.
