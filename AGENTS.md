# Watchtower agent instructions

## Sources and orientation

Run `.venv/bin/wt map` first. The venv is required; never use bare `wt`.
Use the CLI for agent work; Watchtower has no MCP server. Every `wt` command
below is shorthand for `.venv/bin/wt`, run from the repository root. Discover
commands with `.venv/bin/wt --help` and inspect arguments with
`.venv/bin/wt <command> --help` (nested commands have their own help).
Use `wt context <id>` for artifact metadata, `wt data <name>`
for structured records, `wt gallery` for photos, and `wt kanban ls` for tasks.
Use their supported mutation commands. Data/gallery/Kanban reads expose the
workspace revision; pass it with `--expected-revision` where available.
CLI mutations capture a revision when omitted. Use `.tmp/` files for larger payloads:
`wt update <id> --patch-file .tmp/patch.json`, `wt data <name> --file .tmp/data.yaml`,
or `wt batch --file .tmp/batch.json`. Check command help for the payload format.
Active artifacts are registered in `content/data/catalog.yaml`: posts, courses,
chapters, portfolio entries, executable projects, personal notebooks, galleries.
Canonical authored notebooks live under `content/notebooks/`; supporting assets
under `content/assets/` (notebook-relative sidecars are supported). Operational
code in `src/` and `scripts/` is outside the catalog.

Course contracts/ordered TOCs live in `content/data/courses/<slug>.yaml`, portfolio
details in `content/data/portfolio.yaml`, profile/résumé in `content/data/profile.yaml`,
ordered photo headings, paths, captions, and draft/published states in `content/data/photos.yaml`. Personal shows photo
rows only. Preserve former gallery prose privately, outside that surface. The
empty gallery is planned until real photos arrive; never invent photos/captions.

Historical work remains under `archive/2026-09-30/`. Retired publishing inputs are
under `archive/2026-10-01/content-system-inputs/`. Archives are source material,
not evidence of current facts. Use `wt map --archive`, `wt ls <tier> --archive`,
or `wt find <query> --archive` deliberately. Historical portfolio references
link archived code without making it an active project or workspace member.

Read course context in this order:

1. `wt context <id-or-path>` for the record, contract, and reading paths.
2. Its contract YAML: purpose/audience, planned intent, actualized facts, TOC.
3. `index.ipynb`, the learner-facing course home.
4. Optional `00-overview.ipynb` for whole-course technical design.
5. The target chapter; adjacent openings only for a relevant handoff.

A plan is not completion evidence. Update `actualized` only after completed,
checked work. Shared concise facts/navigation belong in course YAML; teaching
belongs in notebooks. Generated context includes appear only in the Quarto build.
Do not load all sibling notebooks by default.

## Notebook operations

Never grep or edit raw notebook JSON. Use `wt find`, `wt cat --index N --context 3`,
then `edit-cell`, `append-cell`, `insert-cell`, or `remove-cell`. Mutations use
exactly one locator. Structural edits shift indices: re-read afterward. `cat`
accepts IDs, stems, tier-prefixed stems, paths, ranges, tags, labels, offsets, and
stored outputs. The default source limit is 4096 characters per cell; `--limit 0`
is unlimited. Writes are capped at 20,000 source characters per cell.

Source notebooks own body cells, execution metadata, attachments, outputs, and
cell-level Quarto options. Document front matter belongs in generated copies.
Chapters have exactly one real H1 matching the full catalog title; fenced-code
examples do not count. `toc_title` is an independent short navigation label.
Use `wt update <id> --title ...` for coordinated metadata/H1 changes. Preserve
individual cell visibility/folding options.

Review with `wt diff`; moved sources support `--base-source <old-repository-path>`.
Run edited code with `wt run <id> --index N`, then inspect `wt output`. Markdown-only
notebooks need no kernel run. Use `wt kernels` for environments. Quarto renders
stored outputs without executing cells. Preserve the public `watchtower.core`
imports: `Plot`, `Panel`, `set_format`, and `set_seed`.

## Management and publication

`wt new post`, `new course`, `new chapter`, and `new portfolio` register plans
without creating source notebooks. `wt start <id>` creates a draft from persisted
planning data, retains the plan, and refuses existing source files. Post plans
accept arbitrary Markdown; chapters require planned content and lab/evidence;
portfolio plans have introduction, what it contains, optional scope notes.
Starting an active portfolio also initializes and registers `projects/<name>`
using the same package scaffold as `make project`. Use its configured project
name, or the final stable-ID segment when omitted. Reuse existing code without
overwriting it. Notebook, scaffold, and registrations share one recoverable save.
Draft portfolio entries may omit abstract/figure metadata; publication requires
the abstract, featured figure, and caption.
Planned portfolio pages include reserved active source URLs before code exists.
Portfolio cards and pages show planned/draft state as yellow diagnostic panels with monospace publication metadata.
Planned entries include the setup command with `wt start <actual-stable-id>`.
Active code directories are required for Draft/Published portfolio entries;
archived source references must always resolve to existing archived code.
Plan files must be under `<repo>/.tmp/`; persist their bodies before removing them.

`wt import` uses supported normalization and defaults authored content to draft.
Use `wt update` for metadata/tags/relations, `wt data` for structured records,
`wt gallery` for atomic per-photo lifecycle saves, and `wt batch` for related repairs.
`new section` and chapter section updates preserve catalog/plan/TOC consistency.
Record actualized work explicitly. `make project NAME=<name>` scaffolds/registers
code; `wt register project` registers existing code. Portfolio abstracts/figures
and active/archived references belong in portfolio YAML, not duplicated project
paths or per-entry GitHub URLs.

Planned notebooks have no authored content and render metadata-generated pages.
Title-only scaffolds are empty. Draft/published entries require authored content
and render actual copied notebooks. Repair manual lifecycle disagreements through
metadata update or eligible publication, validating the proposed final state.
CMS notebook lifecycle choices follow inspected canonical content: Planned for
empty entries, Draft/Published for authored entries, including state repairs.
Do not demand that the old semantic state already pass. Malformed YAML/duplicate
keys require explicit repair and must not be silently overwritten.

`wt publish <id>` requires public visibility, content, and a public published
parent for chapters. `wt draft <id>` preserves source/visibility and returns
published content to draft. Neither commits/pushes, changes siblings, nor proves
deployment. Production includes public published pages and public planned
placeholders; Portfolio cards require published entries. Private/draft courses
suppress all child pages/links/assets while retaining states and membership;
planned courses show only planned children.

`make preview PORT=4300` watches saved inputs, showing all valid states locally.
`make build` validates/renders production. Only successful output is promoted.
GitHub Actions rebuilds committed inputs on `main` and deploys to existing
`gh-pages`. CMS `/cms/`, API `/api/`, and CLI call the same services. Notebook
body editing/execution remains in VS Code/Jupyter. CMS refresh uses saved files,
reports async progress/failures, and never executes cells or changes publication.

## Tooling, writes, and isolation

Managed reads/writes, notebook operations, and build snapshots share the ignored
`backend/runtime/` lock/recovery gate. API requires `If-Match`; CMS carries revisions;
CLI mutations accept `--expected-revision`. Never retry stale writes automatically. Resolve
pending journals before new work. Recovery rolls forward only from matching
preimages/absence; external edits block it while all versions are retained.
Never blindly roll back or overwrite divergent bytes. Uncoordinated IDE saves
have a remaining check-to-replace race; pause affected saves when strict
coordination is required.

`frontend/generated/` and `backend/runtime/` are ignored build/runtime state.
Templates/site assets/settings live under `frontend/`; CMS templates/styles never
enter public generation. The black/gray/blue motif is CMS-only: retain existing
public-site styling. Never edit generated headers/listings/configuration, résumé
artifacts, or context includes. `make knowledge`, `wt sync-site`, and
`wt render-context` regenerate compatible projections. `make resume` generates
profile outputs; `make render NOTEBOOK=<id-or-path>` generates a notebook PDF.

For new courses/multi-file revisions, use an isolated Git worktree when possible
and preview separately, usually port 4300. Never reset/overwrite a dirty primary
checkout. Scratch files belong in `.tmp/`, not system `/tmp`. For Python changes,
run `make lint`, `make typecheck`, and `make test` for behavior changes; validate
and render affected content. Archived projects are excluded from active checks.
Update both this file and README whenever the CLI surface changes.

Skills have canonical sources under `skills/`; `.codex/skills/` and
`.opencode/skills/` are links. Edit canonical files; run `make setup-skills` when
creating skills. Load course-builder, notebook-writing-style, and quarto-jupyter
for relevant content work. Keep secrets in the OS keyring through `wt vault`;
never print/commit values. Use plain prose and em dashes sparingly.

If a supported notebook operation is missing/fails, explain the command, gap,
and expected result, then ask whether an issue should be filed. Never manipulate
raw JSON as a workaround.

Each photo has a required heading, caption, and `lifecycle: draft|published`.
Draft photos may omit the path and show a "No Photo" placeholder in the CMS and
working preview. Published photos require a safe path to an existing image.
CMS course card uploads save to `content/assets/courses/` and update catalog
`cover`; Personal uploads save to `content/assets/photos/` and update photo
`path`. Both accept PNG, JPEG, WebP, or GIF up to 20 MB and save images with
metadata atomically. Empty uploads keep existing images; row moves keep uploads
with their photos.
Photos support optional `width: "80%"` (greater than 0, at most 100%). Blank or
omitted width preserves default image sizing; CMS edits and adds this field.
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

## Author Kanban and CMS collections

Kanban is the final CMS tab, with To do / In progress / Review / Done columns.
Task cards live in `content/data/kanban.yaml` (version 1, `cards`); absence means
an empty board, while malformed existing YAML requires explicit repair. Cards
have permanent human references (`card#1`, `card#2`, ...) alongside immutable
internal IDs; references appear in the CMS and `wt kanban ls`, and can be used
with update, move, and remove. Numbers are never reused. `artifact_ids` link only exact registered stable IDs; reject unknown
IDs without saving. Task movement does not change artifact lifecycle or visibility.
Kanban stays off public pages. Frontend links point at the working preview; VS Code
links require an existing canonical notebook, gallery data file or project directory.
Use `.venv/bin/wt kanban ls`, `add --title ... [--link <stable-id>]`,
`update <card-id>`, `move <card-id> <column>`, or `rm <card-id>`; columns are
`todo`, `in-progress`, `review`, `done`. Mutations accept `--expected-revision`.
Read `wt kanban ls` first and pass its revision for a coordinated write.
`wt data kanban` and the structured-data API support whole-board reads/repairs.

CMS short information and row actions stay visible. Every employment, early
employment, skill and education entry starts folded in résumé views and editors,
regardless of content length. General appears first in résumé
editing, followed by Contact, Employment, Early employment, Skills and Education.
Profile editing uses Home/Résumé `?edit=profile`, starts in editing mode, and
preserves the originating section for Save, Cancel and Back navigation. Category
and record field order match the résumé view; stale saves preserve submitted
values and the original revision.
Posts support title search with pagination preserving active filters. Long lists
scroll; client pagination retains all form controls and selected uploads in the DOM.
Personal provides Add photo (opens its composer) and Edit photos actions.

## Entity deletion

Use `wt delete <id> --dry-run` to review removal
and its revision. `wt delete <id> --expected-revision <revision>`
removes registrations while retaining files; `--cascade` is
required to include a course's chapters. CMS Delete links open the same review
and require explicit confirmation. API `GET /api/deletions/<id>` reviews;
`DELETE /api/artifacts/<id>` requires `If-Match` and optional `cascade=true`.
Incoming catalog relations, Kanban artifact links and résumé artifact links are
detached, preserving their containing records. Chapter deletion repairs the
parent contract TOC, plans and overview. Portfolio deletion retains its project
registration; project deletion retains the code directory.
Authored notebooks and removed course contracts are archived byte-for-byte under
`archive/deleted/<operation-id>/`, with removed metadata and affected preimages
in `record.json`. Images and project code stay in place. Archival copies and
active-file removals share the revision/recovery transaction. Never purge these
files or edit archived notebook JSON. Individual photos, résumé rows and Kanban
cards have existing removal controls; the built-in gallery is not deletable.

CMS creation asks for a Name and generates a kind-specific stable ID and source
path; e.g. `test` becomes `portfolio/test`, and post `gliner` becomes `post/gliner`
at `content/notebooks/posts/gliner.ipynb`. Chapters choose course and section by
title. Spaces and punctuation in names become hyphens.
Deletion permanently reserves removed IDs and notebook sources in catalog
`retired_ids` and `retired_sources`, including planned entries without files.
Do not reuse retired names or clear these reservations when deleting archives.
Creation rejects case variants and active filenames owned by legacy post IDs.
All catalog entity kinds use tags as their single taxonomy. Legacy/imported
categories merge into tags with case-insensitive deduplication. CMS fields show
only tags; routes are managed site metadata and CMS writes cannot change them.
Preserve existing legacy routes. Catalog cover controls appear only for courses,
as Card image; portfolio figures and photo uploads use their dedicated fields.

Use disclosure for each résumé employment, early employment, skill and education
entry, plus course chapters and project content. Keep contacts, short action rows
and basic editor groups visible. Photo overviews use
120×120 thumbnails with direct `/cms/photos/<index>/edit` links; editing starts
immediately and saves only that photo, using the shared revision/upload service.
Personal has no page-wide Edit photos action. Reorder photos below the list opens
the compact photo list with per-photo up and down actions; it does not expose the
full gallery metadata editor.
Portfolio row Edit links open the combined artifact/detail editor with editing
enabled immediately. Save and Cancel return to Portfolio; do not add a separate
bulk-detail editor link to this flow.
Artifact publication and deletion controls belong in the editor toolbar beside
Cancel and Save, without a separate Publication actions section. Keep lifecycle
forms separate from metadata saves, carrying the same revision. Disable
publication while metadata is dirty or saving.
Blank photo width fields show a `100%` hint. Kanban card actions are visible;
Add/Edit/Remove use native dialogs with keyboard dismissal, focus restoration,
unsaved-change handling and server-rendered fallback links. Preserve revisions,
submitted values and uploads through these interactions.
