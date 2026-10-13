---
name: course-builder
description: Plan, build, and revise Watchtower courses through the CMS and CLI, including course briefs and ordered outlines, course homes and technical overviews, chapter notebooks, exercises and just-in-time assessment, and multi-chapter orchestration. Use for course-level planning, creation, extension, migration, or authoring.
---

# Course builder

Use the repository's `.venv/bin/wt` notebook commands and follow the local
`AGENTS.md`. Run `.venv/bin/wt map` first; `wt` below means `.venv/bin/wt`
from the repository root. Inspect command help for current arguments. Never
inspect or edit raw `.ipynb` JSON. Quarto renders stored
outputs without re-executing notebooks, so code changes are incomplete until
their cells have been run and inspected.

## Route the task

Read each required reference completely before acting. Load only the references
that apply to the current task.

| Task | Required reference |
|---|---|
| Plan or scaffold a course or chapter; organize the ordered outline | [Course structure and navigation](references/course-structure.md) |
| Create or revise the CMS course home, `00-overview.ipynb`, the course promise, or the whole-course technical contract | [Course home and Chapter 00](references/course-home.md) and, for new files/navigation, [Course structure](references/course-structure.md) |
| Write, edit, execute, or review an ordinary chapter | [Chapter authoring and notebook workflow](references/chapter-authoring.md) |
| Add, edit, remove, or review exercises, starter code, or existing solutions | [Course problems and solutions](references/exercises.md) plus [Chapter authoring](references/chapter-authoring.md) |
| Build or migrate multiple chapters; coordinate parallel work or subagents | [Multi-chapter orchestration and subagents](references/orchestration.md), then the references for each delegated task |

For notebook prose, also use `notebook-writing-style`. For Quarto options,
figures, tables, Markdown outputs, Mermaid, or render troubleshooting, also use
`quarto-jupyter`.

## Workspace and preview isolation

For a new course or a multi-file course revision, work from a dedicated Git
worktree whenever the environment permits it. This keeps the user's primary
checkout and its site preview usable while the course is being authored. Use an
existing task worktree when one is provided; otherwise create a sibling
worktree from the task's starting commit, for example:

```bash
git worktree add ../watchtower-course-<slug> -b codex/course-<slug>
```

Check `git status` before creating it. Do not reset, clean, or copy over a dirty
primary checkout, and do not silently create a worktree from `HEAD` when the
task depends on uncommitted user changes. Use a worktree that contains the
needed starting state or say in the update that the changes cannot be isolated
safely.

Serve the isolated worktree's working preview on a free port, usually 4300:

```bash
make preview PORT=4300
```

When both CMS and preview are needed, `make dev PORT=4300 CMS_PORT=5300`
starts both and opens browser tabs. For agent verification without opening
tabs, use `.venv/bin/python scripts/dev.py --no-browser --port 4300 --cms-port 5300`.
Do not stop the user's existing servers; choose free ports. Include the exact
URLs of servers you started in progress updates and the final handoff.
A different port without a different worktree does not isolate source or
generated output. Plan-only work needs managed-data validation, not a site preview.

## Course content after orientation

Run `wt context <id-or-path>` first, then read the course contract at
`backend/data/courses/<slug>.yaml` for navigation and public summaries. Writing briefs apply only while Planned. For a Planned artifact, use the `plan` in `wt context <stable-id>` and organize its brief
and outline without requiring source notebooks. Start drafts when the request
includes notebook authoring; see [Course structure](references/course-structure.md)
for creation and one-time seeding rules.

For started content, read the contract `home` fields through `wt context` (the learner-facing home),
`00-overview.ipynb` when present, and the target chapter through `wt cat`.
Read adjacent chapter openings only when a handoff matters; do not load all
sibling chapters. Return to the course-home authoring reference only when the
course home, overview, or course-wide contract must change. Internal notes stay
out of rendered pages. Use the entity’s separate Notes (`internal_notes`, Markdown) and To-dos (`internal_todos`, ordered `{text, done}` items) fields to localize unfinished understanding and work. The modal supports adding, checking and removing items, with completed/total progress; agents save the checklist through an artifact patch. Linked Kanban cards carry scoped execution context. Before marking a task Done, put accepted results in the notebook and lasting unresolved context or follow-up work in internal notes.

Starting consumes the plan. Draft and Published content is committed memory: CMS `home` fields for course homes, notebooks for chapters. Consumed briefs are hidden from the CMS and active agent context, and plan writes are rejected. Planned courses may keep internal notes and to-dos while refining the home; other planned entries must have empty internal notes. After starting, read `wt context` for the course home and `wt cat` for chapters. Record unfinished decisions in internal notes. Flag material changes to purpose, audience or scope unless already authorized; revise committed content once agreed.

## Universal invariants

- Put cumulative reusable computation in the backing project and use notebooks
  to derive, exercise, and interpret it.
- Preserve user changes in a dirty worktree and avoid overlapping parallel
  writes.
- Mutate notebook cells only through `wt`; re-read indices after insertions or
  removals. For shared notebook edits, carry the `cat --with-revision` token
  through `--expected-revision`; re-read after a conflict or intervening save.
- Add new exercises through the ordinary `wt` cell commands. Do not require
  stored solutions; assess learner answers when asked. Preserve any existing
  encoded solution cells unless the user requests a change to them.
- Re-execute edited code cells, inspect stored outputs, review with `wt diff`,
  and render affected pages.
