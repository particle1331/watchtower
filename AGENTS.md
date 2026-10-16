# Watchtower agent instructions

## Sources and orientation

Run `.venv/bin/wt map` first. The venv is required; never use bare `wt`.
Use the CLI for agent work; Watchtower has no MCP server. Every `wt` command
below is shorthand for `.venv/bin/wt`, run from the repository root. Discover
commands with `.venv/bin/wt --help` and inspect arguments with
`.venv/bin/wt <command> --help` (nested commands have their own help).
Use `wt context <id>` for artifact metadata, lifecycle, and the saved plan while
Planned, and `wt data <name>`
for structured records, `wt gallery` for photos, and `wt kanban ls` for tasks.
Use their supported mutation commands. Data/gallery/Kanban reads expose the
workspace revision; pass it with `--expected-revision` where available.
CLI mutations capture a revision when omitted. Use `.tmp/` files for larger payloads:
`wt update <id> --patch-file .tmp/patch.json`, `wt data <name> --file .tmp/data.yaml`,
or `wt batch --file .tmp/batch.json`. Check command help for the payload format.
Active artifacts are registered in `backend/data/catalog.yaml`: posts, courses,
chapters, portfolio entries, executable projects, personal notebooks, galleries.
Canonical authored notebooks live under `content/notebooks/`, with authored
sidecars beside them. Managed uploaded assets live under `backend/assets/`.
Operational code in `src/` and `scripts/` is outside the catalog.

`content/` is safe for authoring in VS Code/Jupyter: notebooks own their bodies,
stored outputs and cell options, while generated metadata and navigation stay
outside it. Use supported notebook commands for agent edits. New notebooks must
be registered; retire active entries with `wt delete` to synchronize links.
Use the CMS/CLI/API for `backend/data/`, `backend/assets/` and
`backend/attachments/`; do not manually edit managed files except for an explicit
repair. Validation/render failures retain the last successful preview/site.
Local authoring does not deploy; successful committed builds on `main` do.
Delete managed entries/files through the CLI, CMS or shared API; backend workers
apply retention policies. Do not manually prune managed storage or
`archive/deleted/`, except for an explicitly reviewed repair. The CLI has no archive
purge command; retain those archives until supported cleanup is implemented.
Active state, revisions and builds never require deleted archives; permanent
ID/source reservations remain in `backend/data/catalog.yaml`. Archived project
directories still referenced by active portfolio entries remain dependencies.
`wt migrate --layout` reviews moving the former content/data, content/assets and
content/attachments directories under backend. Apply with `--layout --apply`
and the reviewed `--expected-revision`; notebooks and public routes stay intact.
The move is recoverable and refuses collisions or stale inputs.

Course contracts/ordered TOCs live in `backend/data/courses/<slug>.yaml`, portfolio
details in `backend/data/portfolio.yaml`, profile/résumé in `backend/data/profile.yaml`,
ordered photo headings, paths, captions, and draft/published states in `backend/data/photos.yaml`. Personal shows photo
rows only. Preserve former gallery prose privately, outside that surface. The
empty gallery is planned until real photos arrive; never invent photos/captions.

Historical work remains under `archive/2026-09-30/`. Retired publishing inputs are
under `archive/2026-10-01/content-system-inputs/`. Archives are source material,
not evidence of current facts. Use `wt map --archive`, `wt ls <tier> --archive`,
or `wt find <query> --archive` deliberately. Historical portfolio references
link archived code without making it an active project or workspace member.

Read course context in this order:

1. `wt context <id-or-path>` for the record, contract, and reading paths.
2. Its course context: ordered TOC and public summaries; writing briefs only for Planned entries.
3. The CMS-managed `home` fields in that course contract, also exposed by `wt context`.
4. Optional `00-overview.ipynb` for whole-course technical design.
5. The target chapter; adjacent openings only for a relevant handoff.

Planned entries use the writing brief and have empty internal notes. Starting seeds the content once and consumes the plan. Course homes are committed CMS-managed content in contract `home`; posts, chapters and full portfolio project pages use notebooks. Portfolio listing entries use portfolio YAML. Consumed plans are hidden from the CMS and active agent context and cannot be changed. Keep unfinished questions and decisions in the modal’s Notes field (`internal_notes`), and checklist items in its separate To-dos field (`internal_todos`). Shared navigation and public summaries remain in course YAML. Generated includes contain the chapter table without an Actualized section. Do not load all sibling notebooks by default.

After starting, the content entity localizes its memory. The notebook is **committed memory**: accepted content and checked results, even while Draft. Internal notes are **localized near-term memory**: questions, decisions, experiments and the authoritative To-dos checklist. Linked Kanban cards are **execution memory**: a scoped objective, card Notes, card To-dos, progress and evidence for that execution. Card Notes and To-dos belong to the task and are editable in its CMS dialog or through `wt kanban update`; `wt kanban show <card-ref>` returns them with the current linked entity context. Do not copy the whole notebook or entity internal notes into a task. Before marking a task Done, write accepted results to the notebook or public metadata, preserve unresolved lasting context in the entity’s internal notes, and update its entity To-do item when verification establishes completion. Card checklist changes never automatically alter entity To-dos, and task movement never proves content readiness. Keep lasting reference files attached to the entity; use `wt attachments link <entity-id> <attachment-id>` to promote a task file without duplicating its bytes.

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
creates a private draft seeded once from supported plan fields, consumes the plan, and refuses existing source files. Planned internal notes must be empty for posts, portfolios, chapters and personal entries; planned courses keep notes and to-dos while their course home is refined.
Planning fields are optional for starting across CMS, CLI and API. No generation
flag is implemented; use the saved build brief to author content explicitly.
Plans take `##` sections named by catalog field (`wt context <id>` lists them while Planned). Chapter
plans may be partial. Portfolio plans recommend The problem, Planned content and Planned evidence; scope
boundaries belong in those fields while planning, and in internal notes after starting.
Starting an active portfolio also initializes and registers the code directory
behind its `project_path` using the same package scaffold as `make project`.
Each entry stores one `project_path`: `projects/<name>`, or
`archive/<date>/projects/<name>` for migrated historical work. It defaults to
`projects/<name>` from the final stable-ID segment; legacy project
name/source/date triples normalize to it on load. Reuse existing code without
overwriting it. Notebook, scaffold, and registrations share one recoverable save.
Draft portfolio entries may omit abstract/figure metadata; publication requires
the abstract, featured figure, and caption. Portfolio CMS forms use one visible
Abstract field in the Page section: creation may leave it blank, and the entry
editor is where a finished abstract is pasted. Start seeds a blank abstract
from the problem and contents (opening prose, capped at 80 words), preserving
explicit abstracts or legacy descriptions. Abstract seeding happens only at Start; later abstract revisions use Page metadata. CMS editing preserves
legacy description fallbacks as abstracts on explicit save.
Planned portfolios have no frontend pages or cards.
Start seeds one notebook section per filled plan field: posts, portfolios and chapters
get The problem, Planned content and Planned evidence. Chapter evidence stays in
`lab_and_evidence`; Outline and Practice and evidence remain plan-file aliases.
Summaries are never seeded. Internal notes never leave the CMS, and
unfinished work belongs in the started entity’s internal Notes and To-dos. Linked Kanban cards execute scoped work and add temporary task context.
Courses start without an editable home notebook. Start seeds contract `home` fields once from the course plan; the CMS then owns Course outcome, Course description, separate Requirements and Prerequisites item lists, and References. Requirements and Prerequisites render together as bullets under **Prerequisites**; References render as bullets. Skip either generated section when its list is empty. Each CMS list uses one item per line, and reference items support Markdown links. Related topics use catalog `relations` stable IDs and disappear from generated pages when no linked page is eligible. Course content is generated from ordered TOC and chapter summaries. Save home fields through `wt update --patch-file` with `{"contract":{"home":{"description":"..."}}}`; partial home patches preserve other fields. Read `wt context course/<slug>` for current committed content. Review `wt migrate --course-homes`, then apply with `--course-homes --apply --expected-revision <revision>` to convert legacy homes, preserving original notebook bytes and metadata under `archive/course-homes/<operation-id>/`. Public HTML URLs stay intact; executable homes must first move executable material into chapters.
Seeding happens only at Start. A title-only draft already owns its notebook; subsequent plan changes are rejected across CMS, CLI, API and structured-data saves. For posts, portfolios and chapters, The problem, Planned content and Planned evidence are temporary starter inputs, not permanent domain fields. Start removes their payloads from active metadata and preserves the old inputs in `archive/starter-seeds/`; the notebook cells own the content. Other consumed briefs remain hidden from active authoring context. Empty plans create title-only drafts. Review seeded prose before publication. Course chapter tables remain generated. Draft portfolio cards and pages show yellow diagnostic panels with monospace publication metadata in preview. Portfolio listing entries show the abstract, featured image and caption. Full entry pages show the preview draft callout and Portfolio / Project source links, then the notebook body and a generated Related content section linking eligible pages in relation order. Abstracts and featured images stay on the listing; the notebook keeps its own content. Portfolio forms expose Title, Abstract, Featured image, Figure caption, Code location, Related content, and, while Planned, The problem, Planned content and Planned evidence. Creation accepts a featured-image upload atomically. Legacy brief fields remain preserved and fold into content/evidence when starting.

Review `.venv/bin/wt migrate --starter-seeds`, then apply with `--starter-seeds --apply --expected-revision <reviewed revision>` to clean older Draft/Published post, portfolio and chapter records. The migration archives exact metadata preimages, removes consumed starter inputs and preserves source notebooks, chapter table summaries and Planned inputs. Starter fields belong to authoring inputs, not the typed chapter metadata schema.

Active code directories are required for Draft/Published portfolio entries;
archived source references must always resolve to existing archived code.
Plan files must be under `<repo>/.tmp/`; persist their bodies before removing them.

`wt import` uses supported normalization and defaults authored content to draft.
Use `wt update` for metadata/tags/relations, `wt data` for structured records,
`wt gallery` for atomic per-photo lifecycle saves, and `wt batch` for related repairs.
`update --plan-file` takes the same `##` sections as creation for every kind and
changes only the sections it contains (an empty section clears that field). `--summary`
sets the public sentence (post/course description, portfolio abstract, chapter table
summary); `--internal-notes` sets CMS-only notes. Hidden aliases `--description`,
`--planned-content`, `--planned-lab-and-evidence`, `--abstract`, `--introduction` and
`--what-it-contains` still work; `--scope-notes` is removed. Patch files remain for
variant fields and relations. Writing-brief changes apply only while Planned; public summaries and navigation remain editable after starting.
`batch --file .tmp/batch.json` accepts `{"updates": [{"id": "...", "patch": {}}], "data": {}}`;
the positional file form remains supported. Supply exactly one file form.
`new section` and chapter section updates preserve catalog/plan/TOC consistency.
`make project NAME=<name>` scaffolds/registers
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
Code location field with that default; repair it through `wt data portfolio` or
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
`make dev` starts the CMS (port 5200) and working preview (port 4200) together,
opening each in a browser tab when ready. `PORT` and `CMS_PORT` override those
ports. It rejects occupied ports, stops both servers if either exits, and Ctrl+C
stops both and their foreground render processes. For agent verification without
browser interaction, run `.venv/bin/python scripts/dev.py --no-browser` with
explicit free `--port` and `--cms-port` values.
`make build` validates/renders production. Only successful output is promoted.
GitHub Actions rebuilds committed inputs on `main` and deploys to existing
`gh-pages`. CMS `/cms/`, API `/api/`, and CLI call the same services. Notebook
body editing/execution remains in VS Code/Jupyter. CMS refresh uses saved files,
reports async progress/failures, and never executes cells or changes publication.
Every build prunes generated projects and build records under the render lock,
before rendering and after completion/failure. Keep the current preview and
production outputs, one successful fallback per mode (`<mode>-previous`), the
latest failed project per mode, and the latest 20 completed records/logs per mode
plus records for retained outputs.
Queued jobs stay intact; a prior running record is interrupted once a new worker
holds the exclusive render lock. Unclaimed standalone PDF/export projects get a
one-hour grace period. Cleanup never follows job-directory symlinks. Cleanup
errors are visible in build records/logs and retried on the next build without
changing the outcome of a successful render. Pending workspace recovery journals
are outside build retention.

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
enter public generation. The CMS follows the public site’s white/charcoal/orange palette. Retain existing
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
CMS course card uploads save to `backend/assets/courses/` and update catalog
`cover`; Personal uploads save to `backend/assets/photos/` and update photo
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
Guided creation and Planned editors capture plan fields and the public summary. Draft/Published editors capture page metadata and internal notes; they omit the consumed writing brief. Retired fields (next
steps, scope notes, takeaway, course progression) were archived under
`archive/2026-10-09/retired-plan-fields/` and cleared; reintegrate them by hand
if needed. Partial plans can be saved and started. Start seeds supported
fields into notebook sections once and sets Draft/private. Publish sets public.
Draft and Published artifacts have persistent Markdown `internal_notes`, editable in the CMS,
through `wt update <id> --internal-notes ...` (or a patch file), and the API.
Planned entries other than courses must have empty `internal_notes` and `internal_todos`; planned courses may hold them while the course home is refined; null inputs normalize to empty text/list, and nonempty writes are rejected. Notes stay editable after publication; structured plans are editable only before starting. Notes never change notebook bytes or publication state. Notes remain Markdown in `internal_notes`; To-dos are an ordered `internal_todos` array of `{text, done}` objects. The modal supports Add/Enter, check/uncheck, edit text, and Remove, with a live completed/total fraction. Changes stay in the same editor form, survive closing the modal, and save atomically with the editor revision. Without JavaScript, Save adds the new item and applies checkmarks/Remove on save. Agents use `wt update <id> --patch-file .tmp/patch.json` or an API patch for the array; `wt context` and `wt kanban show` expose the current list. Existing Markdown notes are preserved. Saved editors
offer Copy source path and Create Kanban task, opening the task composer with the
current artifact already linked. The editor omits the build-brief panel and the
duplicate portfolio notebook-path field. `wt context <stable-id>` returns the
artifact record, lifecycle, reading paths and workspace `revision`; while Planned,
it also returns the structured writing brief as `plan` and its `plan_fields`
schema. The plan keys disappear after starting, when the CMS course home or
notebook becomes the content authority. Context reads work for partial plans and
never create or execute notebooks. Course context includes ordered navigation;
chapter context includes its parent course. Use the internal-notes modal’s
separate Notes and To-dos fields for unfinished work. Keep public summaries and
course navigation accurate. Historical plan text in raw structured records must
not guide revisions of started content.

Plans are not rendered directly in preview or production. Internal notes remain
excluded from pages, generated course context and metadata. Started notebooks own
their seeded content. Public fields include catalog `description`, portfolio
`abstract`, and chapter-plan `summary` for the course table. Review seeded course
description/prerequisites and planned summaries as learner-facing prose before publishing.
Legacy actualized records remain preserved as history and never render in course context. Internal means excluded from the site, not confidential in a public Git
repository. Preserve legacy plan text and existing authored notebooks; do not
infer public summaries from notes or silently scrub previously authored prose.
Kanban tracks work independently of publication state, using artifact links.

Context attachments belong to artifacts or Kanban cards via their `attachments`
metadata. Exact bytes are shared under `backend/attachments/<sha256>`; each
reference keeps its filename, media type and size. Use `wt attachments ls [OWNER]`,
`add OWNER --file PATH` (repeatable), `link OWNER ATTACHMENT_ID`, or
`rm OWNER ATTACHMENT_ID`. OWNER is an exact stable ID or a card ID/`card#N`.
Reads return the workspace revision; carry it with `--expected-revision` for
attachment writes. Files are limited to 20 MB each. `wt context` exposes artifact attachment
metadata; `wt kanban show card#N` returns the card's Notes and
To-dos plus current linked plans, entity internal notes, parent/course context
and attachments for agents.
Context attachments never enter generated site output. They are repository files,
so CMS-only does not mean confidential in a public repository.
Removing the last reference moves the file and ownership metadata to
`archive/deleted/<operation-id>/`, alongside entity deletion content when applicable.
Shared files stay active while any owner references them. All managed writes,
including whole-board repairs/batch updates, apply this cleanup atomically.
Archived files are inert: no active reads, builds or reference counts depend on
them. This does not authorize manual pruning. Use supported backend cleanup;
until an archive-purge operation exists, retain legacy deleted archives.
Completed transaction journals discard attachment byte copies; pending recovery
journals retain them until recovery completes.

Use `/cms/courses/<slug>` to edit the course brief and organize its outline.
Add sections, rename/reorder them, add chapters in context, reorder chapters or
move them between sections within that course. Remove empty sections only,
retaining at least one. All actions carry revisions and atomically synchronize
catalog membership, contract TOC and chapter plans. The advanced contract editor is available only while Planned; started courses use outline controls and page settings. A course metadata API patch can include `contract` for an
atomic save. Consumed writing briefs remain frozen.

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
IDs for explicit repair. Legacy course `planned.content` may be recovered while Planned when the contract summary is empty; preserve
differing legacy text and unknown planning fields.

## Author Kanban and CMS collections

Kanban is the final CMS tab, with To do / In progress / Review / Done columns.
Cards have a fixed height with clamped title/description previews. Clicking the
card surface opens a detail dialog with full text, attachments, linked content
and Move controls. Cards can be dragged between columns; drops move the card immediately
and save through the JSON API with its saved board revision, without reloading the page.
The Move control uses the same background save with JavaScript and a native form otherwise.
Unsaved edits block moving cards. Failed saves restore the original position, show the
requested destination, and require reloading before another move; stale writes never retry.
Edit and Remove
remain visible on the board. Native
`/cms/kanban?view=<card-id>` links open the same detail view without JavaScript.
Each card has a Markdown Notes field and an ordered To-dos checklist for task-specific
execution memory. Add, edit, check, and remove checklist items in Add/Edit; the
card shows a completed/total count. These fields stay on the card and do not
automatically change linked artifact notes or checklists.
Task cards live in `backend/data/kanban.yaml` (version 1, `cards`); absence means
an empty board, while malformed existing YAML requires explicit repair. Cards
have permanent human references (`card#1`, `card#2`, ...) alongside immutable
internal IDs; references appear in the CMS and `wt kanban ls`, and can be used
with update, move, and remove. Numbers are never reused. `artifact_ids` link only exact registered stable IDs; reject unknown
IDs without saving. Task movement does not change artifact lifecycle or visibility.
Kanban stays off public pages. Frontend links point at the working preview; VS Code
links require an existing canonical notebook, gallery data file or project directory.
`kanban add` assigns both the internal ID and `card#N` reference automatically;
it does not accept `--id`. Use `.venv/bin/wt kanban ls`, `add --title ... [--link <stable-id>] [--notes ...] [--todos-file .tmp/card-todos.json]`,
`update <card-id> [--notes ...|--clear-notes] [--todos-file .tmp/card-todos.json]`,
`move <card-id> <column>`, or `rm <card-id>`; columns are
`todo`, `in-progress`, `review`, `done`. Mutations accept `--expected-revision`.
The JSON file replaces the whole checklist using `[ {"text": "Check the result", "done": false} ]`; use `[]` to clear it. `wt kanban show <card-ref>` returns the current card Notes and To-dos plus live linked entity context.
Read `wt kanban ls` first and pass its `board_revision` (`kanban:<hash>`) for a
task-only coordinated write. Its workspace `revision` is still accepted when
the decision depends on content as well. Board tokens survive unrelated
content saves and fail after any change to the board; never automatically retry them.
CMS Kanban forms use board tokens. HTTP Kanban card writes accept either token in `If-Match`. Card mutations
return both tokens. Search also matches internal IDs and `card#N` references.
`wt data kanban` and the structured-data API support whole-board reads/repairs.
Whole-board data and batch saves preserve the numbering counter and existing
card references; omitted refs retain their saved value. Reassigned or reused
references are rejected. Explicit malformed-board repairs should include the
known counter and identities. `--link` and `--clear-links` cannot be combined.

Artifact editors and plan creation use one form with three visible sections:
Basics (title, stable ID or name, chapter course and section), Plan (the writing brief, visible only while Planned;
core fields are marked "Recommended to start"), Page (public summary or abstract,
card or featured image, tags, related content, date and status). Internal notes
become available after starting and open from a button beside the title in a native dialog, with images/files and a
link to create a scoped execution task on Kanban. Closing this dialog preserves unsaved notes
and selected files; Save/Create persists them with the same form. Without JavaScript
the notes remain visible inline. Kanban Add/Edit dialogs accept context files too.
Plan and Page sit
side by side on desktop and stack on narrow screens. Every control lives in that one
form, so unsaved values and uploads survive any interaction. Reveal a collapsed
section before native validation focuses a required control. Creation offers
"Create and start draft". Only the title is required; an optional name defaults to
the title. Summaries remain optional. Saved editors offer Add summary task (Add
abstract task for portfolio), creating a linked Kanban card with execution instructions to retrieve current entity context and save the result. The card references the entity instead of copying its brief and notes.
Save pending edits first; new plans must exist before they can have a task.
An existing unfinished summary task is reused. The action uses the workspace
revision because its decision depends on the saved content as well as the board.
Configure images and code paths in the saved editor.
Source tools are directly visible. Course workspaces open on the compact outline.
Chapter reorder arrows and Edit remain visible; transfer and deletion sit inside
the chapter disclosure. Section rename/reorder and Add section controls stay open.
Course workspaces default to the outline; the Course brief tab retains form fields
and unsaved values. Outline actions save
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
active-file removals share the revision/recovery transaction. Archive purge belongs
to supported backend cleanup; manual filesystem pruning is reserved for an
explicitly reviewed repair. Never edit archived notebook JSON. Individual photos, résumé rows and Kanban
cards have existing removal controls; the built-in gallery is not deletable.

CMS creation asks for a Title and an optional Name and generates a kind-specific
stable ID and source path from the name or, when blank, the title; e.g. `test` becomes `portfolio/test`, and post `gliner` becomes `post/gliner`
at `content/notebooks/posts/gliner.ipynb`. Chapters choose course and section by
title. Spaces and punctuation in names become hyphens.
Deletion permanently reserves removed IDs and notebook sources in catalog
`retired_ids` and `retired_sources`, including planned entries without files.
Do not reuse retired names or clear these reservations when deleting archives.
Creation rejects case variants and active filenames owned by legacy post IDs.
Courses, chapters and portfolios have no tags. Ordered course outlines organize the material;
course briefs and chapter summaries provide agent context. `new course` and
`new chapter` and `new portfolio` do not accept `--tag`; metadata updates reject tags for these kinds.
Legacy course/chapter/portfolio labels are omitted on reads and removed on catalog saves;
imports discard their tag/category metadata. Notebook cell tags remain supported.
Other catalog entity kinds use tags as their single taxonomy. Generated frontend
metadata maps tags to Quarto categories; the Posts listing uses native Quarto
category filtering. Keep categories out of the canonical data model. Legacy notebook
front matter may still contain categories; other notebook imports merge them into tags with
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
CMS portfolio rows show the stable ID, Edit in VS Code, Copy source path and
Create Kanban task instead of expandable abstract/image details. Preserve their
lifecycle/visibility badges and Edit/Delete controls. VS Code links require an
existing notebook. Planned editors and post, portfolio and chapter rows show a
gray View plan button in that position, before Copy source path. It opens the saved
writing brief in a read-only CMS dialog with rendered Markdown and local equation
typesetting, preserving unsaved editor values. `/cms/plan/<stable-id>` is the native
page fallback. Empty/partial plans are readable; started entries have no active
plan reader and use the existing source action.
CMS post rows show the same stable ID and three developer controls while keeping
their summary, tags, lifecycle/visibility badges and Edit/Delete controls.
Post plans use Page on the left (Summary, Tags, Related content) and Plan on the
right (The problem, Planned content, Planned evidence), with larger textareas and
matching desktop column heights. Starting consumes those three writing fields
once; draft editors keep page metadata and internal notes. Preserve legacy post
audience/reference text in content/evidence when starting older briefs, retaining
their saved keys. Never reseed or restructure existing authored post notebooks.
Generated full post pages keep the **← Post** marker and draft preview panel,
omit Summary and author from the title area, and append eligible Related content
links in saved order. Summaries remain on the Posts listing; tags remain categories.
Chapter plans use the same Page-left / Plan-right layout, textarea sizing and three
seeded sections. Page keeps Course table summary and Related content. Visibility,
Date and Status sit directly below Title in post, portfolio and chapter editors.
Generated chapters keep their authored H1 and course navigation, omit the summary
subtitle and author, and append eligible Related content links. Chapter summaries
remain in the course table. Preserve existing authored chapter bodies and stored
legacy briefs; never reseed started chapters. Expanded chapters in CMS course
listings show stable IDs and the three developer controls alongside badges and
Edit/Delete. Edit in VS Code requires an existing notebook.
Course-outline chapter disclosures offer the same stable ID and developer tools,
using View plan while Planned. Chapter Back, Cancel and Save preserve the editor's
entry point: listing filters/pagination and its expanded course, or the parent
course outline. Label the listing link Back to Courses and the outline link Back
to the course title. Preserve that destination through failed saves, explicit
conflict reloads, lifecycle actions and summary-task creation.
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
publish its chapters. A chapter can leave Planned only after its course has started, so a
planned course holds chapter plans only and drafts appear only under started courses.
Blank photo width fields show a `100%` hint. Kanban card actions are visible;
Add/Edit/Remove use native dialogs with keyboard dismissal, focus restoration,
unsaved-change handling and server-rendered fallback links. Preserve revisions,
submitted values and uploads through these interactions.
