# Watchtower

A notebook publishing workspace with a local FastAPI/Jinja/HTMX CMS, a
revision-aware CLI and MCP server, and a generated Quarto website. The CMS uses
black, gray, and violet; the public website retains its existing styling.

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
CMS, JSON API, and MCP call the same file-backed services. Manual YAML edits
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
| `wt start`, `publish`, `draft` | Explicit notebook/publication transitions. |
| `wt update <id>` | Metadata/tags/plans; `--patch-file` supports variant fields and relations. |
| `wt data <name> [--file <yaml>]` | Profile, portfolio, photos, settings, or `course/<slug>`. |
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
| `make mcp` | Publishing tools over MCP stdio. |
| `make resume`, `make render NOTEBOOK=<id-or-path>` | Generate résumé/notebook PDFs outside authored content. |
| `make knowledge`, `wt sync-site`, `wt render-context` | Compatible regeneration of disposable Quarto projections. |
| `make lint`, `make typecheck`, `make test` | Tooling and publishing/recovery acceptance checks. |

All `wt` examples use `.venv/bin/wt`. `cat --context N` shows adjacent cells,
not sibling chapters. Read course context, home, optional overview, and target
chapter in that order. Record actualized learning from checked evidence only.

The CMS edits structured fields/plans. “Edit in VS Code” opens the canonical
notebook; “Start and edit” first materializes it through the lifecycle service.
Notebook lifecycle choices follow the canonical source: Planned before authored
content exists, then Draft or Published. Metadata and plans can be saved while
Planned; authored notebooks cannot be returned to Planned.
The global refresh builds saved inputs and reports progress/errors without
executing cells or changing publication. Notebook bodies remain in the editor.

## Revisions and recovery

Read responses expose SHA-256 revisions over exact workspace input bytes.
API writes require `If-Match` (428 missing, 412 stale); CMS forms carry that token.
CLI/MCP writes accept expected revisions and capture one when omitted. Stale
operations are never automatically retried. Managed clients share a workspace
lock and durable transaction journals. Recovery rolls forward from matching
preimages/absence and blocks on external changes, retaining all versions.
Conflicted journals prevent builds from replacing successful output.

An IDE can save between a final hash check and replacement: detection of
uncoordinated saves remains best effort. Pause affected saves during managed
changes when strict coordination is required. Keep scratch work in `.tmp/` and
secrets in the OS keyring through `wt vault`. Shared skills live in `skills/`;
`make setup-skills` maintains links. Archived code is excluded from active checks.

Each photo has a required heading, path, caption, and `lifecycle: draft|published`.
An optional `width: "80%"` sets image width relative to the content column;
accept percentages above 0 and up to 100%, or leave blank for the default size.
The CMS exposes width for existing photos and new rows.
Published photos render as individual H2 sections in Personal. Working previews
also show draft photos with a per-photo caution titled "Draft entry"; production
excludes draft photos and their assets. The gallery has no document-level status
callout. Captions appear above images. Draft posts, chapters, and course homes use Quarto’s native draft metadata and
banner, with drafts visible only in working previews.
The gallery page state is derived automatically; there is no collection-level
publication control in the CMS.
