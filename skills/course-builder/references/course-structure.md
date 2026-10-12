# Course structure and navigation

A course contract and committed CMS home live in `backend/data/courses/<slug>.yaml`; authored
overview and chapters live in `content/notebooks/courses/<slug>/`. Supporting
authored assets live beside notebooks as relative sidecars. CMS-managed card
images live under `backend/assets/`; use the CMS/CLI/API for managed records and
uploads.
While Planned, the contract owns the writing brief. After Start, the CMS home fields own the course home and notebooks own chapter teaching. The contract retains ordered `toc` sections `{id, title, chapters: [stable chapter IDs]}`. The catalog
chapter owns `parent`, `section`, full `title`, and short `toc_title`. Do not edit
generated `_quarto.yml` or maintain a second sidebar source.

## CMS course workspace

`/cms/courses/<slug>` opens on the ordered outline. Planned courses offer Course plan; started courses offer Course home. Artifact forms use Basics,
Plan (while Planned), and Page: public summaries belong in Page and writing intent in Plan. Internal notes become available in their separate dialog after starting. Only the title is required to create;
partial plans can be saved or started. Creation offers Create and start draft.

Outline actions add, rename, and reorder sections; add and reorder chapters;
and transfer chapters between sections. Chapter disclosures expose the public
table summary, transfer, and deletion controls. Actions save immediately with
their original revision and synchronize catalog membership, contract TOC, and
chapter plans. Save pending brief edits before performing a separate action.
Remove only empty sections and retain at least one.

## Plan and organize through the CLI

1. `wt new course <slug> "<Title>" [--plan-file .tmp/<slug>.md]` registers a
   private Planned course and its contract without a source notebook.
2. Save the course brief with `wt update course/<slug> --plan-file ...`.
   Supported H2 labels are Card description, Purpose, Audience and prerequisites,
   Learning outcomes, Running project, Practice and assessment, and References. Planned internal notes must be empty. Canonical field keys work too; inspect `wt context <stable-id>` for the plan and valid fields.
3. Use the initial `main` section or add sections with
   `wt new section <slug> "<Section>"`.
4. Register chapter plans with full title, short TOC title, section, public
   summary, and an optional writing brief:

   ```sh
   .venv/bin/wt new chapter example 01-introduction --title "Introduction" \
     --toc-title "01. Introduction" --section main \
     --summary "Introduces the topic through a small worked example." \
     --plan-file .tmp/01-introduction.md
   ```

   The chapter plan file uses these sections; Course table summary is also supported. Internal notes are reserved for started drafts:

   ```markdown
   ## Outline
   Explain the topic through a small worked example.

   ## Practice and evidence
   Reproduce the example and explain the result.
   ```

5. An optional `00-overview` has its own chapter plan. Put it first in the
   ordered TOC and set contract `overview` to its stable ID.

Plan files must live under repository `.tmp/`. Creation persists their bodies;
remove temporary payloads only after checking the saved plan. `--plan-file`
updates only sections it contains; an empty section clears that field.
`wt update <id> --summary ...` changes the explicit public sentence. Unknown
or duplicate H2 labels and text before the first heading are rejected.

Every registered chapter occurs exactly once in its parent's TOC, including
unpublished chapters. Catalog/plan section membership agrees with its containing
section. Moves through `wt update <id> --section <id>` update all representations
atomically. Reorder sections/chapters through the CMS or `wt data course/<slug>`.
Read structured data first and carry its workspace revision with
`--expected-revision` when replacing the contract; preserve unrelated fields.
Use `wt batch` for coordinated metadata/contract repairs. Do not automatically
retry stale writes. Consumed writing briefs cannot be changed; preserve historical fields during structured-data saves. Validate plan-only changes
with `wt validate` and inspect the Planned brief through `wt context` and the ordered course context.

## Start and develop notebooks

`wt start <stable-id>` creates a private Draft and consumes its plan. Chapters get notebooks;
courses get CMS home fields without an editable home notebook. `new course` and `new chapter` also support
`--start`. Partial plans can start; empty plans produce title-only drafts.
Courses seed their home description, prerequisite items, learning outcomes and references once from the plan; Requirements can be added separately in the CMS. The running project and assessment become description subsections. Chapters seed the Outline body and Practice and evidence below
their full-title H1. Public summaries and internal notes never seed.

Starting seeds content once and consumes the plan. The CMS home or chapter notebook is then the content authority; plan fields disappear from the CMS and active agent context, and plan writes are rejected. Read current home content with `wt context` and chapter cells with `wt cat`. Keep unfinished draft work in the internal-notes modal’s separate Notes and To-dos fields. Notes are Markdown; `internal_todos` is an ordered array of `{text, done}` objects. Save the checklist through the CMS controls or `wt update --patch-file`, carrying the revision. The completed/total count is derived from the list. Linked Kanban cards execute scoped work and hold temporary context. Read current entity memory through `wt kanban show`; return lasting findings and follow-up work to the notebook or internal notes before marking the task Done. Review and develop the seeded prose before publishing.

## Titles and publication

Source chapters contain exactly one full-title H1; generated templates suppress
the duplicate automatic title block. TOC labels use `NN. <short label>` independently.
Explicit `wt update <id> --title ...` changes both metadata and the existing H1.

`wt publish` requires content and makes visibility public; publish the parent
course before chapters. Planned entries remain CMS-only and never render on the
frontend. Preview shows started drafts and published pages, including private
ones. Production includes only public published pages. A parent must be eligible
before its children appear, without changing their states or sources. Validate
with `wt validate`, then render/inspect affected pages.
