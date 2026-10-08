# Watchtower

A notebook publishing workspace with a local FastAPI/Jinja/HTMX CMS, a
revision-aware CLI, and a generated Quarto website. The CMS uses
black, gray, and blue; the public website retains its existing styling.

## Sources of truth

| Location | Contents |
| --- | --- |
| `content/data/catalog.yaml` | Stable IDs, metadata, publication states, relationships, and legacy routes. |
| `content/data/courses/<slug>.yaml` | Purpose/audience, planned intent, explicit actualized facts, ordered section/chapter TOCs. |
| `content/data/portfolio.yaml` | Ordered abstracts, figures/captions, accompanying notebooks, active/archived code references. |
| `content/data/profile.yaml` | All homepage, résumé, and contact facts. |
| `content/data/photos.yaml` | Ordered photo headings, paths, captions, and individual draft/published states. Personal displays only photo rows. |
| `content/notebooks/`, `content/assets/` | Authored notebook bodies, stored outputs, attachments, cell options, and supporting assets. |
| `frontend/templates/`, `frontend/assets/`, `frontend/site.yaml` | CMS/site templates, public theme assets, repository settings, presentation defaults. |
| `backend/runtime/`, `frontend/generated/` | Ignored transaction journals, build records/logs, render snapshots, successful outputs. |

Executable projects stay under `projects/`. Historical implementations remain in
`archive/2026-09-30/projects/`; portfolio references do not restore/register
historical code as active work. The [migration review](docs/content-system-migration-review.md)
records preservation rules and approved assets/titles. Retired inputs are under
`archive/2026-10-01/content-system-inputs/`. The former gallery prose is retained
privately; the structured gallery stays planned until real photos are supplied.

## Everyday authoring

Run `make bootstrap`, then use `.venv/bin/wt` from the repository root. CLI,
CMS, and JSON API call the same file-backed services. Manual YAML edits
remain supported and are verified before rendering. Document front matter is
injected into generated copies only; notebook bodies remain editable in VS Code
or JupyterLab. Quarto renders saved outputs without executing cells.

```sh
.venv/bin/wt new post example --title "Example" --planned-content "Investigate a question." --tag experiments
.venv/bin/wt start post/example
# Edit notebook body, then explicitly execute its cells.
.venv/bin/wt run post/example
make preview PORT=4300
.venv/bin/wt publish post/example
```

Longer plans use `--plan-file .tmp/<name>.md`. Posts accept arbitrary Markdown.
Chapter files require exactly one nonempty “Planned content” section and
“Planned lab and evidence” section. Portfolio files contain introductory prose,
“What it contains,” and optional scope notes under “Explore the project.”
Plans are persisted, so temporary files can be removed afterward.

```sh
.venv/bin/wt new course example "Example Course"
.venv/bin/wt new chapter example 01-introduction --title "Introduction" \
  --toc-title "01. Introduction" --section main \
  --planned-content "Explain the topic." --planned-lab-and-evidence "Check a reproducible example."
.venv/bin/wt start course/example/01-introduction
.venv/bin/wt new portfolio example --project-path projects/example --plan-file .tmp/example.md \
  --abstract "Project purpose" --figure-path content/assets/portfolio/example.svg --figure-caption "System diagram"
```

Creation registers private plans in YAML without creating notebooks. Plans appear
only in the CMS, never in preview or production. `start` creates a private draft
notebook with editable sections seeded from the saved plan and refuses existing
files. Posts receive their outline, audience, takeaway and evidence; portfolios
receive the problem, contents, approach, evaluation criteria and references;
courses receive
purpose, audience, progression, prerequisites, outcomes and practice. Chapters
receive content and labs. Empty plans create title-only drafts. Generated pages
show the catalog title once: a notebook H1 that repeats the title is dropped from
the build, while chapters keep their authored H1 as the page title. Portfolio plans
show an optional **Abstract** field under the optional planning details. Start
fills a blank abstract with a short
excerpt from the introduction and contents; existing abstracts or legacy public
descriptions take precedence. Review and edit this draft abstract before publishing.

Seeding never rewrites hand-edited cells. Internal notes, next steps, unknown
fields and portfolio scope
notes stay in the CMS. Plan saves refresh the seeded sections while the draft
still matches its last seed; the first hand edit freezes the notebook, and
hand-edited content is never rewritten. Review seeded prose before publishing; no AI generation is
involved. Course chapter tables remain generated from the ordered TOC.

Preview shows started drafts and published notebooks, including private content.
Production selects only public published pages. A course must itself be eligible
before any child pages, links or assets appear. Personal retains its separate
per-photo workflow. Imports with authored content default to draft. Chapters
require one full-title H1; `toc_title` controls navigation.

`publish` requires content and sets visibility to public atomically; chapters
also require a public published parent. `draft` preserves the body/visibility while returning published content
to draft. Neither commits nor pushes. Once changes reach `main`, GitHub Actions
builds committed inputs and publishes successful output to the existing
`gh-pages` target. Failed builds retain the previous successful site.

## Commands and interfaces

| Command | Result |
| --- | --- |
| `wt map`, `ls`, `find`, `context` | Catalog-backed discovery and course reading paths. |
| `wt plan <stable-id>` | Read saved planning fields, internal notes, CMS build brief and workspace revision as JSON, at any lifecycle. Requires an exact stable ID. |
| `wt new post\|course\|chapter\|portfolio`, `new section` | Planned records and ordered course TOCs. |
| `wt start`, `publish`, `draft` | Explicit notebook/publication transitions; active portfolio start also scaffolds/registers its project. |
| `wt delete <id>` | Remove an entry, retaining its files. `--dry-run` reviews affected entries/links; `--cascade` explicitly includes course chapters. |
| `wt update <id>` | Metadata/tags/plans/internal notes (`--internal-notes`); `--planned-content` updates a post outline, chapter content, or course summary. Chapters also accept `--planned-lab-and-evidence`; `--patch-file` supports variant fields and relations. |
| `wt data <name> [--file <yaml>]` | Profile, portfolio, photos, kanban, settings, or `course/<slug>`. |
| `wt kanban ls [--column <column>] [--query <text>]` | List task cards with permanent `card#N` references, validated artifact links, frontend/VS Code URLs, and revision. |
| `wt kanban add --title <title> [--column <column>] [--link <stable-id>]` | Add a card with an automatically assigned ID and `card#N` reference; repeat `--link` for multiple artifacts. |
| `wt kanban update <card-id> [--title ...] [--description ...] [--link ...] [--clear-links]` | Edit a card; links are replaced when supplied. |
| `wt kanban move <card-id> <column>` / `wt kanban rm <card-id>` | Move or remove a task without changing linked artifacts. |
| `wt gallery --file <yaml>` | Save ordered photos and each photo’s lifecycle atomically. |
| `wt batch --file <json>` | Related metadata/data repairs in one validated transaction. |
| `wt import <file> posts\|personal [name]` | Supported normalization preserving outputs. |
| `wt import <file> courses <course> [chapter]` | Import an authored chapter into its course TOC. |
| `wt register <kind> <path> <title>` | Register existing work with an ID derived from its source path; chapters require `--parent <course-id>`. `make project NAME=<slug>` scaffolds code. |
| `wt validate` | Schemas, references, lifecycle/content agreement, H1s, TOCs, images, registration. |
| `wt cat`, `edit-cell`, `append-cell`, `insert-cell`, `remove-cell`, `tag` | Supported notebook operations; `cat --with-revision` exposes a notebook token for guarded writes. Never edit raw JSON. |
| `wt run`, `output`, `diff` | Explicit execution, saved-output inspection, source review. Moved sources use `diff --base-source <old-path>`. |
| `wt map\|ls\|find --archive` | Deliberate historical-source discovery. |
| `wt migrate` | Dry-run inventory; `--apply` requires resolved review decisions. |
| `make preview PORT=4300` | Watch saved files and serve successful working output. |
| `make build` | Production output at `frontend/generated/production/_site/`. |
| `make cms` | CMS at `http://127.0.0.1:8000/cms/`; API/OpenAPI at `/api/` and `/docs`. |
| `make resume`, `make render NOTEBOOK=<id-or-path>` | Generate résumé/notebook PDFs outside authored content. |
| `make knowledge`, `wt sync-site`, `wt render-context` | Compatible regeneration of disposable Quarto projections. |
| `make lint`, `make typecheck`, `make test` | Tooling and publishing/recovery acceptance checks. |

All `wt` examples use `.venv/bin/wt` from the repository root. Agents use the CLI;
Watchtower has no MCP server. Start with `.venv/bin/wt map`, then use
`.venv/bin/wt --help` or `.venv/bin/wt <command> --help` to discover commands and
arguments. `wt context <id>` reads artifact metadata;
`wt data <name>`, `wt gallery`, and `wt kanban ls` read structured records,
photos, and tasks with the workspace revision. Pass it with `--expected-revision` on
supported mutations. Larger payloads can use `.tmp/` files through
`update --patch-file`, `data --file`, or `batch --file`.

`cat --context N` shows adjacent cells,
not sibling chapters. Read course context, home, optional overview, and target
chapter in that order. Record actualized learning from checked evidence only.

When editing a notebook shared with another agent, read with `cat --with-revision`
and pass the printed `notebook:<hash>` token as `--expected-revision` to
`edit-cell`, `append-cell`, `insert-cell`, `remove-cell`, `tag`, `clear-outputs`,
or `run`. The token covers the whole notebook, including outputs and metadata;
an insertion, deletion or intervening save makes it stale. Re-read before deciding
how to resolve a conflict. Other files changing do not invalidate this token.
Omitting the option retains ordinary single-agent editing behavior.

Plan updates route to the effective record: chapter `plan`, course
`contract.planned.summary`, portfolio `detail.planned`, or post/personal
`planned.content`. Chapter plan files use the same two sections as creation;
portfolio files use introduction, “What it contains,” and optional “Explore the
project.” Updating a portfolio with `--planned-content` is rejected; use its
plan file or a detail patch. Existing planning fields and actualized facts are
preserved.

`batch --file .tmp/batch.json` accepts a JSON object with `updates` and/or `data`:

```json
{
  "updates": [{"id": "post/example", "patch": {"description": "Revised description"}}],
  "data": {}
}
```

The positional `batch .tmp/batch.json` form is also supported. Supply one form.

The CMS edits structured fields/plans. “Edit in VS Code” opens the canonical
notebook; “Start draft” first materializes it through the lifecycle service.
Notebook lifecycle choices follow the canonical source: Planned before a notebook
exists, Draft for a started scaffold, then Published when authored content is ready.
Legacy empty scaffolds can be repaired as Planned or Draft. Authored notebooks
cannot be returned to Planned. Metadata, plans and notes remain editable throughout.

CMS creation and editing use guided Markdown briefs for posts, portfolio entries,
courses and chapters. New CMS plans are private by default: **Not on the live
site**. Save an incomplete idea and return to it later. **Copy build brief**
exports the saved planning fields, internal notes and context as Markdown, with
selectable text as a clipboard fallback. **Start draft** creates a private notebook seeded from supported plan fields;
partial plans can be started across CMS, CLI and API. Review the draft before publishing.

New posts, personal notebooks, portfolio entries, courses and chapters default
**Date** to the creation day in the site's configured timezone (Asia/Manila by
default). Explicit dates are preserved; later saves keep the chosen date.

**Internal notes** are a persistent Markdown field alongside the structured brief.
Use the CMS, `wt update <id> --internal-notes "..."`, a patch file containing
`internal_notes`, or an API artifact patch. Notes remain available after publication;
editing them or the plan never rewrites the notebook or changes its lifecycle.
Kanban cards linked to artifacts coordinate work independently of publication.

Read the saved authoring plan directly by stable ID:

```sh
.venv/bin/wt plan post/example
.venv/bin/wt plan course/example/01-introduction
```

The JSON response includes `id`, `kind`, `title`, `lifecycle`, `source_path`,
structured `plan`, `internal_notes`, `build_brief`, and workspace `revision`.
The plan comes from the artifact's saved planning record, including course
contracts, chapter plans, and portfolio details. The build brief matches the CMS;
course briefs include chapters in TOC order and chapter briefs include course
context. Partial plans and published artifacts are readable without creating,
executing, or changing notebooks. Titles and source paths are not accepted as IDs.

Plans are never rendered directly. Started notebooks own their seeded content;
internal notes remain excluded from preview, production, metadata and course
context. Use **Public description** for listings, portfolio abstracts for cards,
and chapter short summaries for the generated course table.
Explicit actualized facts may still render in course context. Existing authored
notebooks and planning text are preserved. Internal notes are still stored in the
repository, so a public repository does not make them confidential.

Course workspaces at `/cms/courses/<slug>` provide the brief, ordered sections,
and contextual chapter creation. Rename and reorder sections, reorder chapters,
or move them to another section of the same course. Remove only empty sections,
keeping at least one; chapter deletion uses the existing review. These changes
keep the catalog, contract TOC and plans synchronized. The advanced contract
editor remains available. Course homes automatically generate a **Section /
Chapter title / Summary** table from the TOC and each chapter's short summary.
Saving changes updates the table on the next preview/build without editing the
course notebook. Production retains the existing visibility/lifecycle filtering.

Related-content controls throughout the CMS search titles and stable IDs while
typing. Suggestions show title, kind, ID and lifecycle; select a result to link it,
and remove selections to unlink. Multiple selections preserve order without
duplicates. Keyboard selection uses arrows/Enter, and Escape dismisses results.
Native select controls work without JavaScript. The read-only `/cms/lookup`
endpoint supports `q`, `kind` and `parent`; saves still validate registered IDs.
Course API patches accept `contract` alongside metadata for an atomic brief save.
Legacy course planning text is offered for recovery when the contract summary is
empty, and only persisted on an explicit save. Existing unknown planning fields
and actualized facts are preserved.
Portfolio editors accept a featured image (PNG, JPEG, WebP, or GIF, up to 20 MB)
and figure caption. Saving stores the image under `content/assets/portfolio/`
with the metadata in one transaction. Portfolio cards show it below the abstract;
entry pages show the same abstract, featured figure and source link above the
notebook content. The CMS shows one **Project path** field (`projects/<name>`,
or `archive/<date>/projects/<name>` for migrated historical entries); it
defaults to `projects/<name>` after the portfolio name, and
`wt data portfolio` repairs it.
planned and draft project cards and pages show a yellow diagnostic panel with monospace publication metadata.
Planned entries include the setup command with the actual stable ID in `wt start <id>`.
Course editors accept a card image in the same formats and size limit, stored
under `content/assets/courses/` through the catalog's `cover` field. It appears
in the Courses card grid. Personal photo editors support uploading new photos
and replacing existing ones under `content/assets/photos/`. Images and metadata
save in one transaction; leaving an upload empty keeps the saved image.
Starting an active portfolio creates its notebook and the `projects/<name>` code
directory behind its project path
with the same package scaffold as `make project NAME=<name>`, and registers both
in one recoverable save. The path defaults to `projects/<name>` from
the final segment of the stable ID. Existing project code is reused untouched.
Drafts may start before the abstract and featured figure are complete;
publication still requires the abstract, image, and caption.
Portfolio scope notes and research references stay in the internal brief; author
reader-facing sections in the notebook. Planned pages use the public description
or abstract and include the reserved active code URL before the directory exists;
draft/published entries require the code directory, and archived references must
always resolve to existing archived code.
The global refresh builds saved inputs and reports progress/errors without
executing cells or changing publication. Notebook bodies remain in the editor.

## Revisions and recovery

Read responses expose SHA-256 revisions over exact workspace input bytes.
API writes require `If-Match` (428 missing, 412 stale); CMS forms carry that token.
CLI writes accept `--expected-revision` and capture one when omitted. Stale
operations are never automatically retried. Managed clients share a workspace
lock and durable transaction journals. Recovery rolls forward from matching
preimages/absence and blocks on external changes, retaining all versions.
Conflicted journals prevent builds from replacing successful output.

Notebook execution captures the source under the workspace lock, releases that
lock while the kernel runs, then checks the source again before saving. Other
agents can inspect and update Kanban during execution. If the notebook was
changed or deleted, execution exits with a conflict and retains its results under
`.tmp/execution-conflicts/`; it does not overwrite the newer source. The error
reports the retained file for review.

An IDE can save between a final hash check and replacement: detection of
uncoordinated saves remains best effort. Pause affected saves during managed
changes when strict coordination is required. Keep scratch work in `.tmp/` and
secrets in the OS keyring through `wt vault`. Shared skills live in `skills/`;
`make setup-skills` maintains links. Archived code is excluded from active checks.

Each photo has a required heading, caption, and `lifecycle: draft|published`.
Draft photos may omit the path and show a "No Photo" placeholder in the CMS and
working preview. Published photos require a safe path to an existing image.
An optional `width: "80%"` sets image width relative to the content column;
accept percentages above 0 and up to 100%, or leave blank for the default size.
The CMS exposes width for existing photos and new rows.
Published photos render as individual H2 sections in Personal. Working previews
also show draft photos with the same yellow publication panel used by Portfolio,
including image readiness and the next CMS action; production
excludes draft photos and their assets. The gallery has no document-level status
callout. Captions appear after images. Personal renders once from
`frontend/templates/site/personal.qmd.j2`, without a generated gallery notebook or duplicate page.
All draft pages and photos use the shared
yellow publication-status panel with instructions, visible only in working previews. Draft course cards, course sidebar
links, and post listings show matching yellow `draft` badges. Production excludes
draft pages, links, cards, and assets.
The gallery page state is derived automatically; there is no collection-level
publication control in the CMS.

The CMS uses the available width. Artifact editors and plan creation separate
**Site content**, **Build plan**, and **Internal notes** into keyboard-accessible
areas. Switching areas retains every control, unsaved value and upload in the
same form. Without JavaScript the areas remain visible as sections. Internal
notes, next steps and scope notes are marked CMS-only; build-plan guidance
explains draft seeding. Course workspaces open on the compact outline: chapter
rows show status, reorder arrows and Edit; expanding a row reveals its summary,
section transfer and deletion link. Section settings and secondary authoring
tools start folded. Outline actions save immediately with the current revision.
Artifact and plan-creation Settings fields stay visible.
Short information and row actions stay visible.
Employment, early employment, skill and education entries start folded regardless
of length, in both résumé views and editors.
Résumé editor groups follow the frontend order, beginning with General and Contact.
Home and Résumé show saved GitHub and LinkedIn links.
Profile editing opens ready to edit on the originating Home or Résumé section,
with the same category and record field order. Save and Cancel return to that
section's overview; a Back link remains available while editing.
Posts support full or partial title search. Collections use pagination and
scrollable lists. Editor pagination
keeps every field in the form so page changes retain edits and selected uploads.
Personal's **Add photo** action opens a standalone composer with Heading, Photo,
Caption, Lifecycle, and Width. Saving adds only that photo and returns to Personal;
existing photos retain their individual Edit links.

Kanban is the final author tab. Its columns are **To do**, **In progress**, **Review**,
and **Done** (CLI values `todo`, `in-progress`, `review`, `done`). Cards persist in
`content/data/kanban.yaml`; an absent file represents an empty board. Cards have
permanent human references (`card#1`, `card#2`, …) alongside immutable internal
IDs. References are shown in the CMS and `wt kanban ls`, can be copied from the
board, and work with `update`, `move`, and `rm`. Numbers are never reused after
removal. Linked `artifact_ids` must exist in the active catalog. The board
is author-only, excluded from generated public pages, and task-only saves do not
trigger automatic site rebuilds. Frontend links open
the working preview; VS Code links appear when the canonical source exists,
including project directories and gallery data. Planned notebooks expose the
CMS link only until started; preview and VS Code links appear once eligible.

All Kanban CLI writes accept `--expected-revision`. Read `wt kanban ls` first and
pass its `board_revision` (`kanban:<hash>`) for task coordination; this checks
the saved board without rejecting unrelated content edits. The existing
workspace `revision` remains accepted when the task decision also depends on
the content snapshot. Card mutations return both tokens. Any intervening change
to the board invalidates the board token, and conflicts are never retried automatically.
`ls --query` searches card IDs and `card#N` references as well as title,
description and artifact IDs. HTTP uses `GET/POST /api/kanban` and
`PATCH/DELETE /api/kanban/<card-id>` with `If-Match` required for writes. CMS,
CLI, and HTTP share the same validation, lock, recovery and conflict handling.
Kanban HTTP card writes also accept the scoped board token in `If-Match`;
ordinary CMS forms continue to carry workspace revisions.

Whole-board `data kanban` and batch saves retain the highest assigned card
number and preserve existing card identities, including when refs are omitted
from submitted rows. Reassigning a saved reference or attaching a reserved
reference to another ID is rejected. Explicit malformed-board repair remains
available; supply the known numbering counter and identities in the repair.
Individual card edits reject combining `--link` with `--clear-links`.

Entity deletion is available from the CMS listing and entity editor. The review
screen lists all affected entries and managed links; course removal requires
explicitly including its chapters. `wt delete <id> --dry-run` returns the same
review and revision. Use `wt delete <id> --expected-revision <revision>` to apply
it, adding `--cascade` for a course with chapters. HTTP exposes
`GET /api/deletions/<id>` and `DELETE /api/artifacts/<id>?cascade=true`, with
`If-Match` required for deletion.

Deletion retains files. Authored notebooks and the removed course contract move
byte-for-byte to `archive/deleted/<operation-id>/` so active notebooks remain
registered. `record.json` preserves the removed registrations and prior affected
structured records. Images and project code stay in place. Portfolio deletion
keeps its executable project registered; deleting that project registration also
retains its directory. Incoming catalog relations, Kanban links and résumé
artifact links are detached, while their containing records remain. Chapter
removal updates its parent TOC, plan and overview. Photos, résumé rows and Kanban
cards use their existing row-removal controls; the built-in gallery stays.

CMS creation asks for a **Name** and generates the stable ID and source path.
For example, `test` becomes `portfolio/test`; post name `gliner` becomes
`post/gliner` and source `content/notebooks/posts/gliner.ipynb`. Courses,
chapters, projects and personal notebooks follow their corresponding source
folders, and chapters let you choose a course and section by title. Names accept
letters, numbers, hyphens and underscores; spaces and punctuation become hyphens.
The generated ID must be unique. Active names and
names of deleted entries remain unavailable, including case variants and older
posts with a different ID but the same filename. Catalog `retired_ids` and
`retired_sources` persist these reservations atomically with deletion. They are
not cleared by removing archival files. CLI/API creation obeys the same
retired-name rules.

All catalog entities use **tags** as their single taxonomy. The frontend maps tags
to Quarto `categories` in generated document metadata and uses native Quarto
category filtering in the Posts listing. Legacy notebook
front matter may still contain `categories`; imports merge those values into tags
and discard the old field, deduplicating without regard to case. CMS editors have
no separate category or editable route field;
legacy routes remain managed site metadata. Only courses expose the catalog image
as **Card image**; posts have no Cover control. Portfolio figures and photo uploads
use their dedicated controls.

The CMS folds every résumé employment, early employment, skill and education
entry, along with course chapter lists and expanded project content.
Contact information, post row actions and basic editor
groups stay visible. Personal lists 120×120 thumbnails with direct **Edit photo**
links; each link opens only that photo with editing already enabled. Personal has
no page-wide Edit photos action. **Reorder photos** below the photo list opens
the compact photo list with per-photo up and down controls. Portfolio row **Edit**
links open the combined metadata, abstract, image and plan editor with editing
already enabled. Save and Cancel return to Portfolio; no second editor is needed.
Artifact editors keep Publish (or Return to draft), Delete, Cancel and Save in
the same toolbar. Planned entries offer Start draft there once their core brief is complete. Publication
uses the saved revision. In draft post, portfolio, course and chapter editors,
**Publish** saves pending fields and any image and publishes in one atomic
operation; no separate Save and publish button is needed. Other lifecycle actions
stay disabled while metadata has unsaved changes. Portfolio
returns to its overview, courses and chapters to their course workspace, and
posts remain in their editor. Chapters require a public published parent;
publishing a course does not publish its chapters.
Validation failures or stale revisions save neither the edits nor publication;
submitted values remain in the editor for correction.
Publish stays clickable for incomplete drafts and reports missing requirements
when attempted. It is disabled while a save is in progress.
Photo width fields show
`100%` as the blank/default hint. Kanban cards show links and actions directly;
Add, Edit and Remove open accessible native dialogs with keyboard dismissal,
focus restoration and unsaved-change protection. Their links also provide a
server-rendered form when JavaScript is unavailable.
