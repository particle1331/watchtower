# Multi-chapter orchestration and subagents

Read this reference when creating a whole course, revising two or more
chapters, running a course-wide migration, or considering subagent delegation.
Subagents are optional; the workflow must remain valid when delegation is not
available.

## Keep the course contract centralized

The main agent owns:

- the course index and Chapter 00;
- shared terminology, notation, artifact lineage, and chapter handoffs;
- backing-project interfaces and cross-chapter schemas;
- sidebar organization;
- integration, course-wide checks, and final rendering.

Once the index and overview are stable, use them as the content contract. Load
only the target chapter, its adjacent handoffs, the relevant skill reference,
and the backing-project interfaces needed for the current task. Return to the
course-home authoring guidance only when the course-wide contract changes.

Work in artifact dependency order. Do not rewrite downstream chapters around
interfaces that have not been implemented or frozen. Preserve a short active
plan containing completed milestones, current assumptions, artifact IDs,
unresolved blockers, and the next concrete chapter handoff.

## When subagents help

Delegate work that is genuinely independent and has an explicit return
contract:

- read-only audits of separate chapters;
- focused research for different sections;
- test or exercise reviews on disjoint notebooks;
- implementation of disjoint modules behind already-frozen interfaces; or
- verification passes that can report findings without changing shared state.

Prefer sequential main-agent work when chapters share an unsettled API,
dataset, notation, evaluator, or checkpoint. Coordination overhead and
integration drift outweigh parallelism when tasks are strongly dependent.

## Delegation packet

Give each subagent only the context needed for its assignment:

1. the course `index.ipynb` and `00-overview.ipynb`;
2. the target chapter and relevant adjacent handoff;
3. the relevant course-builder reference;
4. frozen project interfaces or schemas it may use;
5. the exact deliverable, permitted files, and acceptance checks; and
6. a prohibition on touching overlapping files or redefining the course
   contract.

The main agent must read and interpret every required skill instruction itself;
do not delegate skill loading or policy interpretation. Assign one writer per
file. Parallelize audits and research freely when they are read-only; permit
parallel mutations only across disjoint files with frozen interfaces.

## Subagent return contract

Require each subagent to return:

- findings or implemented outcome;
- files inspected and changed;
- commands and checks run;
- assumptions made;
- unresolved issues or contract conflicts; and
- the exact artifact or chapter handoff produced.

The main agent re-reads every changed notebook through `wt`, reviews project
diffs, resolves cross-chapter inconsistencies, executes edited code cells, runs
`wt check` after exercise work, and renders the integrated course. A subagent's
successful local check is evidence for integration, not a substitute for it.

## Suggested course-wide sequence

1. Main agent creates or revises the index and Chapter 00.
2. Main agent freezes shared project interfaces and artifact schemas.
3. Delegate independent research, audits, or disjoint implementation work.
4. Integrate one dependency layer at a time.
5. Migrate chapters in the order promised by the overview.
6. Run course-wide exercise, execution, navigation, and render checks.
7. Update the index or overview only when measured evidence changes the
   learner-facing contract.
