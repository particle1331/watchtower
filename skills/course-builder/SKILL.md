---
name: course-builder
description: End-to-end workflow for building courses under courses/ in this repo. Covers scaffolding via wt new course/chapter/section, the index-page (course home) structure, sidebar naming rules in _quarto.yml, chapter writing conventions, and the problem/solution exercise layer with its ROT18-encoded solution cells. Use when creating a new course, adding chapters or sections, registering or renaming sidebar entries, or authoring course problems and solutions.
---

# Course builder

Workflow for creating and extending courses in `courses/`. The existing
courses (`courses/cla`, `courses/ml-platform`) follow these conventions and can be
consulted as concrete instances.

## Course anatomy

A course lives at `courses/<name>/`:

- `index.ipynb`: the course home page.
- `NN-topic.ipynb`: one notebook per chapter, zero-padded two-digit prefix.
- `img/`: figures referenced by notebooks (cover image, static diagrams).

The sidebar registration lives in `_quarto.yml` under `website.sidebar`.
Rendering never executes code (`execute.enabled: false`), so what appears on
the site is whatever outputs were last stored by `wt run`.

## Scaffolding

1. `wt new course <name> "<Title>"`: creates `courses/<name>/` with an index
   notebook and a first chapter stub.
2. `wt new chapter <course> <name> --title "<Full title>" [--section "<Name>"]`:
   scaffolds the chapter notebook and registers it in the sidebar. Sidebar text
   and notebook frontmatter are independent surfaces; adjust both after
   scaffolding (see Sidebar naming).
3. `wt new section <course> <name>`: adds a grouping header to the sidebar
   without touching notebooks.

Cell indices shift after every `insert-cell`/`remove-cell`; re-read with
`wt cat` or `wt count` before further positional edits.

## Index page (course home)

Structure: short introduction, contents / learning path, prerequisites,
important notes.

1. **Cell 0, YAML frontmatter**: `title`, `description`, `categories`,
   `image` (e.g. `"./img/<course>-cover.png"`). Quarto renders this title as
   the page H1, so the body must not repeat an H1.
2. **Short introduction**, one or two paragraphs: what the course is and who
   it is for, closing with the governing idea stated once as a bolded design
   rule ("**Design rule:** ...").
3. **Contents / learning path**: a markdown table, one row per chapter, short
   label plus a one-line description of what it covers. Group rows by phase or
   part when the course has natural stages, matching the sidebar sections.
4. **Prerequisites**: bullet list split between tooling (with links) and
   assumed knowledge.
5. **Important notes**: anything required before starting. When a project
   under `projects/<name>` backs the course, link it here and state what it
   contains relative to the chapters. Courses with rigid notation add their
   conventions here too.

## Sidebar naming

- Each entry is `- text: "NN. <short label>"` with `href:` pointing at the
  chapter notebook.
- **The sidebar label must be shorter than the notebook's frontmatter title.**
  Sidebar space is tight and readers scan short labels. Keep qualifiers,
  subtitles, and hedging out of the sidebar; put them in the frontmatter title
  instead.
- Group chapters under `- section:` headers when there is a natural grouping:
  thematic ("Computation") or phase-based ("Phase 1: Reproducible ML"). A
  section's `href:` points at its first chapter.
- After `wt new chapter`, open `_quarto.yml` and set the final short label;
  the scaffold writes placeholder text derived from the filename.

## Chapter anatomy

- Cell 0: YAML frontmatter with `title` (full descriptive title) and
  `categories`. No H1 in the body; the frontmatter title becomes the page H1.
- Lead paragraph immediately after frontmatter, no header above it: why this
  chapter exists and how it connects to adjacent chapters.
- Body: prose-first `##` sections. Every code cell is introduced by a markdown
  cell; post-code commentary interprets results rather than restating code.
- Figure cells carry their Quarto options at the top:
  ```
  #| label: fig-<name>
  #| fig-cap: "..."
  #| code-fold: true
  ```
- Non-obvious code lines get numbered annotations `# <1>`, `# <2>`; the
  following markdown cell explains each annotation in order.
- Determinism: seed RNG once near the imports; a plot-setup cell fixes the
  output format for all figures.
- Voice, emphasis, math, callouts, footnotes: defer to `notebook-writing-style`.
  Cell-option syntax details: defer to `quarto-jupyter`.
- Re-execute edited cells with `wt run` before finishing; the site renders the
  stored outputs verbatim.

## Problems & solutions

Identification is by Jupyter tags; pairing is by shared id tag, never by
position.

- **Problem statement**: markdown cell tagged `problem` + id `<chapter>-<n>`
  (e.g. `07-3`). Heading form `### [P<NN>.<N>] Title`, where NN is the chapter
  number from the notebook filename and N counts problems within the chapter;
  the text after the bracketed id is the statement title.
- **Starter code**: optional code cell right after the statement (theory
  problems have none).
- **Solution**: code cell tagged `solution` + the same id, directly after the
  starter or statement (pairs must occupy consecutive cells; `wt check`
  enforces problem → optional starter code cell → solution). Its source starts
  with a hide-on-render options header
  (`#| echo: false`, `#| eval: false`, `#| output: false`) followed by the
  ROT18-obfuscated body (letters shifted by 13, digits by 5), each non-empty
  line prefixed `# `. Blank lines stay blank. Obfuscation is a spoiler guard,
  not security.

Authoring rules:

- Adding a problem:
  `wt add-exercise <course> <chapter> --statement X [--starter X] --solution X`
  is the only sanctioned creation path. It numbers automatically (next in the
  chapter) and encodes the solution on write, so plaintext never reaches the
  notebook through this command.
- Updating: `wt solution-edit <course> <locator> --content X` (plaintext in,
  encoded stored). Reading: `wt solution <course> <locator>` decodes one
  solution; `wt hint` gives progressive hints (level 1: check descriptions and
  first sentence of the worked text; level 2: full worked text, never the
  answer); `wt cat <path> --tag <id> --decode` reads a stored cell decoded.
- Never hand-write a solution cell with `edit-cell`/`insert-cell` in
  plaintext; a plaintext solution fails `wt check`. To edit an existing
  solution cell directly, read it decoded first, then re-store it via
  `wt solution-edit`.
- Run `wt check <course>` after any problem or solution work; exit 1 means fix
  before committing.

Locators: `7.3`, `07-3`, `07 3`, `<chapter-stem> 3` all resolve to the same
problem.

## Editing loop

1. Locate: `wt find <query>`, or `wt cat --tag/--label` when the cell has a
   stable tag or Quarto label.
2. Read context: `wt cat <path> --index N --context 3`.
3. Mutate: `edit-cell`, `insert-cell`, `append-cell`, `remove-cell`, one
   locator per mutation; delete ranges highest-index-first.
4. Review: `wt diff <path>`.
5. Execute changed cells: `wt run <path> --index N` replays the prefix in a
   fresh kernel and writes back only the target cell's outputs.

## Verification checklist

- Every edited code cell re-executed via `wt run`, exit code 0.
- `wt check <course>` clean after any problem/solution work.
- `wt diff <path>` reviewed against intent before commit.
- Sidebar entries consistent: unique ids, hrefs resolve to real files, labels
  shorter than frontmatter titles.
