# Course structure and navigation

A course contract lives in `content/data/courses/<slug>.yaml`; authored home,
overview, and chapters live in `content/notebooks/courses/<slug>/`. Supporting
assets live under `content/assets/` or preserved notebook-relative sidecars.
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
3. `wt start course/<slug>` creates the editable draft home from that contract.
4. `wt new section <slug> "<Section>"` adds an ordered section.
5. Create chapters with title/TOC-title/section and planned content/lab (partial plans can be saved; both are required to start):

   ```sh
   .venv/bin/wt new chapter example 01-introduction --title "Introduction" \
     --toc-title "01. Introduction" --section main \
     --planned-content "Explain the topic." --planned-lab-and-evidence "Check the result."
   ```

6. For longer plans use `--plan-file .tmp/<name>.md` with “Planned content” and
   “Planned lab and evidence” H2s. Creation saves the plan/catalog/TOC without a
   notebook. `wt start <chapter-id>` materializes its H1 and plan as a draft.
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

`wt publish` requires authored content and public visibility; publish the parent
course before chapters. Public planned placeholders can appear before authored
publication. Production excludes private/draft entries; withdrawing a parent
suppresses children without changing their states or sources. Preview shows all
valid states. Validate with `wt validate`, then render/inspect affected pages.
