# Watchtower agent instructions

## Sources and orientation

Run `.venv/bin/wt map` first. The venv is required; never use bare `wt`.
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
Their planned callout includes `wt start <actual-stable-id>`.
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
`gh-pages`. CMS `/cms/`, API `/api/`, CLI, and MCP call the same services. Notebook
body editing/execution remains in VS Code/Jupyter. CMS refresh uses saved files,
reports async progress/failures, and never executes cells or changes publication.

## Tooling, writes, and isolation

Managed reads/writes, notebook operations, and build snapshots share the ignored
`backend/runtime/` lock/recovery gate. API requires `If-Match`; CMS carries revisions;
CLI/MCP accepts expected revisions. Never retry stale writes automatically. Resolve
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

Each photo has a required heading, path, caption, and `lifecycle: draft|published`.
CMS course card uploads save to `content/assets/courses/` and update catalog
`cover`; Personal uploads save to `content/assets/photos/` and update photo
`path`. Both accept PNG, JPEG, WebP, or GIF up to 20 MB and save images with
metadata atomically. Empty uploads keep existing images; row moves keep uploads
with their photos.
Photos support optional `width: "80%"` (greater than 0, at most 100%). Blank or
omitted width preserves default image sizing; CMS edits and adds this field.
Published photos render as individual H2 sections in Personal. Working previews
also show draft photos with a per-photo caution titled "Draft entry"; production
excludes draft photos and their assets. The gallery has no document-level status
callout. Captions appear above images. Draft posts, chapters, and course homes use Quarto’s native draft metadata and
banner, with drafts visible only in working previews.
The gallery page state is derived automatically; there is no collection-level
publication control in the CMS.
