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
.venv/bin/wt new portfolio example --project-name example --plan-file .tmp/example.md \
  --abstract "Project purpose" --figure-path content/assets/portfolio/example.svg --figure-caption "System diagram"
```

Creation registers plans without creating notebooks. `start` creates a draft
from its persisted plan and refuses existing files. Imports with authored
content default to draft. Chapters require one full-title H1; `toc_title` controls
navigation. A chapter title update coordinates metadata and its source heading.

Planned entries have no authored content and render metadata-generated pages.
Draft/published entries require authored content and render copied notebooks.
Title-only scaffolds are empty. Preview shows all valid states, including private
content. Production selects public published pages and public planned placeholders.
A private/draft course suppresses all children while retaining their states;
a planned course shows only planned children. Public Portfolio cards require
published entries. Personal contains photo rows without prose/notebook listings.

`publish` requires public visibility, content, and a public published parent for
chapters. `draft` preserves the body/visibility while returning published content
to draft. Neither commits nor pushes. Once changes reach `main`, GitHub Actions
builds committed inputs and publishes successful output to the existing
`gh-pages` target. Failed builds retain the previous successful site.

## Commands and interfaces

| Command | Result |
| --- | --- |
| `wt map`, `ls`, `find`, `context` | Catalog-backed discovery and course reading paths. |
| `wt new post\|course\|chapter\|portfolio`, `new section` | Planned records and ordered course TOCs. |
| `wt start`, `publish`, `draft` | Explicit notebook/publication transitions; active portfolio start also scaffolds/registers its project. |
| `wt delete <id>` | Remove an entry, retaining its files. `--dry-run` reviews affected entries/links; `--cascade` explicitly includes course chapters. |
| `wt update <id>` | Metadata/tags/plans; `--patch-file` supports variant fields and relations. |
| `wt data <name> [--file <yaml>]` | Profile, portfolio, photos, kanban, settings, or `course/<slug>`. |
| `wt kanban ls [--column <column>] [--query <text>]` | List task cards with permanent `card#N` references, validated artifact links, frontend/VS Code URLs, and revision. |
| `wt kanban add --title <title> [--id <id>] [--column <column>] [--link <stable-id>]` | Add a card; repeat `--link` for multiple artifacts. |
| `wt kanban update <card-id> [--title ...] [--description ...] [--link ...] [--clear-links]` | Edit a card; links are replaced when supplied. |
| `wt kanban move <card-id> <column>` / `wt kanban rm <card-id>` | Move or remove a task without changing linked artifacts. |
| `wt gallery --file <yaml>` | Save ordered photos and each photo’s lifecycle atomically. |
| `wt batch --file <json>` | Related metadata/data repairs in one validated transaction. |
| `wt import <file> posts\|personal [name]` | Supported normalization preserving outputs. |
| `wt import <file> courses <course> [chapter]` | Import an authored chapter into its course TOC. |
| `wt register project <id> <path> <title>` | Register existing code; `make project NAME=<slug>` scaffolds it. |
| `wt validate` | Schemas, references, lifecycle/content agreement, H1s, TOCs, images, registration. |
| `wt cat`, `edit-cell`, `append-cell`, `insert-cell`, `remove-cell`, `tag` | Supported notebook operations; never edit raw JSON. |
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

The CMS edits structured fields/plans. “Edit in VS Code” opens the canonical
notebook; “Start and edit” first materializes it through the lifecycle service.
Notebook lifecycle choices follow the canonical source: Planned before authored
content exists, then Draft or Published. Metadata and plans can be saved while
Planned; authored notebooks cannot be returned to Planned.
Portfolio editors accept a featured image (PNG, JPEG, WebP, or GIF, up to 20 MB)
and figure caption. Saving stores the image under `content/assets/portfolio/`
with the metadata in one transaction. Portfolio cards show it below the abstract;
planned and draft project cards and pages show a yellow diagnostic panel with monospace publication metadata.
Planned entries include the setup command with the actual stable ID in `wt start <id>`.
Course editors accept a card image in the same formats and size limit, stored
under `content/assets/courses/` through the catalog's `cover` field. It appears
in the Courses card grid. Personal photo editors support uploading new photos
and replacing existing ones under `content/assets/photos/`. Images and metadata
save in one transaction; leaving an upload empty keeps the saved image.
Starting an active portfolio creates its notebook and `projects/<name>` with
the same package scaffold as `make project NAME=<name>`, and registers both
in one recoverable save. The name comes from the configured project name or
the final segment of the stable ID. Existing project code is reused untouched.
Drafts may start before the abstract and featured figure are complete;
publication still requires the abstract, image, and caption.
Planned project pages group source and related-page links under “Related content:”
as bullets. They include the reserved active code URL before the directory exists;
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
callout. Captions appear above images. All draft pages and photos use the shared
yellow publication-status panel with instructions, visible only in working previews. Draft course cards, course sidebar
links, and post listings show matching yellow `draft` badges. Production excludes
draft pages, links, cards, and assets.
The gallery page state is derived automatically; there is no collection-level
publication control in the CMS.

The CMS uses the available width. Short information and row actions stay visible.
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
Personal has **Add photo** and **Edit photos** actions; Add photo opens the composer.

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
frontend placeholder without a VS Code link until started.

All Kanban CLI writes accept `--expected-revision`. Read `wt kanban ls` first and
pass its revision for a coordinated write. HTTP uses `GET/POST /api/kanban` and
`PATCH/DELETE /api/kanban/<card-id>` with `If-Match` required for writes. CMS,
CLI, and HTTP share the same validation, lock, recovery and conflict handling.

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

All catalog entities use **tags** as their single taxonomy. Legacy notebook
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
the same toolbar. Planned entries also offer Start and edit there. Publication
uses the saved revision and stays disabled while metadata has unsaved changes.
Photo width fields show
`100%` as the blank/default hint. Kanban cards show links and actions directly;
Add, Edit and Remove open accessible native dialogs with keyboard dismissal,
focus restoration and unsaved-change protection. Their links also provide a
server-rendered form when JavaScript is unavailable.
