# Chapter authoring and notebook workflow

Read this reference when creating, writing, editing, or reviewing a numbered
course chapter. Also follow `notebook-writing-style`; read `quarto-jupyter`
when the chapter uses Quarto-rendered notebook features.

## Establish the chapter contract

Before editing an ordinary chapter:

1. Run `wt context <chapter>`; read the catalog record and course navigation. Writing briefs apply only while Planned; started notebooks own the content.
2. Read the course CMS `home` fields through `wt context`, `00-overview.ipynb` when present, and target
   chapter with `wt cat` when they have been started. For a Planned chapter,
   read the `plan` in `wt context <stable-id>` and start it when notebook authoring is requested.
   Read adjacent chapter openings only for a relevant handoff.
3. Read the backing project's `AGENTS.md` when one exists.
4. Identify the concept taught, reusable artifact added, controlled result,
   and handoff promised by the overview.

Do not reload the course-home authoring reference merely to write an ordinary
chapter. Return to it only when the index, Chapter 00, or course-wide contract
must change.

## Chapter anatomy

- Source contains one full-title H1 matching catalog `title`; generated copies
  receive document metadata. Chapters have no tags or categories; their course
  and section define their place in the learning path.
- Begin with a lead paragraph, without a heading, that states why the chapter
  exists and how it connects to adjacent chapters.
- Use prose-first `##` sections. Every code cell must have descriptive
  Markdown immediately before it.
- Interpret code outputs after the code. Do not restate the implementation.
- Put reusable computation in the backing project. The notebook introduces,
  exercises, and interprets it rather than maintaining a copy.
- Use numbered annotations `# <1>`, `# <2>` for non-obvious code lines and
  explain them in the following Markdown cell.
- Seed random generators once near imports when determinism matters.
- Keep plotting configuration in one setup cell so figure output is stable.
- Figure cells use Quarto options such as:

  ```text
  #| label: fig-name
  #| fig-cap: "..."
  #| code-fold: true
  ```

## Notebook editing loop

Never inspect or edit raw `.ipynb` JSON.

1. Orient with `.venv/bin/wt map` and `wt ls`.
2. Locate content with `wt find`, a stable Jupyter tag, or a Quarto label.
3. Read the target cell with `wt cat <chapter> --index N --context 3`.
   For shared edits add `--with-revision` and retain the `notebook:<hash>` token.
4. Mutate with `wt edit-cell`, `insert-cell`, `append-cell`, `remove-cell`, or
   `tag`. For shared edits pass the token with `--expected-revision`.
5. Review the content change with `wt diff`.
6. Re-execute every edited code cell with `wt run <chapter> --index N`, using
   a fresh notebook token with `--expected-revision` for shared execution.
   Markdown-only edits need no kernel run.
7. Inspect stored text and image outputs with `wt output` or
   `wt cat --with-outputs`.
8. Render the affected page and inspect its presentation.

Cell mutations accept exactly one locator. Indices shift after insertions and
removals, so re-read indices after every structural change. `edit-cell` does
not shift indices. Notebook tokens cover source, metadata, and outputs; every
save invalidates the old token. Re-read before another guarded write and after
a conflict; do not retry stale writes automatically. Preserve existing
cell-level visibility and folding options.

## Verification

- Every edited code cell exits successfully and has current stored output.
- The chapter still matches the handoff promised by the index and overview.
- Equations, figures, tables, annotations, and internal links render correctly.
- `wt diff` contains only intended notebook content changes.
- TOC labels remain shorter than full catalog titles.
