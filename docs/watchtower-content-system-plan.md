# Watchtower notebook publishing system

Status: draft for architecture and entity-model review. This document proposes the implementation; it does not change the current content contract.

## Goal and acceptance criterion

Make Watchtower a personal notebook publishing system with a FastAPI backend and a Quarto reader site. People and agents use the same content-management operations. The author works on notebook bodies in VS Code, runs cells in the Watchtower notebook environment, and previews or publishes through commands or tools.

The primary acceptance criterion is: **create or update, execute, preview, and publish a notebook without manually editing YAML or Quarto configuration.** `make preview` shows the working content locally. Publishing makes authored content appear on the live website through GitHub Actions after the publication change reaches `main`. Public planned entries can already appear there as metadata-generated placeholder pages.

This criterion concerns publication metadata and site configuration. Intentional per-cell presentation directives remain part of authored notebook content.

Posts, courses, chapters, portfolio pages, project records, personal entries, the gallery, and the structured résumé belong in the system. Preserve the notebook helper library, `watchtower.core`. Structured data can also be edited manually when the author chooses; the API/CMS provides the in convenient management path and the rendering verifier checks both forms of editing.

## Architecture and ownership

```text
content/
  data/                             # Tracked YAML; API/CMS-managed or manually edited
    catalog.yaml                    # Artifact metadata and source references
    portfolio.yaml                  # Abstracts, figures, notebook paths, project names
    profile.yaml                    # Structured résumé and home-page data
    courses/<slug>.yaml              # Course contracts and ordered section/chapter TOCs
    photos.yaml                     # Ordered photo paths and captions
  notebooks/
    posts/
    courses/<slug>/
      index.ipynb                   # Authored course home
      ...                           # Chapters and optional overview
    portfolio/                      # Accompanying portfolio notebooks
    personal/                       # Notebook-based personal writing
  assets/                           # Authored images and other supporting files

backend/
  runtime/                          # Ignored build records, locks, and logs

frontend/
  templates/
    site/                           # Quarto inputs, listings, notebook scaffolds, configuration
    cms/                            # Jinja pages and HTMX fragments for content management
    shared/                         # Shared navigation and presentation helpers
  assets/                           # Theme, CSS, fonts, bibliography, site-wide assets
  generated/                        # Ignored, disposable Quarto project and output

src/watchtower/
  core/                             # Public notebook computation and plotting helpers
  models/                           # Typed entity definitions and validation
  services/                         # Content, course, profile, and publication operations
  api/                              # FastAPI adapters
  cli.py                            # Existing wt entry point
  mcp.py                            # MCP adapter added after API and CLI are proven

projects/                           # Executable project code and uv workspace members
tests/
pyproject.toml
Makefile
```

- `content/` contains the tracked inputs to publishing: structured records in `content/data/`, authored notebooks in `content/notebooks/`, and supporting assets. The API/CMS may manage data records and scaffold notebooks; the author may also edit those records directly. Logs, generated includes, injected headers, and build products stay outside `content/`.
- Source notebooks own their cells, outputs, attachments, and notebook execution metadata. Document front matter is added only to generated copies. Cell options, figure labels, captions, and Quarto syntax within notebook bodies remain authored content.
- Code visibility and folding are cell-dependent and stay in the notebook's cell options. Preserve them when copying and rendering notebooks. Entity models have no generic `quarto` settings mapping or entity-level `show_code` field. Frontend templates control page layout, theme, and page-level TOC defaults.
- An actual chapter source notebook has one H1 containing its full title. Preserve that heading in copies used for draft/published rendering; render it once by suppressing the automatic chapter title block through the frontend template. A planned chapter needs no actual content notebook: synthesize its render notebook and H1 from metadata. Quarto supports replacing its `title-block.html` partial with an empty partial for this purpose ([template partials](https://quarto.org/docs/journals/templates.html)).
- Tracked YAML under `content/data/` owns durable content metadata. FastAPI, CLI, and MCP manage it through validated services, while manual edits remain supported. All operations read the current files rather than a separate database copy. Parse existing files, apply the requested operation in memory, and validate the proposed final state before writes; existing semantic errors can be repaired explicitly. Revision checks and a recoverable transaction journal govern writes as specified below. Fully validate a consistent saved snapshot before every preview or production render. Backend implementation remains in `src/watchtower/`; `backend/runtime/` holds ignored operational state.
- Generated notebook copies, course-context includes, listings, navigation, résumé outputs, and `_quarto.yml` are build products. A clean checkout can regenerate them. Local preview and production builds use separate generated trees and output directories.
- Rendering has two source paths: draft/published entries use copies of their actual authored content notebooks; planned entries use new render notebooks synthesized from catalog and course YAML. Never render an authored notebook as the source of a planned page. Rendering never writes placeholder bodies into `content/notebooks/`; the explicit start operation can materialize the chapter plan there as a draft notebook.
- Quarto renders stored notebook outputs without executing code. Notebook execution remains explicit.
- `watchtower.core` keeps its public imports: `Plot`, `Panel`, `set_format`, and `set_seed`. Notebook kernels use an environment with Watchtower installed. Core helpers stay independent of API startup and publication state; ML dependencies are installed when the notebook needs them.
- SQLite is unnecessary as the canonical store in v1. A future database may index content or record runtime jobs without changing the file ownership contract.
- Active project code remains under `projects/`. Historical portfolio writeups may explicitly reference code under `archive/<archive_date>/projects/` without restoring or registering that code as active work. Project writeups are portfolio or other registered content, linked through stable IDs.

## Technology stack and parallel CMS

The author CMS uses **FastAPI + Jinja2 + HTMX**, served by Uvicorn. Python services and Pydantic schemas handle content operations and validation. Retain Typer/Rich for `wt`, the existing YAML tooling for tracked records, nbformat/nbclient for supported notebook operations and explicit execution, uv for environments, and `watchtower.core` for notebook helpers. Jinja generates both CMS HTML and the inputs/templates used by the Quarto pipeline. Quarto remains the reader-site renderer, with GitHub Actions deploying its static output to GitHub Pages.

The CMS parallels the reader site in navigation, page hierarchy, and visual style. Reuse the site's theme and content layouts, then add author controls to the corresponding views:

| Site section | Corresponding CMS view and controls |
| --- | --- |
| Home | Edit profile identity, homepage introduction, and shared contact information. |
| Résumé | Edit the structured profile sections; validate and preview generated résumé outputs. |
| Portfolio | Use the same stacked project sections and project navigation; edit abstracts, figures/captions, project names, relations, and notebook plans. Show planned/draft entries for management with clear state labels. |
| Posts | Retain the post listing and right-hand Tags sidebar; create/edit plans and metadata, manage tags, and filter entries by lifecycle or visibility. |
| Courses | Show course homes and the same ordered section/chapter TOC; edit contracts, chapter plans/titles, section membership and ordering, and explicitly record actualized work. |
| Personal | Manage the photo gallery's paths/captions and personal notebook entries, using their respective entity models. |

Use the same validated records, section order, stable IDs, and generated route mapping in CMS views and reader pages. The CMS can display every registered state so unfinished work can be managed; clearly identify what is eligible for the live site. Portfolio publication filtering, course-parent eligibility, and private/draft exclusions remain the shared service rules. Do not maintain a separate CMS copy of navigation or content data.

Each notebook entry's CMS view presents its planning data or current content preview, editable metadata, current lifecycle/visibility, source notebook location when present, and the applicable Start, Edit in VS Code, Preview, Publish, or Return to draft actions. Notebook body editing and execution continue in VS Code/JupyterLab. Link to the Quarto preview for the actual reader presentation. Display service validation errors beside the affected fields and preserve unsaved form values on failure.

### Editing and refreshing from the CMS

Use CMS forms for structured fields such as phone number, email, title, description, tags, captions, planning prose, and course ordering. A user can save these changes directly through the validated services. Each draft/published notebook has an “Edit in VS Code” button that opens its canonical editable `.ipynb` under `content/notebooks/`. Resolve portfolio notebooks through `notebook_path`. Use a properly encoded `vscode://file/<absolute-path>` link, supported by [VS Code's URL handling](https://code.visualstudio.com/docs/configure/command-line#_opening-vs-code-with-urls). Opening the file does not change lifecycle or publication state.

For a planned entry with no authored notebook, show “Start and edit” alongside its plan form. It calls the shared start service to create the draft notebook, then offers/opens that notebook in VS Code after success. Existing-file and validation failures preserve the current entry and show actionable errors. Any optional “Open data file” or “Open project” action resolves the canonical YAML record or validated project folder through the service. Editor actions always target authored workspace files rather than generated Quarto copies; do not accept an arbitrary file path from the browser. Show the resolved source path and a copy-path fallback when the browser/editor cannot complete the launch.

Provide a persistent “Refresh site preview” button in the CMS navigation/toolbar, available from every content view, and an “Open preview” link. Refresh validates the saved records and notebooks, regenerates the local Quarto project, and renders/reloads the preview through the same service as `make preview`. Use saved files on disk; indicate unsaved CMS form changes so the author can save them first. Manual refresh is available alongside automatic preview watching. It never executes notebook cells, changes lifecycle, or commits/pushes changes; live publication continues through GitHub Actions.

Refresh returns a build record promptly, shows progress and the last successful refresh time, and exposes validation/render failures. Serialize refreshes through the workspace build service and retain the previous successful preview when a build fails. On successful refresh, update the preview link/status and reload an embedded preview if present.

FastAPI serves CMS page and action routes under `/cms/` and typed JSON API routes under `/api/`. Jinja renders complete pages; HTMX submits forms and refreshes the affected HTML fragments. Both adapters call the same Python services as the CLI and MCP. Return HTML fragments to CMS interactions and structured JSON to API clients. Keep CMS templates out of the generated public Quarto project; shared visual assets can be reused by both surfaces. The CMS runs locally against the workspace, while GitHub Actions builds the reader site directly from committed inputs.

Long-running preview/build operations return a build record promptly. The CMS displays progress, logs, validation failures, and completion through status updates, using the serialized workspace build service. A save or publication action does not need to wait for a full Quarto build to return its form response. Make the difference between saved publication state and the last successful GitHub Actions deployment visible in the author interface.

## Entity models for review

The existing catalog, course contracts, sidebar, notebook front matter, and résumé YAML are the migration inputs. Preserve their information before removing duplicate representations. Use typed models to validate these records and generate the API and tool schemas.

### Shared artifact record

| Field | Type | Origin and meaning |
| --- | --- | --- |
| `id` | string | Existing stable catalog ID; remains stable when source paths change. |
| `kind` | enum | Existing `post`, `course`, `chapter`, `portfolio`, `project`; add `personal` for notebook entries and `gallery` for structured photo collections. |
| `title` | string | Existing catalog and notebook field. For chapters, this is the full title and must match the notebook's H1. |
| `path` | relative path, where applicable | Variant-specific source locator: notebook, course directory, code project directory, or gallery YAML. Portfolio source references live in `portfolio.yaml`, matched to catalog records by ID. All source references are repository-relative. |
| `visibility` | `public` or `private` | Existing publication visibility. Private excludes content from public build input. |
| `lifecycle` | `planned`, `draft`, or `published` | Planned requires no authored content; draft/published require authored content. Publication remains separate from completed learning or project work. |
| `relations` | list of artifact IDs | Existing untyped relationships; retain this representation initially. |
| `date` | optional calendar date | Move from notebook front matter; default for new posts/personal entries is the creation date in the configured site timezone. |
| `description` | optional string | Move from notebook front matter; used for page descriptions and previews. |
| `categories` | list of strings | Broad content groupings, migrated from notebook front matter; default empty. |
| `tags` | list of strings | Free-form topic labels such as `attention`, `pytorch`, or `sqlite`; default empty. Manage through CLI/API/CMS, independently of lifecycle. |
| `image`, `image_alt` | optional strings | Move cover-image metadata from notebook front matter for notebook page types. Portfolio derives its figure from `figure_path` and `figure_caption`. |
| `render_path` | optional relative path | Proposed: location of the generated page source within the Quarto project. Preserve existing routes during migration; derive a default for new entries. |

The catalog at `content/data/catalog.yaml` retains a schema `version` and an `artifacts` list. Portfolio catalog records hold common identity and publication metadata; `content/data/portfolio.yaml` holds their type-specific data. Join the two by stable artifact ID, with exactly one detail record per portfolio catalog entry. Do not duplicate abstracts or source paths in the catalog. The gallery record points to `content/data/photos.yaml`. Creating a new post, chapter, or portfolio entry always creates its plan with lifecycle planned; starting its notebook creates authored content and changes it to draft. Importing an existing authored notebook is a separate operation that defaults to draft. Other empty entries default to planned. Explicit create operations collect or infer a title and intended source path, then register the entry automatically. Directly created or imported files are surfaced as unregistered content until adopted through the service.

### Lifecycle, authored content, and render sources

| Lifecycle | Actual notebook content | Render notebook source | Local preview | Public website |
| --- | --- | --- | --- | --- |
| `planned` | Must have none | Synthesized from catalog/course YAML | Planned placeholder | Planned placeholder when public and its course is eligible |
| `draft` | Must have content | Copy of actual content notebook | Authored page marked draft | Excluded |
| `published` | Must have content | Copy of actual content notebook | Authored page | Included when public and its course is eligible |

For notebook-backed entries, content means authored Markdown beyond the chapter's required title H1, nonempty code-cell source, stored outputs, or attachments. Whitespace and empty cells do not count. Planning descriptions stored in YAML and generator-owned placeholder notices do not count as authored notebook content. Text such as TODOs or prose describing planned lessons inside a source notebook does count; do not guess whether it is sufficiently complete to be content.

A planned entry may have no source notebook or an optional empty scaffold. If a chapter scaffold exists, it may contain only its validated title H1 and empty cells, with no outputs or attachments. It can reserve a future source path without creating the file. The render generator always synthesizes the planned page from metadata, regardless of whether such a scaffold exists. Use the title, description, section/TOC metadata, and course planning data to create the placeholder page and its planned status notice. Chapter planning data includes the bodies of both “Planned content” and “Planned lab and evidence”; render these as named sections, not merely a generic summary.

The verifier rejects planned entries with authored content and draft/published entries without it. The normal post, chapter, and portfolio workflow uses `wt start <id>` to create source content and change planned to draft together. If content was added manually to a planned source, explicitly update its lifecycle to draft through the metadata service before previewing, or use `wt publish <id>` when ready for public publication. These repair operations parse the current files without requiring their existing lifecycle/content agreement to pass; they validate the proposed final state, including all required content, references, and publication preconditions. `wt draft` returns published content to draft; it is not the operation for starting planned content. Neither rendering nor the verifier silently changes lifecycle or deletes content to make an entry valid. Returning an empty entry to planned uses the metadata update operation after its authored content has been removed deliberately.

These content-presence rules apply to notebook-backed entries. A data-driven gallery uses its photo collection as authored content: planned has no photo records, and draft/published has a nonempty valid collection. The structured résumé remains a separately validated singleton, and a code project's completion is not inferred from its associated writeup lifecycle.

### Artifact-specific records

| Entity | Additional fields and behavior |
| --- | --- |
| Post | Shared fields; notebook body is the article for draft/published entries. Public planned entries render metadata-generated placeholders; public published entries render their authored articles. |
| Course | Shared fields plus a course contract described below. Its directory contains a home notebook and its chapter sources. |
| Chapter | Retain required `parent`, referencing a course. Require `title`, `toc_title` (short navigation title), and `section` (the course section ID). Validate the full title against the notebook H1. The course TOC owns section/chapter order. |
| Portfolio entry | Shared catalog identity/publication fields plus a matching record in `portfolio.yaml`. Require `abstract`, `figure_path`, `figure_caption`, `notebook_path`, `project_name`, and `project_source` for draft/published content; archived code also requires `archive_date`. Planned detail records may omit not-yet-created assets/source references and render placeholders from metadata. Relations can link projects and other knowledge artifacts. |
| Project | Shared fields; `path` locates the executable project. Related portfolio records provide reader-facing writeups. Registering or publishing a code project does not render arbitrary code files. |
| Personal entry | Proposed artifact kind using the shared fields and a notebook source for personal writing. |
| Gallery | Shared identity/publication fields with `path` pointing to a YAML photo collection. Render the photos and captions directly from data; no source notebook is needed. |

Use shared identity/publication fields with typed variants. Each variant supplies its own source references and required data. Portfolio `abstract` replaces the current `summary` as its canonical introductory text; its figure fields supply the rendered image and caption.

### Post plan and article template

Posts use a flexible article template. The rendering layer supplies the title, description, author identity from the profile, date, categories, tags, optional cover image, back link to Posts, and page TOC from the body's headings. Display the title once. The author chooses the article's headings and organization; do not require course-style lab/evidence sections or portfolio-style project sections. Code, outputs, figures, and per-cell display options remain authored notebook content.

Store the post plan in its catalog record as `planned.content`, a nonempty Markdown string containing the intended article outline and starter prose:

```yaml
id: post/attention-notes
kind: post
title: "Notes on causal attention"
description: "An experiment tracing how the causal mask changes attention."
path: content/notebooks/posts/attention-notes.ipynb
visibility: public
lifecycle: planned
categories: [experiments]
tags: [llms, attention, pytorch]
planned:
  content: |
    An outline for investigating causal masking with a small example.

    ## The question
    Explain which tokens each position can attend to.

    ## The experiment
    Compare attention weights with and without the mask.

    ## What to check
    Check that future-token weights are zero after masking.
```

The headings above are examples, not schema requirements. `wt new post <name> --planned-content "..."` creates this planned record without an authored notebook. For longer input, `--plan-file .tmp/<name>.md` reads the entire Markdown body verbatim into `planned.content`; unlike chapter/portfolio plan input, it does not parse prescribed section headings. Collect article metadata through CLI/API/CMS fields without requiring front matter in this input. Follow the shared `.tmp/` path and safe persistence rules.

Support repeated `--tag` inputs at creation, for example `wt new post attention-notes --plan-file .tmp/attention-notes.md --tag attention --tag pytorch`, and add/remove/replace tags through metadata operations and the CMS. Tags are optional free-form labels, not a required taxonomy. Validate a list of nonempty strings, trim surrounding whitespace, and deduplicate case-insensitively while retaining the first display spelling. Existing `categories` retain their values during migration; do not silently reinterpret them as tags.

Display clickable tags on post pages and listing entries, and support tag filtering on the generated Posts page. On desktop, place a “Tags” filter in the right sidebar beside the post listing, showing each tag and its eligible-post count. Selecting a tag filters the listing; provide an “All posts” option to clear the selection and visibly indicate the selected tag. Clicking a tag on an article links to the Posts page with that filter selected. On narrow screens, move the tag controls above the listing. Keep categories and tags distinct if category filtering is also shown. Generate tag options and counts only from entries eligible for the selected build, so draft/private post tags do not leak into the public interface. Tags remain catalog metadata, never front matter the author must add to an editable source notebook. Starting, publishing, and returning to draft preserve them.

The current `posts.qmd` disables Quarto's listing category filter with `listing.categories: false` and has no separate tag sidebar. This design introduces the generated right-hand Tags filter; changing the design document alone does not change the existing page. Retain the post table and its date sorting while adding the sidebar through the frontend listing template.

The planned frontend notebook renders this plan inside the article template, with a generated planned notice. `wt start <post-id>` materializes the same Markdown body as editable cells under `content/notebooks/posts/` and changes lifecycle to draft. It does not inject document front matter or lifecycle notices into the source, invent results, or execute code. Article title/metadata remain managed in the rendering layer; posts do not require the chapter-specific source H1. Refuse to overwrite an existing notebook. After starting, draft/published rendering uses the actual notebook and preserves authored sections, code cells, outputs, and attachments; later planning-data changes do not rewrite it.

The public Posts listing includes public published articles and public planned posts, with planned entries clearly labeled and linked to their plan pages. Draft/private posts are excluded from the live listing and production build. Local preview includes all valid states. Listing summaries use `description` and optional cover metadata, not scraped planning prose or stored code outputs. Keep the current listing presentation and date ordering during migration. `wt draft <post-id>` returns a published post to draft while preserving its body and outputs; its live page/listing disappear on the next successful deployment.

### Portfolio data

The dedicated `content/data/portfolio.yaml` stores an ordered list of portfolio detail records:

```yaml
version: 1
entries:
  - id: portfolio/example
    abstract: "What the project does and why it matters."
    figure_path: content/assets/portfolio/example.png
    figure_caption: "The project's main result or system overview."
    notebook_path: content/notebooks/portfolio/example.ipynb
    project_name: example
    project_source: active
    planned:
      introduction: "The intended project and the problem it addresses."
      what_it_contains: |
        Describe the intended components, their responsibilities, and how they connect.
      scope_notes: "Describe intended scope and limits without claiming completed work."
```

For draft/published entries, `abstract` and `figure_caption` are strings, `figure_path` references an existing image, and `notebook_path` references an existing notebook with authored content under `content/notebooks/`. Both paths are repository-relative. `project_name` is the single folder name of the accompanying project. Require `project_source` to be `active` or `archived`: derive `projects/<project_name>` for active code, or `archive/<archive_date>/projects/<project_name>` for archived code. `archive_date` is a required ISO calendar date for archived references and is forbidden for active references. New entries default to active code; migration sets the source explicitly. Reject path separators and `.`/`..` project names, missing directories, and symlinks escaping the selected project root. When a relation references a registered project, verify that its code directory matches the resolved directory. Do not store a second project path in the portfolio record. Planned records can omit unfinished detail fields or reserve a future notebook path; validate any supplied project reference and do not fabricate files merely to satisfy a planned record.

Historical portfolio entries are valid active writeups about archived work. Label their code reference “Archived source” in the CMS and reader templates, and retain historical scope in their abstracts and notebook prose. This reference does not make the archived code an active catalog project, uv workspace member, or execution/build input. Restoring code to `projects/` is a separate deliberate operation, followed by an explicit reference update.

The catalog supplies the entry's title, visibility, lifecycle, and relations. The portfolio listing/presentation uses its abstract, figure, and caption; the accompanying notebook contains the detailed work. List order in `portfolio.yaml` determines portfolio display order. Generate notebook page headers from the joined record without adding them to its source. The project-folder reference identifies the code associated with the work; it does not cause the generator to copy or render the entire code directory.

On the public Portfolio page, include an entry only when its accompanying notebook's catalog record is public and published. A planned or draft portfolio notebook contributes no abstract, figure, caption, or links to that page, even if its portfolio detail fields are already complete. The portfolio detail and notebook share one catalog lifecycle; do not introduce a separate publication flag for the abstract. Returning a published portfolio notebook to draft removes its listing entry on the next successful deployment. Local preview can show planned/draft entries with their state identified.

Each published portfolio entry shows its abstract, figure, figure caption, a “View notebook” link to the rendered accompanying notebook, and a “Source” or “Archived source” link to its project on GitHub. Generate the source URL from shared frontend repository settings (repository URL and source ref, initially `main`) and the validated resolved project directory, using a Jinja template or equivalent rendering helper. For example, active project name `example` produces `https://github.com/particle1331/watchtower/tree/main/projects/example`; archived `autocode` with `archive_date: 2026-09-30` uses the path `archive/2026-09-30/projects/autocode` under the same repository/ref. Do not store or require an editable source URL per portfolio record. Validate the repository settings and resolved directory, and construct the URL using encoded path components so it points to that exact directory. The notebook link comes from the generated route mapping, not a separately maintained URL.

Use the main-branch Portfolio page shown in the author's screenshot as the presentation reference. Generate a page introduction followed by vertically stacked, bordered project sections. Each section has a project heading, a clearly labeled abstract, a prominent figure and caption, and explicit notebook/source links. Preserve the existing `.portfolio-layout`, `.portfolio-main`, `.portfolio-project`, and `.portfolio-sidebar` styling in the frontend template/assets. On desktop, retain the right-hand “Projects” anchor navigation and “Explore” links; on narrow screens, use the existing responsive layout. Generate section anchors and sidebar links from the same eligible entries in the same authored order, so planned/draft entries do not leak into the public sidebar.

The current working-tree `portfolio_listing` generator writes a title/summary list to `portfolio.qmd` and points the navbar there; it omits the previous project's figures, bordered containers, and portfolio sidebar. Replace that simplified generator with the section template during implementation. The former notebook under `archive/2026-09-30/nb/portfolio/portfolio.ipynb` is a layout reference and migration source, not a source of automatically accepted current project claims. Preserve the approved design while populating it from validated active records.

### Planned portfolio notebook template

Use the main-branch individual project page shown in the author's second screenshot as the planned portfolio notebook reference. It is a full article scaffold containing:

1. Project title and descriptive text from catalog metadata.
2. A “← Portfolio” link to the generated portfolio page.
3. An introductory account of the problem and intended project.
4. A “What it contains” section describing the intended components and design.
5. An “Explore the project” section with the generated project source link and eligible related course/content links.
6. Scope/limitations notes when supplied, and a page TOC for its sections.

Store the portfolio-specific planning prose in the detail record's `planned.introduction`, `planned.what_it_contains`, and optional `planned.scope_notes` Markdown strings. Keep these separate from the listing's `abstract`; a short portfolio abstract is not the full notebook plan. Collect the prose through API/CMS fields or Markdown plan-file input. For a portfolio plan file, use introductory prose followed by “What it contains” and optional scope notes under “Explore the project”; derive its source/related links from metadata rather than requiring hand-maintained URLs. Validate the input according to the portfolio schema instead of requiring chapter-style “Planned content”/“Planned lab and evidence” headings.

Generate the frontend planned notebook from this structured plan and the article template. It remains planned because there is no authored source notebook, even though the generated page contains substantial planning prose. Represent that prose as intended work; copying the visual structure does not authorize copying historical claims of completed implementation. A generic one-sentence placeholder does not satisfy this portfolio template.

`wt start <portfolio-id>` materializes the same introductory prose, section structure, generated navigation/source links, and scope notes as Markdown cells in the editable accompanying notebook, then changes the entry to draft. Keep document front matter and lifecycle presentation in the rendering layer. Use the current validated plan and route mapping without requiring an existing frontend build. After starting, the actual notebook is the body source for draft/published rendering; later plan/template changes do not overwrite authored cells. Preserve the stored plan as intent, and never overwrite an existing notebook. The public Portfolio page still omits the entry until its notebook is public and published.

### Photo data

Keep the gallery's common metadata in the catalog and its ordered photo records in `content/data/photos.yaml`:

```yaml
version: 1
photos:
  - path: content/assets/photos/mountain.jpg
    caption: "A morning in the mountains."
  - path: content/assets/photos/coast.jpg
    caption: "The coast at sunset."
```

Each photo needs only an image path and a caption string. List order determines display order. Generate the gallery page from this data and a frontend template. Individual photos inherit the gallery's publication eligibility; per-photo lifecycle fields are unnecessary in v1.

### Chapter data and title validation

A chapter catalog record contains its full title, short TOC title, parent course, and section membership:

```yaml
id: course/example/01-introduction
kind: chapter
parent: course/example
title: "Language Models and the Experiment Contract"
toc_title: "01. Introduction"
section: foundations
path: content/notebooks/courses/example/01-introduction.ipynb
visibility: public
lifecycle: draft
relations: []
```

When the actual source notebook exists, it contains this H1 in a Markdown cell:

```markdown
# Language Models and the Experiment Contract
```

For an existing actual source notebook, the verifier requires exactly one real Markdown H1 across chapter Markdown cells and checks its displayed text against `title`. Ignore heading-like text in code cells, fenced code, and stored outputs. Parse Markdown headings rather than searching raw notebook JSON. Missing, multiple, or mismatched H1s are actionable validation errors; do not silently rename the notebook or metadata. Source edits and explicit API/CLI title updates must bring the pair into agreement before rendering. A planned chapter without a source file obtains its H1 from the generator; draft/published chapters require the actual source file and authored body content.

`toc_title` controls the course sidebar label and is independent of the full title. It is a required nonempty string; it can equal the full title when that title is already concise. `section` identifies one section within the parent course. Do not add per-chapter numeric ordering fields or repeat TOC titles inside the course record.

### Course contract and TOC

Store each course contract in `content/data/courses/<slug>.yaml`, separate from its authored notebook directory under `content/notebooks/courses/`. Keep the existing contract fields and replace the currently separate authored Quarto sidebar with an ordered `toc`. Each item in `toc` is a section record:

| Section field | Meaning |
| --- | --- |
| `id` | Stable section ID within this course; referenced by a chapter's `section` field. |
| `title` | Displayed section heading; an empty string creates an ungrouped section. |
| `chapters` | Ordered list of chapter IDs belonging to this section. |

The course therefore owns its section definitions and the chapters under each section through `toc`:

```yaml
id: course/example
purpose: "What the course teaches"
audience: "Who it is for"
planned:
  summary: "The intended learning path"
  source: "https://example.org/reference"   # Optional; existing field
  chapters:                              # Optional; normalized existing field
    - chapter_id: course/example/01-introduction
      section: foundations               # Section ID, defined in toc below
      summary: "What this planned chapter covers"
      content: |                         # Markdown body of “Planned content”
        - Explain the model inputs and outputs.
        - Introduce the experiment contract.
      lab_and_evidence: |                # Markdown body of “Planned lab and evidence”
        - Run a deterministic input/output fixture.
        - Record the expected shapes and checked results.
actualized:
  summary: ""                            # Existing; recorded from checked work
overview: course/example/00-overview      # Optional; explicit chapter reference
toc:                                     # Ordered sections and chapter references
  - id: orientation
    title: ""                            # Ungrouped section for the optional overview
    chapters:
      - course/example/00-overview
  - id: foundations                      # Section ID; matches chapter.section
    title: "Foundations"
    chapters:
      - course/example/01-introduction
```

`toc` list order determines section order, and each section's `chapters` list determines chapter order. For example, a chapter with `section: foundations` belongs to the course's `toc` item with `id: foundations`. Section IDs are unique within their course; references use stable chapter IDs rather than filenames or Quarto paths. Resolve chapter labels from `toc_title` and links from the source/render mapping.

Every registered chapter must appear exactly once in its parent course's TOC, including unpublished chapters. Its `section` must match the containing section ID and the `section` in its chapter-plan record, when present. The verifier rejects missing/duplicate chapter references, chapters from another course, nonexistent sections, and inconsistent membership. Creating a chapter records the selected section in its catalog and plan records and adds it to that TOC section. Moving a chapter updates its catalog section, plan section, and course TOC through one validated service operation; reordering changes only the TOC lists.

`planned.chapters` describes instructional intent; `toc` controls navigation. Do not infer `actualized` from file existence, publication, or a successful render. Generate course-context includes from this contract into the Quarto build, while preserving the authored home and overview notebooks.

Each chapter plan is keyed by `chapter_id` in `planned.chapters` and has a required `section` referencing a section ID defined in `toc`. This makes section membership explicit when reading the chapter plan itself. Its `content` and `lab_and_evidence` fields are Markdown strings, separate from the optional concise `summary`. Planned chapters require one matching plan record with nonempty bodies for both planning-content sections. Reject duplicate or foreign chapter references, missing/unknown/mismatched section IDs, and H1 headings inside those bodies so the generated chapter keeps one full-title H1. Keep the plan after a chapter becomes draft/published; it records intent and does not replace the notebook or prove completed work.

### Creating a chapter plan and starting its notebook

Creating a chapter always means saving its plan, registering its catalog entry with `lifecycle: planned`, and adding it to the course TOC. It does not create an authored source notebook. No lifecycle flag is needed for creation. Importing an existing authored notebook is a separate operation that defaults to draft. The proposed chapter creation command must accept the actual plan bodies:

```sh
wt new chapter <course> <name> \
  --title "Causal Self-Attention and Multi-Head Attention" \
  --toc-title "03. Attention" --section attention \
  --planned-content "Explain query/key/value projections, softmax, and causal masking." \
  --planned-lab-and-evidence "Check that future tokens cannot affect earlier outputs."
```

For longer plans, accept `--plan-file .tmp/<name>.md` instead of the two inline body flags. The input file must live under `<repo-root>/.tmp/`; resolve relative paths against the repository root and reject resolved paths outside that directory. This rule applies to post and portfolio plan-file inputs too. These Markdown files are temporary creation inputs; persist their parsed planning data in the entity's canonical YAML record rather than retaining a dependency on the temporary file. The Markdown file for a chapter contains `## Planned content` and `## Planned lab and evidence` with nonempty bodies; parse those sections into the same fields and return actionable errors for missing, repeated, or unsupported sections. This is a plain Markdown input, not YAML the author must maintain. API/CMS and MCP creation use the same typed plan fields. Register the catalog entry, plan, and TOC through one validated, journaled transaction using the recovery protocol below.

The planned frontend notebook contains the chapter H1 and those two sections, plus generated publication metadata/status presentation. Updating the stored plan refreshes that placeholder during preview.

The separately proposed `wt start <id>` supports planned posts, chapters, and portfolio entries. For a chapter, it creates the editable notebook at the reserved `content/notebooks/` path from the current plan. Reuse the same body template as the planned frontend notebook so its H1 and planning sections agree; generate directly from data without requiring or copying an existing frontend build. Omit backend-managed document front matter and status notices from the editable source. Materializing these nonempty planning sections creates authored notebook content, so the operation also changes lifecycle to draft. Preserve identity, visibility, full/TOC titles, section, and planning data; leave `actualized` unchanged. Refuse to overwrite an existing source notebook, including an empty scaffold, and report how to use the existing source instead.

A public course with lifecycle planned or published is eligible for the website; a draft/private course is not. Under an eligible course, public planned chapters appear as metadata-generated pages in the course TOC. A public published chapter uses its actual content notebook and is eligible only under a public published parent course. Draft/private chapters remain excluded from the public build and navigation. The parent condition is a production-selection rule and a precondition for a new chapter publish action, rather than a global invariant on stored chapter lifecycle. A previously published chapter under an ineligible parent remains a valid record with authored content.

Course withdrawal preserves every child's lifecycle, visibility, content, plan, and TOC membership. `wt draft <course-id>` changes only the course to draft and suppresses its home and all descendants from production. Setting the course visibility to private has the same suppression effect without changing its lifecycle. An explicit lifecycle update to planned must satisfy the course's no-authored-content rule; under that public planned course, planned public chapters can appear but published chapters are suppressed. None of these operations cascades metadata changes to children or makes the catalog invalid. Local preview continues to show them, and the CMS identifies children whose public pages are suppressed by their parent.

Restoring the parent to public published makes its already-public published chapters eligible again; restoring a public planned parent restores only planned public chapter placeholders. Show the affected child IDs and resulting eligibility in course action responses and the CMS, including this restoration effect. Publishing a course never changes child lifecycle values, and changing a chapter's lifecycle or visibility affects only that chapter. Apply the same selection rules to pages, navigation, listings, related links, assets, and search so suppressed descendants cannot leak through other generated surfaces. Omit sections with no publicly visible planned/published children without deleting them from the authored TOC. Local preview includes all chapter states in authored order without changing publication state. The course home remains the sidebar root; an optional overview appears immediately after it in the initial ungrouped section.

### Post and portfolio notebook workflow

Posts and portfolio notebooks follow the same lifecycle operations as chapters:

| Operation | Post, chapter, and portfolio behavior |
| --- | --- |
| Create | Save planning data and register a planned entry without an authored notebook. No lifecycle flag is needed. |
| `wt start <id>` | Materialize an editable notebook from the same planning data/template used by its frontend placeholder, and change planned to draft. |
| `wt publish <id>` | Validate authored content, required entity data, and publication eligibility, then set published. |
| `wt draft <id>` | Return published content to draft while preserving its notebook, outputs, metadata, and visibility. |

Extend `wt new post` and add portfolio creation through `wt new portfolio` to use planned creation. Post plans belong to their catalog record; portfolio plans belong to the matching `content/data/portfolio.yaml` detail record. Both can accept planned content via the API/CMS or CLI, including Markdown file input, without manual YAML edits. Chapter-specific section/TOC requirements and required lab/evidence sections do not automatically apply to posts or portfolio pieces.

Starting a portfolio entry writes its accompanying notebook to `notebook_path`; it does not create, copy, or overwrite the code project directory. Starting validates the resulting draft's required abstract, figure, caption, and project reference before committing the notebook and lifecycle change. Missing portfolio details produce actionable errors without leaving a partially started entry. Public planned post/portfolio pages continue to use their metadata-generated frontend notebooks, and drafts use their actual source notebooks locally. Planned/draft portfolio entries have no card on the public Portfolio page. A draft remains excluded from the live site until published and deployed.

### Profile and résumé

Treat the profile at `content/data/profile.yaml` as a singleton structured document, separate from the artifact catalog. Preserve the existing shape and section ordering rather than flattening résumé content into generic posts.

| Field or nested entity | Proposed fields |
| --- | --- |
| Profile | `version` (new), `name`, `contact`, `summary`, `homepage_intro`, `employment`, `early_employment`, `skills`, `education`, optional `projects`. |
| Contact | Existing `phone`, `email`, `github`, `linkedin`. Preserve the current handle/URL conventions during migration. |
| Employment item | Existing `title`, `company`, `dates`, `bullets`, optional `tech`. Same model for early employment. |
| Skill group | Existing `name`, `entries`. |
| Education item | Existing `institution`, `degree`, `dates`; optional `major`, `awards`, `thesis`, `courses`, `description`. |
| Résumé project item | Existing template-supported `title`, `bullets`; proposed optional `artifact_id` to link a registered project or portfolio entry. |

Keep résumé date ranges as display strings initially; the current records include ranges that cannot be represented faithfully by a single start/end pair. Do not add new factual résumé claims during migration. Generate home-page content, web résumé, contact assets, and PDF from this one profile.

Site appearance settings remain frontend configuration. They are distinct from author/content identity and can be changed through backend operations when needed. Migration retains the current theme, navigation categories, and site-wide defaults.

### Runtime build record

A build is an operational record, not a catalog artifact. Track `id`, operation (`preview` or `build`), optional target artifact, status, timestamps, log location, error summary, and output location under ignored `backend/runtime/` storage. Serialize Quarto builds for one workspace. No external queue infrastructure is required initially.

## Service operations and public interfaces

All adapters call the same Python services; the CLI can operate locally without a running HTTP server.

- Content operations: list/filter, inspect context, create planned posts/chapters/portfolio entries, start their editable notebooks, import/register, update metadata, relate artifacts, validate, publish, and return published content to draft through explicit `wt draft <id>`.
- Course operations: create course/chapter/section, create or update a chapter plan including planned content and planned lab/evidence, start an editable notebook from that plan, update chapter full and TOC titles, update the contract, move or reorder chapters and sections, withdraw or restore the parent while preserving child states, and record actualized work explicitly. Planned chapter creation registers data without an authored notebook; starting it materializes its H1 and planning sections as a draft. Explicit full-title changes update metadata and any existing notebook heading through supported notebook operations.
- Profile operations: read and update structured profile sections, validate them, and generate résumé outputs.
- Portfolio/gallery operations: create or update portfolio records across their catalog/detail files, manage photo paths/captions and display order, and validate linked images, notebooks, and project directories. Expose these through the same API/CMS, CLI, and MCP service layer.
- Build operations: preview the working site or a selected artifact in a separate preview workspace, build the production site, and inspect build status/logs.

FastAPI exposes typed request/response models and generated OpenAPI documentation. Read/list/update routes expose entities; action routes expose validation, preview, build, publication, and return-to-draft transitions. MCP tools reuse those schemas and services once the first workflow is stable.

Keep the existing `wt` entry point and notebook cell operations. Change `wt new post` and `wt new chapter`, and add `wt new portfolio`, to create planned entries and accept plan-input options; add `wt start <id>` for their notebooks, `wt draft <id>`, metadata update, build, preview, and local API serving commands; extend publication to all supported page artifacts. These creation behaviors, plan-input options, `start`, and `draft` are proposed changes, not existing behavior. Supply machine-readable JSON output for agent-facing operations, structured validation errors, and useful exit codes.

### Validation, revisions, and recoverable writes

Separate loading from domain validation. Load existing YAML with safe parsing, reject duplicate keys and unsupported versions, and require enough structural information to identify records and apply the requested patch. Parse any relevant notebook through supported notebook operations. Do not require the old state to satisfy lifecycle/content agreement, state-dependent required fields, or all cross-file domain constraints before applying a repair. Apply the requested change to an in-memory candidate, then fully validate the proposed workspace state, including schemas, content, references, and action preconditions, before any source write. A planned notebook containing prose can therefore become draft through metadata update or published through `wt publish` when its final state and publication eligibility pass. No invalid final state is committed; unrelated semantic errors must also be repaired in an explicit batch or separately before the write can succeed. Malformed files that cannot be loaded require manual repair; services preserve them and return an actionable error. Inspection can report existing semantic errors without mutating files. Preview/build always requires full validation of the saved snapshot.

Use optimistic revision checks alongside a workspace advisory lock at `backend/runtime/workspace.lock`. A revision is a SHA-256 digest of exact file bytes, with a distinct token for an absent path. Read responses expose an opaque revision token for the operation's input set: the owning YAML files and all notebooks/assets/contracts whose contents affect the update or its validation. API writes require `If-Match`; CMS forms carry that token; CLI/MCP mutations accept an expected revision and otherwise capture one at the start of their operation. Missing HTTP preconditions return 428; stale revisions return 412 (and an equivalent structured CLI/MCP conflict). Under the exclusive lock, reload and compare every input revision before constructing the candidate, recheck the complete input set before committing, and compare each destination immediately before replacement. Never retry a stale mutation automatically; return affected paths and current revisions while preserving submitted form values. Independent field changes to the same YAML file also conflict, preventing stale whole-file serialization from erasing manual edits.

Persist multi-file mutations, including catalog/course/notebook creation and title changes, through a durable journal under `backend/runtime/transactions/<transaction-id>/`. Before touching tracked files, store a manifest with the operation, expected input revisions, ordered write set, preimage and candidate hashes, and file-existence states, plus exact preimage backups and candidate bytes. Flush these files and their directories with `fsync`. Stage replacement files on the destination filesystem and flush them before installation. After candidate validation and revision rechecks, durably record commit intent; use `os.replace` for each existing destination and flush its parent directory. For creation, use `os.link` from the staged file to the destination on that filesystem: it atomically fails if the destination already exists, so an IDE-created file is never replaced after an absence check. Record progress durably, verify the complete resulting state, and mark committed only after every destination is durable. Preserve notebook outputs, attachments, and metadata in both candidate and backup bytes.

Once commit intent is durable, recovery rolls forward. Every service startup and operation checks pending journals under the lock before reading mutable content; pending transactions also block local preview/build promotion. First verify that inputs outside the write set still match the manifest's expected revisions. For each destination, its candidate hash means that write already completed, while its preimage hash (or expected absence) permits installing the saved candidate. This makes recovery idempotent even when a crash occurs between replacement and progress recording. Any other bytes or changed input dependency mean an external edit: stop recovery, retain the current file and all journal copies, and report the path for explicit reconciliation. Never overwrite a divergent file or blindly restore a backup. A prepared journal without commit intent can be abandoned because no tracked writes have begun. An I/O failure after commit intent returns a pending transaction ID and recovery status, rather than claiming that nothing changed. Keep journals/backups until recovery or reconciliation finishes; clean them only after a committed result is verified.

All cooperating reads, writes, notebook operations, and build-snapshot capture use the same lock and recovery gate. Readers cannot consume a partially committed transaction. Capture build inputs into an immutable staging snapshot while locked, check revisions again after copying, and fully validate that snapshot before rendering; Quarto can then run without holding the content lock. Multi-file atomic visibility applies to these managed readers, not to arbitrary filesystem readers. Git and an IDE can observe intermediate files, so finish recovery before committing or editing affected files.

The lock and revision checks do not provide filesystem compare-and-swap against an uncoordinated IDE save between the last hash check and replacement. Guaranteed conflict rejection applies to participating service writers; detection of overlapping unmanaged saves is best effort. Manual edits remain supported between operations, but pause saves to files being changed by a managed operation, or route those saves through the revision-aware service when strict protection is required. Show the affected paths before CMS operations that rewrite notebooks. Preserve observed divergent bytes and journal versions for reconciliation, and never describe atomic replacement or the workspace lock as an absolute guarantee against concurrent IDE saves.

### Local preview and live publication

- `make preview` generates and serves the local Quarto preview. Include registered renderable entries in all states, including private ones locally. Synthesize planned pages from metadata, even if they have no source notebooks; copy actual content notebooks for draft/published pages. Clearly identify planned/draft entries locally. Preview does not change visibility or lifecycle.
- Watch source notebooks, supporting assets, metadata, and frontend templates. Regenerate affected preview inputs after saves so the author can keep writing in VS Code and see changes without editing generated files or rerunning a manual synchronization command. Never execute cells as part of this refresh.
- `wt publish <id>` validates an entry's public visibility, required authored content, and parent-course eligibility, then sets lifecycle to `published`. An empty planned placeholder cannot be published as authored content. The normal commit/push workflow carries metadata and source content to `main`; the command does not automatically commit or push unrelated working changes.
- `wt draft <id>` returns a published post, chapter, portfolio entry, course, or other supported published content entry to draft. Verify that authored content exists, set lifecycle to `draft`, and preserve content and visibility. It does not create a notebook or start planned content. Drafting a course preserves child states and suppresses the entire course from production; making a course private does the same without changing lifecycle. A drafted page remains visible locally and leaves the website after the change is deployed.
- A push to `main` triggers the existing `.github/workflows/publish.yml`. GitHub Actions installs the required environment, runs validation and the production generator from the committed sources, renders eligible public published content and public planned placeholders, and deploys the result to the existing `gh-pages` target. Do not require the local FastAPI server or local generated files in CI.
- The live website changes only after that workflow succeeds. A local publication flag is eligibility for the next deployment, rather than evidence that deployment has already completed. Returning an entry to draft and pushing the change removes it on the next successful production build.
- Publishing includes the GitHub Actions delivery path in the product workflow. No separate author-facing deployment command or hosting-provider migration is required for v1.

## Generation and validation

1. Resolve pending transactions, capture a consistent saved-input snapshot through the workspace lock/revision protocol, and fully validate the catalog, portfolio detail records, gallery photo data, course contracts, profile, and requested build selection in that snapshot.
2. Create a fresh staging Quarto project for the selected mode. Local preview includes all valid entry states; production builds include eligible public planned placeholders and public published content, while excluding drafts/private entries. Their inputs and outputs remain separate.
3. Choose the render source by lifecycle. For draft/published entries, copy actual notebooks/assets, preserving outputs, attachments, cell IDs, labels, and execution metadata; inject generated document front matter. For planned entries, synthesize new render notebooks from catalog/course YAML and frontend templates, including their title H1 and planned notice; do not copy authored source notebooks or stored outputs. Preserve chapter H1s and suppress their automatic duplicate title block. Mirror asset paths and map generated page locations so internal references remain valid.
4. Generate `_quarto.yml`, listings, portfolio presentations, the photo gallery, course navigation from each course's TOC and chapter short titles, course-context includes, home, and résumé artifacts from the structured data and frontend templates.
5. Run Quarto with execution disabled and capture status and logs. Locally promote only successful output. In GitHub Actions, deploy only a successfully rendered production site; leave the last deployed website available if validation, generation, or rendering fails.

The rendering verifier validates all current YAML inputs in the saved snapshot for syntax, schema, references, and content/lifecycle agreement before generating or rendering any site. This full build validation is distinct from loading an existing state for a repair operation. Reject duplicate YAML keys, incorrect field types, missing fields required for the current state, unsupported schema versions, invalid relationships/course membership, duplicate IDs/routes, unmatched or duplicate portfolio detail IDs, and missing referenced files required by draft/published entries. A chapter with an ineligible parent is valid but suppressed from production according to the course rules above. Planned notebook references may reserve a nonexistent file, but an existing planned scaffold must contain no authored content. Use safe YAML parsing. Return actionable errors with the file path and field/line location where available, such as `content/data/portfolio.yaml: portfolio/example.figure_path: image does not exist` or `course/example/01-introduction: planned entry has notebook body content; explicitly update lifecycle to draft or use wt publish`.

Also validate chapter H1/full-title agreement, required short titles, section membership, TOC completeness/order references, and document front matter accidentally added to headerless source notebooks. Preserve authored cell options and surface malformed cell-option syntax through validation/render errors. Validate actual document YAML front matter rather than treating every Markdown horizontal rule or per-cell option block as a header. Invalid manual edits block the next preview update or production build; preserve the previous successful preview or deployed site. Valid manual changes are picked up by the preview watcher and used by CI without an API import or database synchronization step.

## Implementation sequence and migration

1. **Review and approve the models in this draft.** Existing field names are retained where possible; proposed additions and normalizations are marked above. Finalize these before changing persistent formats.
2. **Build one complete post workflow.** Add typed models, revision-aware YAML repository operations and transaction recovery, shared services with final-state repair validation, FastAPI endpoints, CLI actions, a Jinja/HTMX CMS Posts view with metadata/plan forms and lifecycle actions, and a staging Quarto generator. Prove source notebook → executed outputs → generated copy → `make preview` → publication metadata → committed production build through GitHub Actions. Verify stale-write rejection and crash recovery at this milestone before extending to multi-entity operations.
3. **Extend to all entities.** Add lifecycle/content validation and metadata-generated planned pages, chapter H1/title validation, short titles and sections, ordered course TOCs/context, data-driven portfolio records with accompanying notebooks, project records, notebook-based personal writing, YAML-driven photo galleries, and structured profile/resumé generation. Add MCP tools around the proven services.
4. **Migrate active content.** Produce a dry-run inventory combining the current catalog, course YAML, sidebar, notebook headers, gallery notebook, and résumé. Extract chapter TOC titles, section membership, and ordering from the authored sidebar. Resolve conflicting full titles before adding approved H1s to chapters that currently rely on front matter; preserve existing H1s and report mismatches. Move portfolio-specific records into `content/data/portfolio.yaml`, convert `summary` to `abstract`, migrate existing portfolio QMD bodies into accompanying notebooks through supported conversion operations, and review missing figures/captions before completing migration. Apply the historical project mappings below rather than restoring code or withdrawing entries to satisfy the model. Extract gallery photo references into YAML and review captions and any existing prose before retiring its source notebook. Do not silently discard overlapping metadata or invent images/captions. Preserve IDs, existing public routes, reviewed publication states, teaching content, execution outputs, assets, and all résumé facts.
5. **Switch the workflow.** Move approved structured records into `content/data/`, source notebooks into `content/notebooks/`, authored supporting images/files into `content/assets/`, and frontend templates/site assets into `frontend/`. Replace handwritten publication configuration with generated configuration. Update `wt` discovery and scaffolding paths, add `make preview`, adapt the existing GitHub Actions workflow to the production generator, and update relevant agent skills, `README.md`, and `AGENTS.md`. Keep compatible existing commands where their meaning remains valid and document any changed behavior.

### Historical portfolio migration decision

Keep the three currently public published portfolio entries as historical writeups with explicit archived code references. The current catalog has no active project records and `projects/` has no project directories; their existing code is under `archive/2026-09-30/projects/`. Set `project_source: archived` and `archive_date: "2026-09-30"` for each detail record:

| Portfolio ID | `project_name` | Resolved code directory |
| --- | --- | --- |
| `portfolio/autocode` | `autocode` | `archive/2026-09-30/projects/autocode` |
| `portfolio/change-planner` | `change-planner` | `archive/2026-09-30/projects/change-planner` |
| `portfolio/ml-platform` | `ml-platform` | `archive/2026-09-30/projects/ml-platform` |

These mappings are the chosen migration destination, not unresolved active-project references. Preserve stable IDs/routes and historical descriptions, convert the active QMD bodies to accompanying notebooks, and resolve the required figures/captions through reviewed existing assets or explicitly authored replacements before switching pipelines. Missing presentation assets remain a migration completion blocker; they do not justify changing the project mapping or inventing historical results. Do not restore code, create active project records, or withdraw these entries merely because their implementation is archived. Review any additional claims drawn from archived writeups as historical evidence before including them.

Use supported notebook operations for source normalization and review notebook changes with `wt diff`. If bulk front-matter extraction needs a new notebook operation, implement that operation in Watchtower before applying it to real content. Do not migrate the historical archive into active work or infer current facts from it; the explicit portfolio references above leave archived code in place.

Retain authored per-cell visibility/folding options during migration. Move existing page-layout/TOC choices into the corresponding frontend templates/defaults and report presentation exceptions for review rather than adding an arbitrary Quarto-options mapping to entity records.

Existing notebooks containing prose about future lessons have authored content under the new lifecycle definition, even if their course's `actualized` account is empty. Keep them draft/published according to the reviewed publication choice. If the author chooses to replace such a page with a planned placeholder, preserve that prose in reviewed planning data or migration source material before clearing/retiring the actual notebook; never delete it automatically to make the planned check pass.

The primary checkout contains existing uncommitted changes. Preserve those changes and establish an isolated migration workspace containing the required starting state before restructuring multiple files. Preview the migrated workspace on a separate port.

## Verification and completion

- An author creates or updates, executes, previews, and publishes a notebook while manually editing only notebook content. `make preview` shows both new drafts and updates to existing published notebooks locally before GitHub Actions delivers them to the live site.
- A real notebook imports `watchtower.core` from its installed kernel environment, produces a figure, saves outputs, and renders successfully.
- The FastAPI/Jinja/HTMX CMS parallels the site's Home, Résumé, Portfolio, Posts, Courses, and Personal navigation and content hierarchy. Verify form errors preserve input, applicable lifecycle actions call the shared services, course/portfolio layouts agree with the reader templates, preview/build status remains responsive, and CMS templates are excluded from public generation.
- Verify “Edit in VS Code” resolves the canonical notebook, including portfolio notebook paths and paths containing spaces; it never opens generated copies. “Start and edit” materializes planned content through the shared lifecycle operation before opening it. Simple fields save through CMS forms. The global refresh button uses saved inputs, preserves stored execution outputs and publication state, reports failures, and keeps the last successful preview.
- Generation leaves source notebooks unchanged and preserves outputs, attachments, figure references, relative images, and bibliography resolution.
- Different cells retain their individual code visibility/folding choices in the rendered page; metadata updates and site generation do not overwrite those authored cell options.
- After creation, data updates, preview, and publication, `content/` contains only tracked inputs: data, notebooks, and supporting assets. Runtime records and generated outputs stay outside it.
- Gallery rendering needs only photo path/caption YAML and image files. Portfolio rendering joins catalog metadata with `portfolio.yaml`, including the abstract, figure path/caption, accompanying notebook, project name/source, and archive date when applicable, while preserving the authored display order. Resolve active and archived code directories through the typed reference; verify all three historical mappings with `projects/` empty, without restoring or registering archived code as active work.
- The public Portfolio page includes only public published portfolio notebooks. Verify that planned/draft entries have no abstract/figure/links in the listing and returning a published entry to draft removes its card. Published entries link to the correct rendered notebook and derive their GitHub source URL from shared repository settings and the resolved code directory, without a per-entry URL field. Check “Archived source” labels and exact archive links. Reject invalid project names/source values/archive dates, missing project directories, escaping symlinks, and invalid repository settings.
- Visually compare the generated Portfolio page with the main-branch screenshot: stacked bordered project sections, labeled abstracts, prominent figures/captions, notebook/source links, and a desktop Projects/Explore sidebar. Check a narrow viewport and ensure sidebar anchors include only eligible entries and match their section order.
- Valid manual YAML changes refresh preview and survive subsequent API updates. Malformed YAML, duplicate keys, wrong field types, missing images/notebooks/project directories, and unmatched portfolio IDs produce clear verifier errors before rendering and preserve the last successful output. CLI/API writes receive the same validation as manually edited files.
- Rebuilds deterministically reproduce headers, listings, routes, and course order. Removed/unpublished pages do not survive as stale output.
- Chapter verification catches missing/multiple/mismatched H1s while ignoring code-fence examples. Rendered chapter pages show one full-title H1, and course navigation uses each chapter's `toc_title`.
- Chapter moves keep metadata and TOC section membership consistent; reordered sections/chapters follow the course lists. Reject unknown/duplicate section IDs, duplicate/missing chapter references, and cross-course membership.
- Saves to source notebooks and metadata refresh local preview without changing publication state or re-executing cells.
- A planned entry with no source notebook still generates a navigable placeholder from catalog/course YAML. A valid H1-only scaffold behaves identically. Draft/published pages render from the actual notebook, including its stored outputs; planned generation never copies them.
- Chapter creation always sets lifecycle to planned, accepts both plan sections through inline flags or a Markdown file, and registers its plan/catalog/TOC without creating a source notebook or requiring a lifecycle flag. Verify both input forms persist equivalent data, missing/duplicate sections fail clearly, and the generated page shows both sections. Starting the chapter creates the same H1 and plan bodies as an editable draft without frontend metadata, preserves the stored plan, and refuses existing source files.
- Plan-file inputs for posts, chapters, and portfolio entries resolve under `<repo-root>/.tmp/`; reject paths outside it. After creation, preview and start use the persisted planning data and continue to work if the temporary input file is removed.
- Reject planned notebooks with body text/code/outputs/attachments and draft/published notebooks without content. The title H1 and empty cells alone do not count as content. Creating empty entries defaults to planned; imports with body content default to draft. From a manually edited planned notebook containing prose, verify that metadata update to draft and eligible `wt publish` both repair the disagreement without changing the notebook. Invalid final states and malformed input files still fail without writes; builds remain blocked until repair succeeds.
- `wt draft <id>` preserves existing authored content and returns published entries to draft; `wt publish <id>` requires content. Neither command changes a private entry to public or deletes content. Verify both lifecycle transitions through local preview and production selection.
- Verify the complete create/start/publish/draft workflow for posts and portfolio notebooks as well as chapters. Portfolio start uses its configured accompanying notebook path, preserves project code, and fails without partial writes when required detail fields are missing.
- Post plans accept arbitrary Markdown headings through inline content or a `.tmp/` plan file without requiring chapter/portfolio section names. Verify that planned rendering and start preserve the same outline/prose, the article title appears once, generated metadata stays out of source notebooks, and draft/published rendering retains authored code/outputs. Check planned labels and published links in the Posts listing and exclusion of draft/private posts.
- Verify tag creation/update, whitespace normalization and case-insensitive deduplication, clickable labels, and Posts filtering. Visually check the desktop right-hand Tags sidebar and mobile controls above the listing; verify selected-state presentation, “All posts” reset, and article tag links opening the corresponding filter. Tag options/counts obey build eligibility, preserve existing categories, and survive lifecycle transitions without source notebook edits.
- Compare the generated planned portfolio notebook with the individual project screenshot: title/description, back link, introductory prose, “What it contains,” “Explore the project,” source/related links, optional scope notes, and page TOC. Starting it produces matching editable body cells as a draft; subsequent planning-data changes leave authored cells unchanged. The generated planned body is not treated as an authored source notebook.
- Private/draft content is absent from production staging, output, listings, navigation, and search. Public planned placeholders remain visible in production when their parent is eligible, including the course TOC. Working previews remain separate and can show every valid state locally. Drafting a course or making it private suppresses its home and every child page/link/asset/search entry while preserving child states, source bytes, and TOC membership; full validation still passes. Republish/restore public visibility and verify that public published children reappear, while private/draft children stay excluded. Under a public planned course, planned children appear and published children remain suppressed. New chapter publish actions still require a public published parent. Verify that course action responses and CMS show affected child IDs and eligibility changes.
- GitHub Actions rebuilds from a fresh checkout on `main`, deploys public published content and public planned placeholders to the existing website, and removes drafted/withdrawn entries. Failed builds do not replace the last deployed site.
- Two service clients saving from the same revision produce one success and one stale-write conflict, including edits to different fields in the same YAML file. An IDE save between load and precommit checks causes a conflict without losing its bytes; an IDE-created notebook at a reserved path defeats start's no-overwrite creation. Test missing/stale API preconditions and equivalent CLI/MCP/CMS errors. Document the remaining uncoordinated-save race without claiming absolute protection.
- Inject failure before commit intent, after each file replacement, and between replacement and journal progress recording for catalog/course/notebook transactions. Recovery is idempotent and either reaches the fully validated candidate or blocks on an external edit while preserving all versions. Managed reads/builds never consume partial state; pending or conflicted journals block mutations and preview promotion. Verify durable preimages/candidates and absence checks, and that recovery never blindly rolls back external changes.
- A failing Quarto process exposes an actionable error and leaves the last successful site intact.
- API, CLI, and MCP produce equivalent domain results and validation errors.
- Migration preserves existing IDs/routes and résumé fields, resolves reported conflicts, and renders representative pages from every content type plus the résumé PDF.
- Run the repository's `make lint`, `make typecheck`, and `make test` for the implementation, along with a real Quarto render and visual checks of the affected site navigation/pages.

The first completed milestone is the one-post workflow. The system migration is complete only when all existing active entity types use the new pipeline, everyday content work requires no manual publication YAML edits, and authors can optionally edit `content/data/` directly with render-time verification.
