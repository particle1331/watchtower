---
name: course-builder
description: Build and revise Watchtower courses under nb/courses/, including course homes and technical overviews, scaffolding and sidebar structure, chapter notebooks, exercises and encoded solutions, and multi-chapter orchestration. Use for any course-level creation, extension, migration, or authoring task.
---

# Course builder

Use the repository's `.venv/bin/wt` notebook commands and follow the local
`AGENTS.md`. Never inspect or edit raw `.ipynb` JSON. Quarto renders stored
outputs without re-executing notebooks, so code changes are incomplete until
their cells have been run and inspected.

## Route the task

Read each required reference completely before acting. Load only the references
that apply to the current task.

| Task | Required reference |
|---|---|
| Scaffold a course or chapter; add, move, or rename sidebar entries | [Course structure and navigation](references/course-structure.md) |
| Create or revise `index.ipynb`, `00-overview.ipynb`, the course promise, or the whole-course technical contract | [Course home and Chapter 00](references/course-home.md) and, for new files/navigation, [Course structure](references/course-structure.md) |
| Write, edit, execute, or review an ordinary chapter | [Chapter authoring and notebook workflow](references/chapter-authoring.md) |
| Add, edit, remove, or review problems, solutions, starter code, or hints | [Course problems and solutions](references/exercises.md) plus [Chapter authoring](references/chapter-authoring.md) |
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

Serve the isolated worktree on a non-default port, usually 4300:

```bash
.venv/bin/wt docs --port 4300
```

Include the exact preview URL, such as `http://localhost:4300/`, in progress
updates and the final handoff. A different port without a different worktree
does not isolate the files or Quarto's `_site` output.

## Course content after orientation

Once a course has `index.ipynb` and `00-overview.ipynb`, those notebooks are the
source of truth for its promise, terminology, artifact lineage, execution
profiles, chapter handoffs, and evidence standard. Ordinary chapter work should
read those pages and the target chapter, not reload the course-home authoring
reference. Return to that reference only when the course home, overview, or
course-wide contract must change.

## Universal invariants

- Put cumulative reusable computation in the backing project and use notebooks
  to derive, exercise, and interpret it.
- Preserve user changes in a dirty worktree and avoid overlapping parallel
  writes.
- Mutate notebook cells only through `wt`; re-read indices after insertions or
  removals.
- Add exercises only through `wt add-exercise` and update solutions only
  through `wt solution-edit`. Never write a plaintext solution cell directly.
- Re-execute edited code cells, inspect stored outputs, review with `wt diff`,
  run `wt check <course>` after exercise work, and render affected pages.
