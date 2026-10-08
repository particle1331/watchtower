# Watchtower agent instructions

## Sources and orientation

Run `.venv/bin/wt map` first. The venv is required; never use bare `wt`.
Use the CLI for agent work; Watchtower has no MCP server. Every `wt` command
below is shorthand for `.venv/bin/wt`, run from the repository root. Discover
commands with `.venv/bin/wt --help` and inspect arguments with
`.venv/bin/wt <command> --help` (nested commands have their own help).
Use `wt context <id>` for artifact metadata, `wt plan <stable-id>` for saved
authoring plans and internal notes, and `wt data <name>`
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
Generated notebook copies render the catalog title once: a non-chapter H1 that
repeats the title is dropped from the build, and chapters keep their authored H1
because their generated title block is empty.
Use `wt update <id> --title ...` for coordinated metadata/H1 changes. Preserve
individual cell visibility/folding options.

Review with `wt diff`; moved sources support `--base-source <old-repository-path>`.
For shared notebook edits, read with `wt cat --with-revision` and carry its
`notebook:<hash>` token through `--expected-revision` on `edit-cell`,
`append-cell`, `insert-cell`, `remove-cell`, `tag`, `clear-outputs`, and `run`.
The token covers exact notebook bytes; structural edits and output saves also
invalidate it. Re-read after a conflict before deciding on a new write.
Run edited code with `wt run <id> --index N`, then inspect `wt output`. Markdown-only
notebooks need no kernel run. Use `wt kernels` for environments. Quarto renders
stored outputs without executing cells. Preserve the public `watchtower.core`
imports: `Plot`, `Panel`, `set_format`, and `set_seed`.
Execution releases the workspace lock while the kernel runs, then checks source
bytes before saving. Conflicting execution results are retained under
`.tmp/execution-conflicts/`, with their path in the error; inspect them and the
current source rather than blindly copying them over it.

## Management and publication

`wt new post`, `new course`, `new chapter`, and `new portfolio` register plans
as private CMS-only entries without creating source notebooks. `wt start <id>`
creates a private draft seeded from supported plan fields, retains the plan and
internal notes, and refuses existing source files.
Planning fields are optional for starting across CMS, CLI and API. No generation
flag is implemented; use the saved build brief to author content explicitly.
Post plans accept arbitrary Markdown; chapter plans may be partial;
portfolio plans have introduction, what it contains, optional scope notes.
Starting an active portfolio also initializes and registers the code directory
behind its `project_path` using the same package scaffold as `make project`.
Each entry stores one `project_path`: `projects/<name>`, or
`archive/<date>/projects/<name>` for migrated historical work. It defaults to
`projects/<name>` from the final stable-ID segment; legacy project
name/source/date triples normalize to it on load. Reuse existing code without
overwriting it. Notebook, scaffold, and registrations share one recoverable save.
Draft portfolio entries may omit abstract/figure metadata; publication requires
the abstract, featured figure, and caption. Portfolio CMS forms use one visible
Abstract field: the create form keeps it under optional planning details, and the
entry editor is where a finished abstract is pasted. Start seeds a blank abstract
from introduction/contents (opening prose, capped at 80 words), preserving
explicit abstracts or legacy descriptions. A still-blank abstract is seeded again
while the draft still matches its last seed; plan edits never overwrite an
existing abstract. CMS editing preserves
legacy description fallbacks as abstracts on explicit save.
Planned portfolios have no frontend pages or cards.
Portfolio scope notes stay in the internal brief.
Start seeds posts with outline/audience/takeaway/evidence; portfolios with
problem/users/contents/approach/success criteria/references; courses with
purpose/audience/progression/prerequisites/outcomes/project/tools/assessment;
chapters with content/labs.
Post, course, chapter and portfolio references may be seeded. Internal notes,
next steps, unknown fields and portfolio scope notes remain internal.
Seeding never rewrites hand-edited cells. While a started draft still matches
its last seed exactly (a stored fingerprint of the seeded section cells; the
title cell is excluded so coordinated renames do not count as edits), saving the
plan re-seeds its sections and fills a still-blank abstract. The first hand edit
freezes the draft, and notebooks without a stored fingerprint are treated as
edited. Empty plans
create title-only drafts. Review seeded prose before publication. Course chapter
tables remain generated, not copied into notebooks. Draft portfolio cards and pages
show yellow diagnostic panels with monospace publication metadata in preview.
Portfolio entry pages project the abstract, featured figure and source link from
portfolio YAML in the generated copy; the notebook keeps only its own content.
Active code directories are required for Draft/Published portfolio entries;
archived source references must always resolve to existing archived code.
Plan files must be under `<repo>/.tmp/`; persist their bodies before removing them.

`wt import` uses supported normalization and defaults authored content to draft.
Use `wt update` for metadata/tags/relations, `wt data` for structured records,
`wt gallery` for atomic per-photo lifecycle saves, and `wt batch` for related repairs.
`update --planned-content` changes post/personal content, chapter-plan content,
or the course-contract summary. Chapters accept `--planned-lab-and-evidence`;
chapter and portfolio `--plan-file` use their creation section format.
Portfolio inline content is ambiguous and rejected; use its plan file or a
`detail.planned` patch. Existing planning fields and actualized facts survive.
`batch --file .tmp/batch.json` accepts `{"updates": [{"id": "...", "patch": {}}], "data": {}}`;
the positional file form remains supported. Supply exactly one file form.
`new section` and chapter section updates preserve catalog/plan/TOC consistency.
Record actualized work explicitly. `make project NAME=<name>` scaffolds/registers
code; `wt register project <path> <title>` registers existing code. Registration
requires an existing code directory. Missing referenced code or assets leave the
workspace invalid and block saves, while deletions tolerate them so `wt delete`
can retire the records that point at them. The CLI
commands `new`, `import`, `register`, and `kanban add` do not accept custom IDs.
`new` and `import` derive IDs from names; `register`
derives IDs from the source filename stem (directory name for courses/projects),
prefixed by kind or the required `--parent` course ID for chapters.
Portfolio abstracts/figures
and the project path belong in portfolio YAML; per-entry GitHub URLs are never
stored. `project_path` is the single code reference (`projects/<name>`, or
`archive/<date>/projects/<name>` for migrated historical entries), validated and
turned into a source URL from shared repository settings. The CMS shows one
Project path field with that default; repair it through `wt data portfolio` or
the structured-data API.

Planned notebooks have no authored content and never render in preview or production,
including legacy public plans. Draft requires a source notebook and may contain
only its title; Published requires content. Draft and published pages render actual
copied notebooks. Repair manual lifecycle disagreements through metadata update or
eligible publication, validating the proposed final state.
CMS notebook lifecycle choices follow inspected canonical sources: Planned for
absent sources, Planned/Draft for empty scaffolds (allowing legacy repairs), and
Draft/Published for authored notebooks. Publish rejects empty scaffolds.
Do not demand that the old semantic state already pass. Malformed YAML/duplicate
keys require explicit repair and must not be silently overwritten.

`wt publish <id>` requires content, sets visibility to public atomically, and
requires a public published parent for chapters. `wt draft <id>` preserves
source/visibility and returns published content to draft. Neither commits/pushes,
changes siblings, nor proves deployment. Production includes only public published
pages. Private/draft courses suppress all child pages/links/assets in production;
planned courses suppress all children in both modes. Preview shows started private
or public courses and their started children. Personal keeps its per-photo rules.

`make preview PORT=4300` watches saved inputs, showing drafts and published pages locally.
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
callout. Captions appear after images. Personal renders once from
`frontend/templates/site/personal.qmd.j2`, without a generated gallery notebook or duplicate page.
All draft pages and photos use the shared
yellow publication-status panel with instructions, visible only in working previews. Draft course cards, course sidebar
links, and post listings show matching yellow `draft` badges. Production excludes
draft pages, links, cards, and assets.
The gallery page state is derived automatically; there is no collection-level
publication control in the CMS.

## CMS planning and course organization

New CMS plans default to private visibility, labeled Not on the live site.
New posts, personal notebooks, portfolios, courses and chapters default Date to
the creation day in the site's configured timezone. Preserve explicit dates;
later saves do not refresh the default.
Guided creation/editing fields capture post outlines, portfolio scope, course
contracts and chapter content/labs, plus optional audience, evidence, references
and next steps. Partial plans can be saved and started. Start seeds supported
fields into notebook sections once and sets Draft/private. Publish sets public.
Every artifact has persistent Markdown `internal_notes`, editable in the CMS,
through `wt update <id> --internal-notes ...` (or a patch file), and the API.
Notes and structured plans remain editable in every lifecycle, including Published;
changing them never changes notebook bytes or publication state. Copy build brief
exports saved fields, notes, IDs, paths and context; course briefs include ordered
chapter plans and notes, and chapter briefs include parent-course notes.
`wt plan <stable-id>` returns JSON with identity/lifecycle, reserved or existing
`source_path`, effective structured `plan`, `internal_notes`, the same CMS
`build_brief`, and workspace `revision`. Use an exact registered stable ID, not a
title, stem or source path. This read works for partial plans and every lifecycle;
it neither creates nor executes a notebook. Course plans include ordered chapter
plans in the build brief; chapter briefs include parent-course context.

Plans are not rendered directly in preview or production. Internal notes remain
excluded from pages, generated course context and metadata. Started notebooks own
their seeded content. Public fields include catalog `description`, portfolio
`abstract`, and chapter-plan `summary` for the course table. Review seeded course
purpose/audience and planned summaries as learner-facing prose before publishing.
Actualized facts remain explicit completed-work records and can render in course
context. Internal means excluded from the site, not confidential in a public Git
repository. Preserve legacy plan text and existing authored notebooks; do not
infer public summaries from notes or silently scrub previously authored prose.
Kanban tracks work independently of publication state, using artifact links.

Use `/cms/courses/<slug>` to edit the course brief and organize its outline.
Add sections, rename/reorder them, add chapters in context, reorder chapters or
move them between sections within that course. Remove empty sections only,
retaining at least one. All actions carry revisions and atomically synchronize
catalog membership, contract TOC and chapter plans. The advanced contract editor
remains available. A course metadata API patch can include `contract` for an
atomic brief save. Do not derive actualized facts from the plan.

Course homes derive their chapter table from ordered TOC, full catalog chapter
title, and chapter-plan `summary`, with columns Section, Chapter title, Summary.
Titles link to eligible chapter pages. The CMS shows the same ordered data once
in compact section/chapter rows; summaries and section transfer are disclosed
inside each chapter. Missing summaries prompt editing in CMS, show a placeholder
in preview, and stay empty in production. Builds filter rows through the existing parent/child publication
rules. Do not maintain a second table in authored notebooks or generated files.

All related stable-ID controls use search/select with suggestions by title or ID,
showing title/kind/ID/lifecycle. Multi-selects preserve order and deduplicate;
single links can be cleared. Native selects are the no-JavaScript fallback.
`/cms/lookup` is read-only (`q`, optional `kind`/`parent` filters). Search text is
never a saved relationship; shared services validate selected registered IDs.
Conflicts preserve submitted selections and original revisions, including missing
IDs for explicit repair. Legacy course `planned.content` is offered as a summary
only when the contract summary is empty, and persisted on explicit save; preserve
differing legacy text and unknown planning fields.

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
`kanban add` assigns both the internal ID and `card#N` reference automatically;
it does not accept `--id`. Use `.venv/bin/wt kanban ls`, `add --title ... [--link <stable-id>]`,
`update <card-id>`, `move <card-id> <column>`, or `rm <card-id>`; columns are
`todo`, `in-progress`, `review`, `done`. Mutations accept `--expected-revision`.
Read `wt kanban ls` first and pass its `board_revision` (`kanban:<hash>`) for a
task-only coordinated write. Its workspace `revision` is still accepted when
the decision depends on content as well. Board tokens survive unrelated
content saves and fail after any change to the board; never automatically retry them.
HTTP Kanban card writes accept either token in `If-Match`. Card mutations
return both tokens. Search also matches internal IDs and `card#N` references.
`wt data kanban` and the structured-data API support whole-board reads/repairs.
Whole-board data and batch saves preserve the numbering counter and existing
card references; omitted refs retain their saved value. Reassigned or reused
references are rejected. Explicit malformed-board repairs should include the
known counter and identities. `--link` and `--clear-links` cannot be combined.

Artifact editors and plan creation separate Site content, Build plan and Internal
notes into keyboard-accessible panes. Settings groups remain unfolded. Keep all controls in the same form when
switching panes so unsaved values and selected uploads survive. Without
JavaScript, show the areas as sections. Reveal a pane before native validation
focuses a required control. Internal notes, next steps and scope notes belong in
the CMS-only pane; chapter short summaries belong with site content. Preserve the
optional reader-facing Abstract in creation's optional planning details, with an
explicit site-content label. Course workspaces open on the compact outline.
Chapter reorder arrows and Edit remain visible; transfer and deletion sit inside
the chapter disclosure. Section settings start folded. Outline actions save
immediately with their original revision.

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
Personal provides Add photo, opening a standalone composer with Heading, Photo,
Caption, Lifecycle, and Width. Saving adds only that photo and returns to Personal;
existing photos retain their individual Edit links.

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
All catalog entity kinds use tags as their single taxonomy. Generated frontend
metadata maps tags to Quarto categories; the Posts listing uses native Quarto
category filtering. Keep categories out of the canonical data model. Legacy notebook
front matter may still contain categories; imports merge them into tags with
case-insensitive deduplication and discard the old field. CMS fields show only
tags; routes are managed site metadata and CMS writes cannot change them.
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
Cancel and Save, without a separate Publication actions section. In draft post,
portfolio, course and chapter editors, Publish submits the metadata form and
atomically saves metadata/uploads and sets Published/public using the submitted
revision. It remains enabled with unsaved edits; there is no extra Save and publish
button. Other lifecycle forms stay separate from metadata saves and are disabled
while metadata is dirty or saving. Validation or conflicts leave all
changes unsaved. Disable Publish only while saving; keep it clickable for
incomplete drafts and show the missing requirements after a failed attempt.
Chapters still require a public published parent; publishing a course does not
publish its chapters.
Blank photo width fields show a `100%` hint. Kanban card actions are visible;
Add/Edit/Remove use native dialogs with keyboard dismissal, focus restoration,
unsaved-change handling and server-rendered fallback links. Preserve revisions,
submitted values and uploads through these interactions.
