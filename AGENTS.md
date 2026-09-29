# Watchtower — agent rules

## Architecture
This repo is a personal system with three tiers of content with DIFFERENT visibility:
- `nb/posts/*.ipynb` — all published writing, from focused notes to long-form articles
- `nb/courses/` — full course notes
- `nb/photos/photos.ipynb` — personal photo gallery
- `projects/<name>/` — code projects (each a uv workspace member)

## Agent skills
- Shared skills live in `skills/<name>/SKILL.md`, which is the canonical source.
- `.codex/skills/` and `.opencode/skills/` contain relative symlinks to the
  shared skills. Edit the canonical files under `skills/`, not the symlink
  paths.
- When creating a shared skill, add it under `skills/<name>/` with a
  `SKILL.md`, then run `make setup-skills`. The command creates or validates
  the corresponding symlinks in both tool directories. Do not duplicate skill
  files or create the symlinks manually.
- Run `make setup-skills` to create missing links or validate an existing
  checkout. `make bootstrap` runs it automatically before `uv sync`.

Canonical source files are Jupyter notebooks (`.ipynb`). Authors edit them
in JupyterLab (running cells, getting outputs); Quarto renders the notebooks
to the website using **inline outputs, no re-execution** — so heavy compute
done once in JupyterLab (or imported from Colab/Kaggle) is preserved as-is.

## Knowledge base
- The canonical knowledge base is `nb/posts/*.ipynb` and `nb/courses/**/*.ipynb`.
- Raw `.ipynb` JSON is noisy — do NOT `grep`/`read` it directly. Use the
  `wt` wrappers below, which expose cell sources as plain markdown.
- `.ipynb_checkpoints/` is excluded from listings and resolution.

## Environment
- All `wt` commands require the venv. Use `.venv/bin/wt` (from repo root)
  or activate the venv first. Never run bare `wt`.
- Scratch/temp files belong in `ROOT_PATH / ".tmp"` (repo root, gitignored) — not the
  system `/tmp`. Use it for any intermediate artifacts, drafts, or scratch
  docs you'd otherwise write outside the repo.

## Navigation
- Run `wt map` first to get structured repo layout as JSON.
- Run `wt ls posts|courses` for notebook listings, or `wt ls projects` for
  project directories.
- `<name>` for notebook commands (`cat`, `output`, `diff`, `edit-cell`,
  `append-cell`, `insert-cell`, `remove-cell`, `clear-outputs`, `tag`, `count`,
  `run`) resolves as: bare stem (`001-testnote`),
  tier-prefixed stem (`nb/posts/001-example`), or full path (`nb/posts/001-example.ipynb`).

## Reading notebooks
- `wt cat <name>` — print all cells as markdown (`> cell N [code|markdown] ...` headers; `>` marks tool meta, not notebook content).
- `wt cat <name> --index N` — just cell N.
- `wt cat <name> --tag foo` — cells with Jupyter tag `foo` (may be multiple).
- `wt cat <name> --label fig-x` — cells whose leading Quarto options contain
  `#| label: fig-x`.
- `wt cat <name> --index N --offset 500 --limit 1000` — slice chars 500:1500
  of cell N's source. Header carries `src[start:end] of total` so you can
  chain reads without re-paying for bytes you've already seen.
- `wt cat <name> --index N --with-outputs` — also print the cell's outputs,
  each with its own `>> cell N output K [stream stdout|error ...]` header.
  Use `--out-offset` / `--out-limit` to slice each output's body the same
  way `--offset` / `--limit` slice the source. Image/base64 payloads are
  summarized (`[image/png, N chars — not shown]`), not dumped.
- `wt output <name> --index N` — inspect stored outputs from one code cell;
  text/errors are printed and image payloads are decoded to `ROOT_PATH / ".tmp"`.
  Use `--output K` for one output or `--save-dir DIR` for another directory.
- `wt cat <name> --index N --context 3` — render cells N-3..N+3; context
  cells are marked `context` in their header. The standard way to see a cell
  with its surroundings before editing.
- Existing course solutions are collected in
  `nb/courses/solutions.qmd`; `wt cat` shows the stored notebook cell source.

## Agent editing workflow (any coding agent)

The notebook ops are the agent contract for every coding agent (Copilot,
opencode, Claude Code, ...). The loop:

1. `wt ls <tier>` / `wt map` — orient.
2. `wt find <query>` — locate the text; it prints `path [cell N]: line`.
3. `wt cat <path> --index N --context 3` — read the cell with its
   surroundings (or `--tag`/`--label` when the cell has stable tags).
4. `wt edit-cell <path> --index N --content "..."` — edit (or
   insert/append/remove per the rules below).
5. `wt diff <path>` — review the change as a markdown diff vs HEAD (never
   read `.ipynb` JSON directly; `wt diff` renders both sides for you).
6. `wt run <path> --index N` — re-execute the edited cell with prior notebook
   state available in a fresh kernel.

## Editing notebooks
- Cell writes (`edit-cell`, `append-cell`, `insert-cell`) are hard-capped at
  20k chars per source — break large content into smaller cells.
- **Locator-based cell mutations take exactly one locator.** `edit-cell` and `tag` accept
  `--index N`, `--tag foo`, or `--label foo`; `insert-cell` accepts one of
  `--after N`, `--before N`, `--tag foo`, or `--label foo`; `remove-cell`
  accepts `--index N`, `--tag foo`, or `--label foo`.
  `edit-cell`, `insert-cell` tag/label locators, and `tag` require one matched
  cell. `remove-cell` deletes every matching cell, including multiple tag or
  label matches. Prefer stable tags or Quarto labels over positional indices
  when possible. To target a cell without a stable locator, run `wt cat` and
  read the `> cell N ...` index from its header.
- **Indices shift after insert/remove.** Any `insert-cell` or `remove-cell`
  bumps the index of every cell that comes after the anchor by ±1. So:
  - When planning multiple mutations, do them right-to-left (highest index
    first) so earlier indices stay valid. `edit-cell` does NOT shift
    anything — it only rewrites the source of cell N.
  - After an insert/remove, do NOT reuse indices you resolved before that
    mutation — re-run `wt cat` (or `wt count`) to get fresh indices.
- `wt edit-cell <name> --index N | --tag foo | --label foo [--content "..."]`
  — replace a cell's source (outputs + metadata preserved). If `--content` is
  omitted, source is read from stdin, which is useful for multi-line content.
  stdin is decoded as UTF-8.
- `wt append-cell <name> --type md|code [--content "..."]` — push to end;
  the default type is Markdown.
- `wt insert-cell <name> --after N | --before N | --tag foo | --label foo
  --type md|code [--content "..."]` — insert a new cell below/above the
  located cell; `--tag`/`--label` insert *below* the matched cell.
- `wt remove-cell <name> --index N | --tag foo | --label foo` — delete every
  matching cell. Resolve ranges with `wt cat --index N:M`, then remove from
  highest to lowest if you need to delete a selected range by index.
- `wt tag <name> --index N | --tag foo | --label foo [--add foo] [--remove bar]`
  — manage Jupyter cell tags on one matched cell. `--add` and `--remove` may
  be repeated; with neither, prints the cell's current tags.
- `wt clear-outputs <name> [--index N | --tag foo | --label foo | --from N]`
  — clear stored outputs from matching code cells. With no locator, all code
  cells are cleared; `--from N` clears code cells from `N` to the end; Markdown
  cells are skipped.

## Executing notebooks
- `wt kernels` — list installed Jupyter kernel names and languages; use the
  `name` column with `wt run --kernel`.
- When `--kernel` is omitted, `wt run` uses the notebook's
  `kernelspec.name`, falling back to `python3` when no kernelspec is stored.
- `wt run <name> [--index N] [--timeout S] [--kernel K]` — execute code
  cells in-place via nbclient, writing outputs back to the `.ipynb`. Quarto
  renders inline outputs without re-running; `wt run` is the explicit
  re-execution path. The default timeout is 300 seconds per cell. Execution is
  JupyterLab-like: a cell error is stored as an inline output and execution
  continues; exit code is 1 if any cell errored (agents can use it to verify
  notebook code).
- `--index N` runs the notebook prefix through that cell in a *fresh* kernel,
  so imports and variables from earlier cells are available. Only the target
  cell's outputs are written back.
- Indexed runs replay that prefix on every CLI invocation. This is deterministic
  but can be expensive for heavy earlier cells; state is not reused between
  separate `wt run` calls.
- A notebook with no code cells prints "no code cells to run" and never
  launches a kernel.

## Importing notebooks
- `wt import <path.ipynb> posts [<name>]` — copy a notebook produced
  elsewhere (Colab, Kaggle, a teammate) into a tier dir, preserving inline
  outputs. Quarto will render with those outputs, no re-execution.
- `wt import <path.ipynb> courses <course> [<chapter>] [--section <name>]` —
  import as a chapter of an existing course: copies to
  `nb/courses/<course>/<chapter>.ipynb` and registers it in the course's sidebar in
  `_quarto.yml` (last section by default, or the section named by `--section`).
- `wt import` preserves stored outputs, adds a default `python3` kernelspec if
  needed, and strips a leading `# Title` heading that duplicates frontmatter
  `title` (Quarto renders that title as the page's H1). A bare `# Title` with
  no frontmatter is kept as-is.

## Rendering
- `make docs [PORT=<port>]` rebuilds résumé pages and PDF from
  `assets/resume.yaml`, then serves the site on the chosen local port (default
  :4200; publishing is handled by the `publish.yml` GitHub Action on push to
  `main`). The command prints the PDF path and preview URL before blocking.
- `make resume` rebuilds generated home, résumé, posts, contact, LaTeX, and PDF
  artifacts from `assets/resume.yaml` and published post metadata.
- `make render NOTEBOOK=nb/posts/<name>.ipynb` renders one notebook to PDF
  under its source directory's `pdf/` folder using inline outputs.
- `make project NAME=<name>` scaffolds a uv workspace project under
  `projects/<name>`.
- `_quarto.yml` sets `execute.enabled: false`. Quarto never runs your
  code at render time — it uses whatever outputs already live in the `.ipynb`.

## Implementation tradeoffs
Pick the mode from the directory you're writing into.

**Tooling code (`src/`, `projects/`).** Write the simplest correct thing.
This code is mostly I/O-bound notebook/file manipulation, so readability
almost always beats CPU micro-optimization. Reach for a faster but more
complex algorithm only when the input can realistically get large enough to
matter — and when you do, say so in one line. A slightly slower but obviously
correct implementation beats a clever one that needs a comment to explain why
it works. Common traps to avoid regardless: `x in some_list` inside a loop
(use a `set`), repeated string `+=` in a loop (use `join`), and building
throwaway intermediate lists you iterate once (use a generator).

**Post & course content (`nb/posts/`, `nb/courses/`).** Here the
algorithm is often the lesson, so the priorities differ. Implement the
complexity you claim: code in a note about an O(n log n) method must actually
be that — a stray O(n²) is a teaching bug even if the outputs are right. State
the complexity when it's the point. Prefer the clearest form that still
teaches the idea, and note that showing a naive version first and then the
optimized one is a feature, not a smell — keep both when the contrast is the
lesson.

## General
- Before commit there is no hook; run `make lint` and `make typecheck` if
  you changed Python under `src/` or `projects/`.
- **Doc-drift check before committing:** any change to the `wt` CLI's
  commands, options, or output format MUST be reflected in both
  `AGENTS.md` (agent-facing) and `README.md` (user-facing). Stale docs
  are worse than no docs — `wt` CLI reference is one place agents/users
  learn the surface area without reading source code.
- Do NOT commit secret values — secrets live in the OS keyring via
  `wt vault` (see below).
- Style: avoid excessive em-dash (—) usage. Use em-dashes only when
  necessary within a paragraph (e.g., one parenthetical aside); prefer
  commas, colons, or restructured sentences otherwise.

## Tooling gaps
If you hit a rough edge the `wt` CLI doesn't cover (a missing command, a parsing error, a
locator that won't resolve, a cell operation that would clobber outputs, a
render path that breaks) — do NOT silently work around it with raw `.ipynb`
JSON or ad-hoc shell scripts. **Open an issue** with
`gh issue create -R particle1331/watchtower -t "<title>" -b "<body>"`
covering the gap, the command you ran, and what you expected.

## Per-project rules
If working inside `projects/<name>/`, also read `projects/<name>/AGENTS.md`
if present (project-specific rules stack on top of these).

## Vault (secrets)
- Secrets live in the OS keyring, accessed via `wt vault`. NEVER commit secret values.
- `wt vault export` emits export lines — projects use it via
  `eval "$(wt vault export)"` or `from watchtower.vault import get_secret`.

## Course building and exercises

Course scaffolding, index/sidebar/chapter conventions, and exercise authoring
live in `skills/course-builder/SKILL.md`. Load it whenever creating or
extending a course under `nb/courses/`. Write new exercise prompts with the
ordinary `wt` cell commands. Assess answers when requested; new exercises do
not require stored solutions. Existing solutions are collected in the public
page `nb/courses/solutions.qmd`.

For a new course or a multi-file course revision, use a dedicated Git worktree
when the environment permits it so the user's primary checkout and site
preview remain usable. Run the isolated preview with `make docs PORT=4300` (or another unused port) and include the exact URL in progress
updates and the final handoff. A separate port without a separate worktree
does not isolate source files or Quarto's `_site` output. Never reset, clean, or
overwrite a dirty primary checkout to create the worktree.

## CLI command reference (for the agent)

The `wt` CLI is limited to notebook/content workflows and the `vault` secret
tool. Site previews, PDF rendering, résumé generation, and project creation
are Make tasks, not `wt` subcommands. `wt --help` and each subcommand's
`--help` output are the authoritative syntax.

- `wt kernels` — list installed Jupyter kernel names and languages; use the
  `name` column with `wt run --kernel`.
- `wt new` — command group for `post`, `course`, `chapter`, and `section`
  scaffolding. `wt new course` requires `<name> <title>`; chapter creation and
  course imports register entries in `_quarto.yml`.
- `wt new post <name> [--title <title>]` — scaffold a dated post notebook; <title> defaults to a titleized version of <name>
- `wt new course <name> <title>` — scaffold `nb/courses/<name>/` with an index notebook and first lesson stub; <title> becomes the display title in the index frontmatter
- `wt new chapter <course> <name> [--title <title>] [--section <name>]` — scaffold a course chapter (notebook) and register it in the course's sidebar in `_quarto.yml`; <title> defaults to a placeholder derived from <name> (sidebar text and notebook frontmatter are independent surfaces — edit either or both after scaffolding)
- `wt new section <course> <name>` — add a section header to a course's sidebar in `_quarto.yml`
- `wt map` — JSON repo structure (orientation)
- `wt ls posts|courses|projects` — list notebook sources or project directories
- `wt find <query>` — grep across `.ipynb` cell sources
- `wt count <name>` — cell count (plan ranges before `--index N:M`)
- `wt cat <name> [--index N|N:M | --tag foo | --label foo] [--offset O --limit L]
  [--with-outputs] [--out-offset O --out-limit L] [--context N]`
  — read notebook cells as markdown. `--index` accepts a single 0-based index
  or a Python-style slice (`N:M`, `:M`, `N:`) to scan a range of cells quickly.
  Default per-cell limit is 4096 chars (`--limit 0` = unlimited).
  `--context N` also renders the N cells around each match (marked
  `context`). A tag may match multiple cells; image/base64 output payloads are
  summarized rather than dumped.
- `wt output <name> --index N [--output K] [--save-dir DIR]` — print text and
  error outputs from one cell and save decoded image outputs for visual
  inspection. The default image directory is `ROOT_PATH / ".tmp"`.
- `wt edit-cell <name> --index N | --tag foo | --label foo [--content X]`
  — replace a cell's source (outputs + metadata preserved); locator must match one cell
- `wt append-cell <name> --type md|code [--content X]`
  — append a new cell
- `wt insert-cell <name> --after N | --before N | --tag foo | --label foo
  --type md|code [--content X]` — insert a new cell; `--tag`/`--label` insert
  below the matched cell (must be unique)
- `wt remove-cell <name> --index N | --tag foo | --label foo`
  — delete every matching cell; delete selected index ranges from highest to
  lowest when planning multiple removals
- `wt tag <name> --index N | --tag foo | --label foo [--add foo] [--remove bar]`
  — manage cell tags (unique match required)
- `wt clear-outputs <name> [--index N | --tag foo | --label foo | --from N]`
  — clear stored outputs of code cells (markdown cells skipped). `--from N`
  clears every code cell from index N to the end (handy for a trailing
  section like a problem set); with no locator, all code cells are cleared.
- `wt diff <name> [--base REF]` — markdown diff of a notebook vs a git ref
  (default HEAD): both sides rendered like `wt cat` (JSON-stripped, no
  outputs), so the diff shows stored cell source, not `.ipynb` JSON.
  Added/removed lines are highlighted in interactive terminals; output stays
  plain when piped, redirected, or `NO_COLOR` is set. An unchanged notebook
  reports `no changes`.
- `wt run <name> [--index N] [--timeout S] [--kernel K]` — execute code cells
  in-place via nbclient, writing outputs back; exit code 1 if any cell errored.
  `--index N` runs the notebook prefix through that cell in a fresh kernel;
  prior state is available and only the target cell's outputs are written back.
- `wt import <path.ipynb> posts [<name>]` — import an external notebook
  (Colab/Kaggle) into a flat tier
- `wt import <path.ipynb> courses <course> [<chapter>] [--section <name>]`
  — import as a chapter of an existing course (copies into the course dir and
  registers in the course's sidebar)

- `wt vault set <key> <value>` — store a secret in the OS keyring
- `wt vault get <key>` / `wt vault rm <key>` — retrieve/delete a secret
- `wt vault ls` — list stored keys
- `wt vault export` — emit shell export statements

`wt vault get` prints a secret value, `ls` prints keys only, and `export`
emits shell-safe `export KEY=value` lines. Use `eval "$(.venv/bin/wt vault
export)"` when loading the values into the current shell.

## Repository tasks (Make)

`wt` focuses on notebook work and retains the core `vault` tool. Run these tasks from the repository root; Make uses
`.venv/bin/python` automatically. Implement repository tasks as standalone
scripts under `scripts/`, with no imports from `watchtower`; keep notebook
operations and core tools in `src/watchtower/`. `make` or `make help` lists
the workflows.

- `make project NAME=<name>` — scaffold a uv workspace project
- `make render NOTEBOOK=<path.ipynb>` — render a notebook to PDF in its
  source directory’s `pdf/` folder
- `make resume` — render `assets/resume.yaml` plus published post metadata
  -> `assets/resume.tex`, `index.qmd`, `resume.qmd`, `posts.qmd`, and
  `assets/contact.js` via Jinja2 templates, then `pdflatex`
  -> `assets/resume.pdf` (builds in a
  temp dir). The YAML is the single source; edit it, never the generated
  `.tex`/`.qmd`.
- `make docs [PORT=<port>]` — rebuild résumé pages and PDF from `assets/resume.yaml`, then serve the site (blocking;
  default :4200)
- `make help` — print the repository workflow summary
- `make bootstrap` — set up skills and run `uv sync`
- `make setup-skills` — create and validate skill symlinks
- `make test` — run `pytest`
- `make lint` — run `ruff check .`
- `make typecheck` — run `pyright`
- `make review` — run lint, typecheck, tests, and print the diff summary
