# Watchtower2

An independent prototype for understanding Watchtower v1 and improving its design.
The proposed stack is a `wt2` CLI and declarative Flet interface over shared Python
application services, with Turso records, Backblaze B2 files, and explicit garbage
collection policies. Adoption or migration is a future decision.

## Start here

1. Read the [prototype plan](docs/README.md) and [local agent instructions](AGENTS.md).
2. Follow [the v1 walkthrough](docs/current-system.md) using read-only inspection.
3. Work through the [guided stages](docs/development-plan.md): explain v1, propose
   an improvement, implement a small slice, demonstrate it, and review together.

## Course learning path

The Draft/private course **AI-Assisted Development: Building Watchtower2** uses
this prototype as its running application. Its
[initial overview](../../content/notebooks/courses/ai-assisted/00-watchtower2-overview.ipynb)
explains the proposed architecture and development sequence. Chapters 01–16 have
saved writing plans and no source notebooks yet. Read the course home, ordered
outline and public summaries with `.venv/bin/wt context course/ai-assisted` from
the repository root. Course plans describe intended learning and evidence;
implemented behavior must be established by each subsequent development slice.

## Current state

This project contains a Python package scaffold and the design/learning plan.
The backend, provider integrations, Flet application, and `wt2` executable are
not implemented yet. No provider dependencies or credentials are configured.
The scaffold deliberately has no Hello World command pretending to be `wt2`.

The project is registered as `project/watchtower2`, Draft/private. It is excluded
from the root uv workspace and owns its dependency lockfile/environment. Its
Python code has no dependency on the v1 package; data, credentials, source copies,
ports and generated output must also be isolated when implementation begins.

## Layout

```text
projects/watchtower2/
  AGENTS.md                   Project-local working rules
  README.md                   Project entry point
  pyproject.toml              Minimal package metadata
  uv.lock                     Prototype-only dependency lock
  src/watchtower2/__init__.py Package marker
  docs/                       Canonical plan and walkthrough
```

Scratch, runtime databases and generated files belong in ignored project-local
directories. Add real modules as the guided slices need them; avoid empty layers
or speculative services in the scaffold.

Run future project-local uv commands from `projects/watchtower2/`. Its environment
will live at `projects/watchtower2/.venv/`, separate from the root environment used
to inspect v1. No provider or GUI dependencies have been added yet.

## Development boundaries

- `wt` and the current CMS/site continue to operate independently.
- `wt2` will call the prototype's application services; Flet will call those same
  services, with framework/provider code kept at the boundaries.
- Use copied fixtures or a dedicated worktree for notebook/source experiments.
- Prototype uploads, deletion, GC and release tests use explicitly isolated stores
  and publishing targets. They never operate on active v1 data.
- Keep current root agent instructions, skills, scripts and deployment pointed at
  their existing system. Changes to adoption are outside this prototype's scope.
