# Watchtower

A workspace for knowledge work and its supporting tools. Published pages are selected from the active catalog alongside the résumé and personal photo gallery. Earlier posts, courses, portfolio pieces, and code projects are preserved in [`archive/2026-09-30/`](archive/2026-09-30/README.md) as source material for new work.

## Knowledge content

The active registry is [`knowledge/catalog.yaml`](knowledge/catalog.yaml). Register logical works: a post, course, chapter, portfolio piece, or project. Each record has a stable ID, kind, title, path, visibility (`public` or `private`), lifecycle (`planned`, `draft`, or `published`), and relationship IDs. Images, tests, and individual code files belong to their parent work. Operational sources such as `scripts/`, `src/watchtower/`, and `assets/resume.yaml` are outside this catalog.

A course has three distinct layers:

| Source | Purpose |
| --- | --- |
| `nb/courses/<slug>/course.yaml` | Concise shared contract: purpose, audience, **planned** path, and separately recorded **actualized** work. |
| `nb/courses/<slug>/index.ipynb` | Learner-facing course home or README: orientation, navigation, prerequisites, and practical guidance. |
| `nb/courses/<slug>/00-overview.ipynb` (optional) | Deeper technical design and whole-course explanation. |

The home embeds a short generated rendering of the YAML contract. `make knowledge`, `make docs`, and `make render` refresh that include. Quarto uses stored notebook outputs and does not execute cells while rendering. The planned section states intent; the actualized section must be updated from evidence, never inferred from file existence.
Only catalog entries marked both `public` and `published` enter the site. Publishing a course renders its home and creates its grid card; chapters render independently when they are published under a published course. The course sidebar lists only its published chapters. `knowledge/sidebar.yaml` stores the authored course outline; synchronization derives the published sidebar in `_quarto.yml` without discarding draft entries. `make knowledge` validates the catalog and synchronizes Quarto's render list and navigation; drafts and private works stay out of the public site.

## `wt` navigation

Use `.venv/bin/wt` from the repository root. `wt map` is the starting point: it groups active courses by home, optional overview, and chapter. Discovery commands read the catalog, so an unregistered file is not silently treated as active.

| Command | Result |
| --- | --- |
| `wt map` | Active artifact map as JSON. |
| `wt ls posts\|courses\|portfolio\|projects` | Paths registered in one tier. |
| `wt context <id-or-path>` | Catalog record, course YAML when applicable, and labeled reading paths. It does not load sibling chapters. |
| `wt find <query>` | Search registered active sources; notebooks report cell indices, text files report line numbers. |
| `wt validate` | Check catalog records, paths, course contracts, home includes, relations, and unregistered active content. |
| `wt register <kind> <id> <path> <title>` | Register an existing work, especially a portfolio page or project. |
| `wt publish <course-or-chapter-id>` | Publish one public course or chapter and synchronize its card, render path, and course navigation. Publishing a course leaves its chapters unchanged. |
| `wt render-context`, `wt sync-site` | Refresh course-home includes and Quarto publication paths from the catalog. |
| `wt map --archive`, `wt ls <tier> --archive`, `wt find <query> --archive` | Explicitly inspect the repository-only archive. |
| `wt cat <notebook>` | Read notebook cell sources as Markdown, without raw `.ipynb` JSON. An archived notebook can be read by its full path. |

`wt cat --context N` shows **neighboring cells in that one notebook**. For course-level context, use `wt context`, then read the course home, overview when present, and target chapter as needed. Read adjacent chapter openings only when handoffs matter; `wt` does not read every notebook in a course automatically.

Notebook IDs such as `post/example` or `course/example/01-introduction` work with notebook read and edit commands. Existing notebook path forms still work.

## Creating and editing

```text
.venv/bin/wt new post example --title "Example"
.venv/bin/wt new course example "Example Course"
.venv/bin/wt new chapter example 02-next --title "Next Step"
.venv/bin/wt new section example "Part II"
.venv/bin/wt import external.ipynb posts example
.venv/bin/wt import external.ipynb courses example 03-imported
```

Scaffolding and import register the new work in the catalog. A new course also creates `course.yaml`, its home notebook and generated include, a first chapter, and sidebar entries. For project or portfolio works created outside these notebook commands, add a catalog entry and run `wt validate`.
Use `wt register portfolio <id> <path> <title>` for a portfolio page; `make project` registers its new project automatically.
Use `.venv/bin/wt publish course/<slug>` to publish a course home and generate its Courses card. Publish a chapter separately with `.venv/bin/wt publish course/<slug>/<chapter>`; its parent course must already be published.

For notebook changes, use `wt find`, `wt cat --index N --context K`, then `wt edit-cell`, `append-cell`, `insert-cell`, or `remove-cell`. Review with `wt diff`; run edited code with `wt run` and inspect stored output with `wt output`. `wt cat` defaults to a 4096-character source limit per cell; `--limit 0` removes it. Cell writes are capped at 20,000 source characters. `wt --help` and subcommand help give full syntax.

## Repository tasks

| Command | Purpose |
| --- | --- |
| `make bootstrap` | Set up shared skill links and sync the uv environment. |
| `make knowledge` | Validate the catalog, regenerate course-home includes, and sync public published site pages. |
| `make resume` | Regenerate home, résumé, and PDF from `assets/resume.yaml`. |
| `make docs PORT=4300` | Refresh generated context and résumé artifacts, then preview the site. |
| `make render NOTEBOOK=<path>` | Refresh context and render one notebook to PDF. |
| `make project NAME=<slug>` | Create and register a uv workspace project. |
| `make lint`, `make typecheck`, `make test` | Check active tooling. Archived code is excluded from lint and type checks. |

Do not edit generated résumé pages or raw notebook JSON. Use the `.venv/bin/wt vault` commands for local secrets; never commit secret values. Shared skills live under `skills/`, with links set up by `make setup-skills`.
