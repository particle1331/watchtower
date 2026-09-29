# watchtower ⛫

A personal system for posts, projects, and course notes.

This repository supports lifelong learning while also serving as a place to
compile and document interesting projects into a portfolio. Jupyter
notebooks are rendered into a website with Quarto and published automatically
through CI, so the published material is backed by code executed end to end.
It also provides infrastructure for coding agents, including a
notebook-aware CLI and shared skills synchronized across agent frameworks.

This repository takes its name from the [Watchtower structure in *Battle Realms*](https://battlerealms.fandom.com/wiki/Watchtower).

## Tiers

| Tier      | Where                       | Effort | Audience | Listing             |
|-----------|-----------------------------|--------|----------|---------------------|
| Home      | `index.qmd`                 | —      | public   | site landing page |
| Résumé    | `resume.qmd`                | —      | public   | full web résumé and PDF link |
| Posts     | `nb/posts/*.ipynb`          | mixed  | public   | `posts.qmd` |
| Portfolio | `nb/portfolio/`            | high   | public   | project sections and full pages |
| Courses   | `nb/courses/**/*.ipynb`        | mid    | you      | `nb/courses/index.ipynb`  |
| Personal  | `nb/photos/photos.ipynb`       | —      | public   | personal photos           |

Site content is primarily stored as Jupyter notebooks (`.ipynb`); the generated
home and résumé pages are `index.qmd` and `resume.qmd`. `posts.qmd` lists the
post notebooks. Agents read notebook cell sources as plain markdown through
the notebook-aware `wt` CLI; they never need to see the raw JSON.

## Quick start

```bash
make bootstrap                       # setup shared skills + uv sync (creates .venv)
source .venv/bin/activate             # or use .venv/bin/wt explicitly
wt new post my-post                   # nb/posts/my-post.ipynb
wt new post my-post -t "My Post"     # custom display title
wt ls posts                           # list all post notebooks
wt ls projects                        # list project directories
wt new course llm "Large Language Models"  # nb/courses/llm/ (index + first lesson)
wt new chapter my-course 02-bar       # nb/courses/my-course/02-bar.ipynb + register in sidebar
wt new section my-course "My Section" # add section header to course sidebar
make project NAME=my-code-project       # uv init projects/my-code-project

make render NOTEBOOK=nb/posts/my-post.ipynb  # render notebook PDF
make resume                            # render home, résumé, posts, contact script, LaTeX, and PDF
make docs                              # rebuild résumé from YAML, serve site on :4200
make docs PORT=4300                  # rebuild résumé, serve on :4300
```

`wt` handles notebook and content operations. Site previews, PDF rendering,
résumé generation, and project scaffolding are repository-level `make` tasks.

The site is published automatically to `gh-pages` on push to `main` via
`.github/workflows/publish.yml`.

## Agent skills

Shared Codex and OpenCode skills live under `skills/`. The corresponding
`.codex/skills/` and `.opencode/skills/` entries are relative symlinks into
that directory, so each skill has one canonical source file.

After cloning, run `make bootstrap`. It installs the Python environment and
repairs or validates the skill symlinks. Edit the files under `skills/`, not
the tool-specific symlink paths.

To add a shared skill, create `skills/<name>/SKILL.md` and run
`make setup-skills`. The command registers it in both tool directories; do not
duplicate the skill file or create the symlinks manually.

## Editing workflow

Open the `.ipynb` in JupyterLab, run cells, save. Inline outputs are
preserved on render — Quarto never re-runs your code (see `execute.enabled:
false` in `_quarto.yml`).

For agent reads/edits, never touch the raw `.ipynb` JSON. Use `wt cat`,
`wt edit-cell`, etc. (see `AGENTS.md` for the full reference).

To re-run code without opening JupyterLab, use `wt run <name>`: it executes
the notebook in place and saves the outputs, which Quarto then renders as-is.
To see the names accepted by `--kernel`, run `wt kernels`; use the `name`
column, for example `wt run <name> --kernel python3`.
When `--kernel` is omitted, `wt run` uses the notebook's `kernelspec.name`
and falls back to `python3` if the notebook has no kernelspec.

To inspect a stored result from one code cell, use `wt output <name> --index N`.
Text and errors are printed; image outputs are decoded into `ROOT_PATH / ".tmp"` so a
vision-capable agent can inspect plots without parsing notebook JSON.

## Importing notebooks from elsewhere

```bash
wt import ~/Downloads/foo.ipynb posts my-post                  # copy + normalize into nb/posts/
wt import ~/Downloads/foo.ipynb courses llm                    # import as a chapter of llm/ + register in sidebar
wt import ~/Downloads/foo.ipynb courses llm 02-bar             # chapter stem override
wt import ~/Downloads/foo.ipynb courses llm 02-bar -s "Setup"  # into a specific section
```

Inline outputs are preserved — Colab/Kaggle runs ship with the file, so a
heavy-training notebook renders with its figures intact, no re-execution.
A leading `# Title` heading that duplicates the frontmatter `title` is
stripped (Quarto renders that title as the H1), so imported notebooks get one
H1, not two.

## Secrets

```bash
wt vault set OPENAI_API_KEY <value>
wt vault rm OPENAI_API_KEY
wt vault ls
eval "$(wt vault export)"        # export lines for current shell
```

Stored in the OS keyring; never committed. Projects read them via:

```python
from watchtower.vault import get_secret
get_secret("OPENAI_API_KEY")
```

## Layout

```
index.qmd                 # site home page (generated by make resume)
resume.qmd                # full web résumé (generated by make resume)
posts.qmd                 # published post listing (generated by make resume)
nb/
  posts/
    *.ipynb                # all individual posts in one flat directory
    img/                   # images used by posts
  portfolio/
    portfolio.ipynb         # project abstracts and links
    *.qmd                   # full project pages
  photos/
    photos.ipynb            # personal gallery
_quarto.yml               # publishes all content tiers (execute.enabled: false)
assets/
  styles.css              # site styling
  img/                    # shared images
  resume.yaml             # canonical résumé source (single source of truth)
  resume.tex.j2           # Jinja2 template -> moderncv LaTeX (PDF)
  index.qmd.j2            # Jinja2 template -> site home page (QMD)
  resume.qmd.j2           # Jinja2 template -> full web résumé (QMD)
  posts.qmd.j2            # Jinja2 template -> combined post listing (QMD)
  contact.js.j2           # Jinja2 template -> copyable contact details
  resume.pdf              # built by `make resume` (served as download link)
filters/
  center-images.lua       # Quarto lua filter (image centering for PDF)
nb/courses/
  <course>/               # full course notes
  index.ipynb             # listing page
scripts/                  # standalone repository tasks (no watchtower imports)
  resume.py               # résumé/site artifact builder
  docs.py                 # Quarto preview
  project.py              # uv project creation
  render.py               # single notebook PDF
projects/                 # uv workspaces (each member has its own pyproject.toml)
src/watchtower/           # the `wt` CLI + importable `watchtower` package
  cli.py                  # Typer application
  scaffold.py             # notebook/course scaffolding
  notebook.py             # cell reads, edits, insertion, removal, tags, outputs
  outputs.py              # structured cell-output access + image extraction
  inspect.py              # `wt map | find | ls` + resolver
  convert.py              # `wt import` (external ipynb -> tier)
  execute.py              # `wt run` via nbclient
  kernels.py              # installed Jupyter kernel discovery
  paths.py                # repository and content paths
  vault.py                # OS keyring wrapper
```

## CLI reference (`wt`)

Run `.venv/bin/wt --help` for the live command list. The CLI is intentionally
focused on notebook/content workflows and secret management; use the Make
targets below for site and repository tasks.

> **Defaults**: `wt cat` limits each cell source to 4096 chars (use `--limit 0`
> for unlimited). Cell writes (`edit-cell`, `append-cell`, `insert-cell`) are
> hard-capped at 20k characters.

### Scaffolding & importing

| Command | What it does |
| --- | --- |
| `wt new post <name> [--title <title>]` | create a dated `nb/posts/<name>.ipynb` (title defaults to the titleized name) |
| `wt new course <name> <title>` | create `nb/courses/<name>/` with index, first lesson, and sidebar (title shown in index frontmatter) |
| `wt new chapter <course> <name> [--title <title>] [--section <name>]` | create `nb/courses/<course>/<name>.ipynb` and register in sidebar (title optional; sidebar text and notebook frontmatter are independent — edit either or both after scaffolding) |
| `wt new section <course> <name>` | add a section header to a course's sidebar in `_quarto.yml` |
| `wt import <ipynb> posts [<name>]` | import an external notebook into `nb/posts/`; the destination name defaults to the source stem |
| `wt import <ipynb> courses <course> [<chapter>] [--section <name>]` | import into an existing course, defaulting the chapter name to the source stem, and register it in the sidebar |

`wt new` is a command group containing `post`, `course`, `chapter`, and
`section`. Course imports require an existing course. Imports preserve stored
outputs, add a default Python kernelspec when needed, and strip a leading
Markdown `# Title` that duplicates frontmatter.

### Navigation & search

| Command | What it does |
| --- | --- |
| `wt map` | print repo structure as JSON |
| `wt ls posts|courses|projects` | list notebook sources or project directories |
| `wt find <query>` | grep across `.ipynb` cell sources |
| `wt count <name>` | print cell count (plan ranges before `--index N:M`) |
| `wt cat <name>` | print notebook as markdown; each cell headed `> cell N [code\|markdown]` (use N for `--index`) |
| `wt cat <name> --index N` | print one cell; `--index` also accepts Python-style `N:M`, `:M`, and `N:` slices |
| `wt cat <name> --tag foo` | print cells with Jupyter tag `foo` |
| `wt cat <name> --label foo` | print cells whose leading Quarto options contain `#\| label: foo` |
| `wt cat <name> --index N --offset O [--limit L]` | slice characters `O:O+L` from each selected cell (default limit 4096; `0` = unlimited) |
| `wt cat <name> --with-outputs` | also print each code cell's outputs (stream/error/etc.) |
| `wt cat <name> --with-outputs --out-offset O [--out-limit L]` | slice each output's text body; image/base64 payloads are summarized |
| `wt cat <name> --index N --context K` | include `K` surrounding cells, marked `context` in their headers |
| `wt output <name> --index N [--output K] [--save-dir DIR]` | inspect stored text/errors and extract image outputs; the default image directory is `ROOT_PATH / ".tmp"` |
| `wt diff <name> [--base REF]` | show a JSON-free Markdown diff against `HEAD` or another Git ref; terminal output is highlighted when supported |

Notebook names resolve as a bare stem, a tier-prefixed path such as
`nb/posts/example`, or a full `.ipynb` path. `wt map` reports the current
posts, courses, projects, portfolio path, and `AGENTS.md`; `wt find` reports
matching source lines with their notebook cell indices.

### Editing notebooks
| Command                              | What it does                                              |
|--------------------------------------|-----------------------------------------------------------|
| `wt edit-cell <name> --index N \| --tag foo \| --label foo [--content X]` | replace one cell's source while preserving outputs and metadata |
| `wt append-cell <name> [--type md\|code] [--content X]` | append a Markdown cell by default |
| `wt insert-cell <name> --after N \| --before N \| --tag foo \| --label foo [--type md\|code] [--content X]` | insert above/below a located cell; tag and label locators insert below |
| `wt remove-cell <name> --index N \| --tag foo \| --label foo` | remove all cells matching the locator; a tag or label may match multiple |
| `wt clear-outputs <name> [--index N \| --tag foo \| --label foo \| --from N]` | clear outputs from matching code cells; no locator clears all, and `--from N` clears from `N` to the end |
| `wt tag <name> --index N \| --tag foo \| --label foo [--add foo] [--remove bar]` | inspect tags, or add/remove repeatable tags on one matched cell |

For `edit-cell`, `append-cell`, and `insert-cell`, omit `--content` to read
the new source from stdin. Write locators must identify one cell. `remove-cell`
may remove every matching cell, while `clear-outputs` may operate on multiple
tagged cells. `--tag` and `--label` are mutually exclusive with `--index`.

### Executing notebooks

| Command | What it does |
|---|---|
| `wt kernels` | list installed Jupyter kernel names and languages |
| `wt run <name> [--index N] [--timeout S] [--kernel K]` | execute code cells in place; indexed runs execute through `N` in a fresh kernel and save only the selected cell's outputs |

Both forms start a fresh kernel. Without `--index`, the entire notebook runs;
with `--index N`, the prefix through cell `N` runs so that cell has prior
notebook state, but only its outputs are saved. Every indexed invocation
re-executes that prefix, which is deterministic but can be expensive when
earlier cells perform heavy computation. State is not reused between separate
CLI calls. The default per-cell timeout is 300 seconds. Cell errors are stored
inline, execution continues, and `wt run` exits with status 1 if any occurred.

Kernel selection: an explicit `--kernel K` overrides the notebook's
`kernelspec.name`; otherwise the notebook kernelspec is used, falling back to
`python3` when no kernelspec is stored.

### Course exercises

Exercise prompts live in chapter notebooks. Add or revise them with the same
`wt` cell commands used for other notebook content, and assess learner work
when requested. New exercises do not need stored answers. Existing solutions
are collected in the public [course solutions page](nb/courses/solutions.qmd).

### Core tools: vault

| Command | What it does |
| --- | --- |
| `wt vault set <key> <value>` | store a secret in the OS keyring |
| `wt vault get <key>` | print a secret value |
| `wt vault rm <key>` | remove a secret |
| `wt vault ls` | list stored keys |
| `wt vault export` | emit shell export statements |

`wt vault` is a command group. `get` prints a value, `ls` prints keys only,
and `export` emits shell-safe `export KEY=value` lines for use with
`eval "$(.venv/bin/wt vault export)"`.

## Make targets

`wt` focuses on reading, editing, running, and importing notebooks,
including course exercises, and retains `wt vault` as a core tool. Make handles
notebook PDF rendering, the site, résumé, project creation, and development
tasks. Run `make` or `make help` to see the available workflows.
Make invokes standalone scripts under `scripts/` using the repo virtual
environment, so shell activation is optional. These tasks live outside the
`watchtower` package and do not import it.

| Target             | What it runs   |
|--------------------|----------------|
| `make resume` | rebuild site pages, contact script, LaTeX, and PDF from `assets/resume.yaml` and published posts |
| `make docs [PORT=4200]` | rebuild résumé artifacts, then serve Quarto; `PORT=4300` selects another port |
| `make project NAME=<name>` | create a uv workspace project |
| `make render NOTEBOOK=<path.ipynb>` | render a notebook PDF into its source directory’s `pdf/` folder |
| `make help` | print the repository workflow summary |
| `make bootstrap`   | setup skills + `uv sync` |
| `make setup-skills`| create and validate skill symlinks |
| `make test`        | `pytest`       |
| `make lint`        | `ruff check .` |
| `make typecheck`   | `pyright`      |
| `make review`      | run lint, typecheck, tests, and print the diff summary |

Run `make lint` and `make typecheck` before committing changes to anything
under `src/` or `projects/`. A pre-commit hook runs Gitleaks against staged
changes to catch hardcoded secrets. Install Gitleaks (`brew install gitleaks`),
then run `uv run pre-commit install` from the repo root.

## Dependencies

- `uv` (workspace + project management) — https://docs.astral.sh/uv
- `quarto` CLI (render `.ipynb` to PDF/HTML) — install separately from https://quarto.org
- `ripgrep` (`rg`) — used by `wt find` for searching cell sources — `brew install ripgrep`
- `jupyterlab` + `jupyterlab-quarto` — edit `.ipynb` in JupyterLab
- `nbformat` — read/write `.ipynb` files from `wt` wrappers

The résumé PDF build requires XeLaTeX (`texlive-xetex` on Debian/Ubuntu).
Its name header uses the bundled Ubuntu Bold font in `assets/fonts/`, matching
the homepage; the font license is included alongside it.
