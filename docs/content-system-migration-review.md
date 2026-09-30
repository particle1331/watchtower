# Content-system migration review

The migration service prepares repository-relative candidate files in memory. It
never changes a legacy notebook, deletes a source, executes code, restores an
archived project, or infers completed work. Applying candidates is a separate
validated repository transaction after review; the legacy originals remain
available for comparison until the pipeline switch is checked.

## Inputs and candidate structure

`Migration(root).inventory()` returns a JSON-compatible report. `prepare()`
returns `files`, a mapping from repository-relative destination to UTF-8/source
bytes, and `report`. The report includes artifacts, notebook source/destination
paths and hashes, extracted headers, course TOCs, photo references, retained
gallery prose, profile field names, presentation exceptions, warnings, blockers,
candidate paths, and a `ready` flag. A blocker prevents migration completion;
candidate bytes are available for review even when the report is not ready.

| Legacy input | Candidate | Preservation rule |
| --- | --- | --- |
| `knowledge/catalog.yaml` | `content/data/catalog.yaml` | Preserve stable IDs, title decisions, visibility, lifecycle, and relations; assign `route` to preserve legacy HTML locations. |
| `nb/posts/*.ipynb` | `content/notebooks/posts/*.ipynb` | Extract first-cell document YAML; preserve authored cells and all stored results. |
| `nb/courses/<slug>/course.yaml` | `content/data/courses/<slug>.yaml` | Preserve purpose/audience, planning summaries, optional fields, and actualized facts exactly. |
| `knowledge/sidebar.yaml` | Course `toc`, chapter `section`/`toc_title` | Preserve authored section/chapter order and labels; resolve paths to stable IDs. |
| Course homes and chapters | `content/notebooks/courses/<slug>/` | Preserve real H1s; add agreed missing chapter H1s only when catalog/header titles agree. |
| Active portfolio QMD | `content/notebooks/portfolio/*.ipynb` | Use the Jupytext Quarto parser; preserve the active body, without substituting archive prose. |
| Portfolio catalog summaries | `content/data/portfolio.yaml` | Move `summary` to `abstract`; retain authored entry order. |
| `assets/resume.yaml` | `content/data/profile.yaml` | Add schema version; preserve every existing résumé/home/contact field and value. |
| `nb/photos/photos.ipynb` | Review-dependent gallery/personal records | Extract ordered images, report missing captions and prose, and require an explicit preservation choice. |

`route` is the implemented equivalent of the design document's proposed
`render_path`; routes refer to generated Quarto source locations, preserving
their `.html` output paths. Portfolio `.qmd` inputs become generated `.ipynb`
inputs at the same basename, so their public HTML URLs remain unchanged.
Front-matter `image` becomes the typed catalog's `cover`; unsupported/overlapping
document fields remain visible in the review report rather than disappearing.

The supported normalization operation parses with nbformat through the notebook
helper. It removes only recognized document YAML at the start of the first
Markdown cell. Markdown horizontal rules and code-cell options remain authored
content. Empty header cells remain in place with their original IDs. A missing
chapter H1 uses that empty cell when possible; otherwise a new deterministic-ID
title cell is prepended. Existing cells, metadata, attachments, execution counts,
outputs, labels, and folding/visibility options survive unchanged. Markdown
heading parsing ignores fenced code, code cells, and output text, and recognizes
Setext headings. Conflicting metadata titles and multiple/mismatched chapter H1s
are blockers.

QMD conversion upgrades the notebook format minor version to at least 5 when
assigning cell IDs so the resulting notebook validates. Existing sibling images
and authored include files are copied alongside the migrated notebooks at their
matching relative paths; generated course-context includes are regenerated.
The existing LLMS course cover therefore resolves to
`content/notebooks/courses/llms-from-scratch/img/course-cover.svg`. This deliberate
placement preserves authored image/include references and remains visible in
the asset inventory; future authored portfolio figures use `content/assets/`.

## Initial inventory and review decisions

The initial legacy inventory has 37 notebook/QMD sources and nine review
blockers: the post's overlapping titles, three missing portfolio figure/caption
pairs, and gallery prose plus two remote placeholder images without captions.
Course chapter full titles agree between the catalog and notebook headers, so
their missing H1s can be supplied without renaming teaching content.

The user approved the three existing archived diagrams and their original
captions. `reviewed_portfolio_figures=True` copies the SVG bytes to
`content/assets/portfolio/` and extracts captions directly from the archived
portfolio layout notebook. This approval concerns assets/captions only; active
portfolio QMD prose and current historical abstracts remain the sources of the
writeups. The detail records use `project_source: archived`,
`archive_date: '2026-09-30'`, and the exact approved project-folder names:
`autocode`, `change-planner`, and `ml-platform`. Their code remains under
`archive/2026-09-30/projects/`; no active project records are created.

The user also approved preserving the gallery prose as personal writing and
leaving a new gallery planned and empty until real photographs are available.
`preserve_gallery_as_personal=True` retains every body cell, including remote
placeholder references, at `content/notebooks/personal/photos-notes.ipynb`.
Following the user's clarification that Personal should contain only photo rows,
`personal/photos-notes` is private/published, with the separate route
`nb/personal/photos-notes.html`. The public/planned `gallery/photos` owns the
original `nb/photos/photos.html` route and an empty `content/data/photos.yaml`
collection. Both the CMS Personal screen and reader Personal page use ordered
photo rows; the preserved writing is excluded from production.

The post catalog title is “Watchtower CLI and Tests”; its notebook header says
“Understanding the repo CLI `wt`”. The user approved the notebook title. The
migration reports both. A caller supplies
the approved full title in `title_choices` keyed by stable artifact ID; only an
exact choice of one of those existing titles resolves the conflict. No title is
chosen silently.

## Frontend presentation review

The initial document-level exceptions are `toc: true` on the post and
`page-layout: article` on the three portfolio writeups. These belong to frontend
templates/defaults, with their original values retained in the inventory for
review. They are not added as arbitrary entity-level Quarto option mappings.
Per-cell `#|` directives remain in the source notebooks. The profile remains the
canonical source of shared author identity rather than duplicating an `author`
mapping into notebook records.

Before retiring any originals, validate the complete candidate snapshot and
render representative posts, course home/overview/chapter pages, all three
portfolio entries, the personal page/planned gallery, and résumé outputs. Check
legacy routes, source-image references, output/attachment preservation, chapter
title presentation, desktop/mobile portfolio navigation, and exclusion rules.

## Completed local verification

The reviewed migration is installed. Original notebooks, metadata, frontend
assets, and handwritten Quarto inputs are preserved verbatim under
`archive/2026-10-01/content-system-inputs/`. Historical project code remains in
its separate `archive/2026-09-30/` location.

The complete automated suite passes, including a real kernel execution with
`watchtower.core`, stored figure output, preview generation, and production
publication selection. Ruff and Pyright pass. The migrated production build
renders all eligible source pages plus the résumé PDF; previous render checks
found no broken local references, duplicate chapter titles, or private/draft
content in production. Snapshot generation leaves authored notebook bytes
unchanged and reproduces identical generated inputs.

The black, gray, and violet motif is confined to CMS static files. The reader
keeps its United theme and existing palette. CMS files are excluded from public
staging. Browser verification was interrupted by user activity in Brave; no
further interaction was attempted with the user's open form. CI is configured
for the new generator; no external deployment was performed during this work.

Photos now have individual headings and draft/published lifecycle fields. CMS
Personal manages those fields per row and has no Gallery lifecycle control.
Published rows render as H2 sections; draft rows and their image assets are
excluded from both reader preview and production. A real Quarto render checks
this behavior alongside the saved-output notebook workflow.
