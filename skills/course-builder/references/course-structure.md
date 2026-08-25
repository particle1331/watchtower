# Course structure and navigation

Read this reference when scaffolding a course or chapter, adding sections,
registering or renaming sidebar entries, or changing course-level navigation.

## Course anatomy

A course lives at `courses/<name>/`:

- `index.ipynb`: the learner-facing course home and README.
- `00-overview.ipynb`: an optional whole-course technical overview.
- `NN-topic.ipynb`: one notebook per chapter, with a zero-padded prefix.
- `img/`: figures referenced by notebooks.

The sidebar registration lives in `_quarto.yml` under `website.sidebar`.
Rendering never executes notebook code because `execute.enabled: false`; the
site uses the outputs last stored by `wt run`.

The existing `courses/cla` and `courses/ml-platform` courses remain concrete
examples of course structure and phased sidebar organization.

## Scaffolding

1. Run `wt new course <name> "<Title>"` to create the course home and first
   chapter stub.
2. If the course needs a whole-system orientation before Chapter 01, run
   `wt new chapter <course> 00-overview --title "<Overview title>"`, then move
   its sidebar entry before Chapter 01 in `_quarto.yml`.
3. Run
   `wt new chapter <course> <name> --title "<Full title>" [--section "<Name>"]`
   for later chapters.
4. Run `wt new section <course> <name>` to add a sidebar grouping header.

After scaffolding a chapter, set its final sidebar label explicitly. The
notebook frontmatter title and sidebar text are independent surfaces; the
scaffold initially derives placeholder text from the filename.

## Sidebar naming

- Use `NN. <short label>` for numbered chapter entries and `00. <short label>`
  for an overview.
- Keep the sidebar label shorter than the notebook's frontmatter title. Put
  qualifiers, subtitles, and hedging in the notebook title instead.
- When a course has `00-overview.ipynb`, keep the course home and overview in
  one unnamed section rooted at `index.ipynb`. The home is the section target,
  and the overview is its only child:

  ```yaml
  - section: ''
    href: courses/<name>/index.ipynb
    contents:
      - text: "00. Overview"
        href: courses/<name>/00-overview.ipynb
  ```

  Do not render the course home and `00-overview.ipynb` as sibling `text`
  entries, and do not use a project-specific title such as `ProofLM overview`
  for the numbered overview label.
- Group chapters under thematic or phase-based section headers when the course
  has a natural grouping. A section's `href` points to its first chapter.
- Keep every `href` unique and resolve it to a real notebook.
- Place `00-overview.ipynb` directly after the course home and before the first
  numbered section.

## Structural verification

- Confirm every sidebar `href` resolves to a real file.
- Confirm sidebar labels are shorter than frontmatter titles.
- Render the affected pages so `_quarto.yml`, frontmatter, and navigation are
  parsed together.
