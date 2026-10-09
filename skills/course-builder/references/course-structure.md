# Course structure and navigation

A course contract lives in `backend/data/courses/<slug>.yaml`; authored home,
overview, and chapters live in `content/notebooks/courses/<slug>/`. Supporting
authored assets live beside notebooks as relative sidecars. CMS-managed card
images live under `backend/assets/`; use the CMS/CLI/API for managed records and
uploads.
The contract owns purpose/audience, separate planned/actualized accounts, and
ordered `toc` sections `{id, title, chapters: [stable chapter IDs]}`. The catalog
chapter owns `parent`, `section`, full `title`, and short `toc_title`. Do not edit
generated `_quarto.yml` or maintain a second sidebar source.

Use an isolated Git worktree for new courses/multi-file revisions when possible.
Preserve dirty primary changes. Preview it with `make preview PORT=4300` and report
the exact URL. A separate port alone does not isolate source/build files.

## Scaffolding

1. `.venv/bin/wt new course <slug> "<Title>"` registers its planned home and contract.
2. Set purpose/audience/planned prose through `wt data course/<slug>` or the CMS.
3. `wt start course/<slug>` creates a private draft home seeded from supported contract fields; internal notes remain separate.
4. `wt new section <slug> "<Section>"` adds an ordered section.
5. Create chapters with title/TOC-title/section and planned content/lab (both are optional; partial plans can be saved and started):

   ```sh
   .venv/bin/wt new chapter example 01-introduction --title "Introduction" \
     --toc-title "01. Introduction" --section main \
     --planned-content "Explain the topic." --planned-lab-and-evidence "Check the result."
   ```

6. For longer plans use `--plan-file .tmp/<name>.md` with “Planned content” and
   “Planned lab and evidence” H2s. Creation saves the plan/catalog/TOC without a
   notebook. `wt start <chapter-id>` creates a private draft with its full-title H1 and sections from content, lab and references. Read the saved build brief, then develop the seeded body cells. Internal notes and next steps stay separate; later plan edits do not change the notebook.
7. Optional `00-overview` is a chapter with its own plan; put it first in the
   ordered TOC and set contract `overview` to its stable ID.

Every registered chapter occurs exactly once in its parent's TOC, including
unpublished chapters. Catalog/plan section membership agrees with its containing
section. Moves through `wt update <id> --section <id>` update all representations
atomically. Reorder sections/chapters through contract data/CMS lists. Use
`wt batch` for coordinated metadata/contract repairs. Never infer actualized work.

## Titles and publication

Source chapters contain exactly one full-title H1; generated templates suppress
the duplicate automatic title block. TOC labels use `NN. <short label>` independently.
Explicit `wt update <id> --title ...` changes both metadata and the existing H1.

`wt publish` requires content and makes visibility public; publish the parent
course before chapters. Plans remain private in the CMS and never render on the
frontend. Preview shows started drafts and published pages, including private
ones. Production includes only public published pages. A parent must be eligible
before its children appear, without changing their states or sources. Validate
with `wt validate`, then render/inspect affected pages.
