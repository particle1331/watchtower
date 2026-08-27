# watchtower ⛫

A personal system for notes, articles, projects, and course notes.

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
| Home      | `index.qmd`                 | —      | public   | resume landing page |
| Articles  | `nb/articles/*.ipynb`          | high   | public   | `nb/articles/index.ipynb` |
| Portfolio | `nb/portfolio/portfolio.ipynb` | high   | public   | cards on one page         |
| Notes     | `nb/notes/*.ipynb`             | low    | you      | `nb/notes/index.ipynb`    |
| Courses   | `nb/courses/**/*.ipynb`        | mid    | you      | `nb/courses/index.ipynb`  |
| Photos    | `nb/photos/photos.ipynb`       | —      | public   | single gallery page |

Site content is primarily stored as Jupyter notebooks (`.ipynb`); the generated
résumé home page is `index.qmd`. Agents read notebook cell sources as plain
markdown via the `wt` CLI (jupytext under the hood); they never see
the raw JSON.

## Quick start

```bash
make bootstrap                       # setup shared skills + uv sync (creates .venv)
wt new note my-note                  # nb/notes/my-note.ipynb
wt new note my-note -t "My Note"       # custom display title

wt new article my-article             # nb/articles/my-article.ipynb
wt new article my-article -t "My Article"  # custom display title
wt new course llm "Large Language Models"  # nb/courses/llm/ (index + first lesson)
wt new chapter my-course 02-bar       # nb/courses/my-course/02-bar.ipynb + register in sidebar
wt new section my-course "My Section" # add section header to course sidebar
wt new project my-code-project       # uv init projects/my-code-project

wt render notes my-note              # render ipynb -> PDF (nb/notes/pdf/) and open
wt resume                            # render assets/resume.yaml -> assets/resume.tex + index.qmd, then pdflatex -> assets/resume.pdf
wt docs                              # serve site on :4200
wt docs --port 4300                  # serve an isolated worktree preview
```

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
wt import ~/Downloads/foo.ipynb notes my-foo                   # copy + normalize into nb/notes/
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
wt vault set OPENAI_API_KEY sk-...
wt vault rm OPENAI_API_KEY
wt vault ls
eval $(wt vault export)        # export lines for current shell
```

Stored in the OS keyring; never committed. Projects read them via:

```python
from watchtower.vault import get_secret
get_secret("OPENAI_API_KEY")
```

## Layout

```
index.qmd                 # "Ron Medina ∷ Résumé" home page (generated by wt resume)
nb/
  portfolio/
    portfolio.ipynb         # hand-maintained project cards
  photos/
    photos.ipynb            # personal photos (mountaineering, landscapes, kid)
_quarto.yml               # publishes all content tiers (execute.enabled: false)
assets/
  styles.css              # site styling
  img/                    # shared images
  resume.yaml             # canonical résumé source (single source of truth)
  resume.tex.j2           # Jinja2 template -> moderncv LaTeX (PDF)
  index.qmd.j2            # Jinja2 template -> site home page (QMD)
  resume.pdf              # built by `wt resume` (served as download link)
filters/
  center-images.lua       # Quarto lua filter (image centering for PDF)

  notes/
    *.ipynb                 # working notes
    index.ipynb             # listing page
    pdf/                    # gitignored rendered PDFs
  articles/
    *.ipynb                 # long-form articles
    index.ipynb             # listing page
    pdf/                    # gitignored rendered PDFs
  courses/
    <course>/               # full course notes
    index.ipynb             # listing page
projects/                 # uv workspaces (each member has its own pyproject.toml)
src/watchtower/           # the `wt` CLI + importable `watchtower` package
  cli.py                  # Typer application
  scaffold.py             # `wt new note|article|course|chapter|section|project`
  notebook.py             # `wt cat | edit-cell | append-cell | insert-cell | remove-cell | tag`
  outputs.py              # structured cell-output access + image extraction
  inspect.py              # `wt map | find | ls` + resolver
  convert.py              # `wt import` (external ipynb -> tier)
  render.py               # `wt render | docs`
  resume.py               # `wt resume`
  vault.py                # OS keyring wrapper
```

## CLI reference (`wt`)

> **Defaults**: `wt cat` limits each cell source to 4096 chars (use `--limit 0`
> for unlimited). Cell writes (edit/append/insert) are hard-capped at 20k chars.

### Scaffolding & importing

| Command | What it does |
| --- | --- |
| `wt new note <name> [--title <title>]` | create `nb/notes/<name>.ipynb` (title optional; defaults to `<name>`) |
| `wt new article <name> [--title <title>]` | create `nb/articles/<name>.ipynb` (date injected in frontmatter; title optional; defaults to `<name>` titleized) |
| `wt new course <name> <title>` | create `nb/courses/<name>/` with index, first lesson, and sidebar (title shown in index frontmatter) |
| `wt new chapter <course> <name> [--title <title>] [--section <name>]` | create `nb/courses/<course>/<name>.ipynb` and register in sidebar (title optional; sidebar text and notebook frontmatter are independent — edit either or both after scaffolding) |
| `wt new section <course> <name>` | add a section header to a course's sidebar in `_quarto.yml` |
| `wt new project <name>` | `uv init projects/<name>` and wire workspace |
| `wt import <ipynb> notes|articles [<name>]` | import external notebook (Colab/Kaggle) into a flat tier |
| `wt import <ipynb> courses <course> [<chapter>] [--section <name>]` | import as a chapter of an existing course (copies into the course dir and registers in the course's sidebar) |

### Rendering & serving

| Command                              | What it does                                              |
|--------------------------------------|-----------------------------------------------------------|
| `wt render notes <name>`             | render one notebook to PDF (`nb/notes/pdf/`), open it        |
| `wt render articles <name>`            | render one notebook to PDF (`nb/articles/pdf/`)                |
| `wt render <path/to.ipynb>`          | render by full path                                        |
| `wt resume`                          | render `assets/resume.yaml` -> `assets/resume.tex` + `index.qmd`, then `pdflatex` -> `assets/resume.pdf` |
| `wt docs [--port <port>]`            | serve the site on the chosen port (default: :4200)        |

### Navigation & search

| Command | What it does |
| --- | --- |
| `wt map` | print repo structure as JSON |
| `wt find <query>` | grep across `.ipynb` cell sources |
| `wt count <name>` | print cell count (plan ranges before `--index N:M`) |
| `wt cat <name>` | print notebook as markdown; each cell headed `> cell N [code\|md]` (use N for `--index`) |
| `wt cat <name> --index N` | print only cell N |
| `wt cat <name> --index N:M` | print cells N..M-1 (Python slice; `:M` and `N:` ok) |
| `wt cat <name> --tag foo` | print cells with Jupyter tag `foo` |
| `wt cat <name> --label foo` | print cells with matching [Quarto label](https://quarto.org/docs/authoring/cross-references.html#computations) |
| `wt cat <name> --index N --offset O [--limit L]` | slice chars `O:O+L` of cell N (default limit 4096; 0 = unlimited) |
| `wt cat <name> --with-outputs` | also print each code cell's outputs (stream/error/etc.) |
| `wt cat <name> --with-outputs --out-offset O [--out-limit L]` | slice each output's text body |
| `wt output <name> --index N [--output K] [--save-dir DIR]` | inspect one cell's stored outputs; print text/errors and save images (default: `ROOT_PATH / ".tmp"`) |
| `wt cat <name> --index N --context K` | print cells N-K..N+K (surrounding context, marked `context`) |
| `wt cat <name> --tag solution --decode` | print solution cells decoded to plaintext (spoiler opt-in) |
| `wt diff <name> [--base REF]` | markdown diff of a notebook vs a git ref (both sides rendered like `wt cat`, solutions decoded); highlights in interactive terminals and stays plain when piped or `NO_COLOR` is set |

### Editing notebooks
| Command                              | What it does                                              |
|--------------------------------------|-----------------------------------------------------------|
| `wt edit-cell <name> --index N \| --tag foo \| --label foo [--content X]` | replace a cell's source (outputs preserved) |
| `wt append-cell <name> [--type md\|code] [--content X]` | append a new cell (default: md)          |
| `wt insert-cell <name> --after N [--type] [--content X]` | insert a new cell below index N            |
| `wt insert-cell <name> --before N ...`           | insert above index N                                    |
| `wt remove-cell <name> --index N \| --tag foo \| --label foo` | delete matching cell(s); a tag may remove multiple |
| `wt tag <name> --index N \| --tag foo \| --label foo [--add foo] [--remove bar]` | list tags (no flags), or add/remove |
| `wt clear-outputs <name> [--index N \| --tag foo \| --label foo \| --from N]` | clear stored outputs of code cells (markdown skipped); `--from N` clears every code cell from N to the end; no locator clears all |
> `--content X` is optional for `edit-cell` / `append` / `insert`; if omitted,
> the new source is read from stdin (useful for multi-line contents via heredoc).
> Write locators (`--index` / `--tag` / `--label`) must match exactly one cell,
> except `remove-cell --tag foo`, which removes every matching cell.

### Executing notebooks

| Command | What it does |
|---|---|
| `wt kernels` | list installed Jupyter kernel names and languages |
| `wt run <name> [--timeout S] [--kernel K]` | execute every code cell in order and write all outputs back to the `.ipynb` |
| `wt run <name> --index N [--timeout S] [--kernel K]` | execute cells through `N` in a fresh kernel and write only cell `N`'s outputs back |

Both forms start a fresh kernel. Without `--index`, the entire notebook runs;
with `--index N`, the prefix through cell `N` runs so that cell has prior
notebook state, but only its outputs are saved. Every indexed invocation
re-executes that prefix, which is deterministic but can be expensive when
earlier cells perform heavy computation. State is not reused between separate
CLI calls.

Kernel selection: an explicit `--kernel K` overrides the notebook's
`kernelspec.name`; otherwise the notebook kernelspec is used, falling back to
`python3` when no kernelspec is stored.

### Problems

Course problems and solutions live entirely in the chapter notebooks — there
is no `problems.json`. A problem is a markdown cell tagged `problem` + its id
(e.g. `07-3`), headed by `### [PNN.N] title` (chapter from the notebook
filename, number per-chapter, e.g. `### [P11.4] Energy retention in
practice`), optionally followed by a starter code cell; the solution is
the code cell tagged `solution` + the same id right after it. Its source is a
`#| echo: false` / `#| eval: false` / `#| output: false` Quarto cell-options
header followed by the ROT18-obfuscated body, each non-empty line prefixed
`# ` (blank lines stay blank). The `#|` options hide the cell entirely on the
rendered site, so solutions stay in the notebook for self-grading but never
spoil the rendered chapters.

| Command                              | What it does                                              |
|--------------------------------------|-----------------------------------------------------------|
| `wt problem <course> <locator>`      | print a problem statement (plus starter code)             |
| `wt solution <course> <locator>`     | print a problem's decoded solution (worked text, answer, checks, reference code) |
| `wt hint <course> <locator> [--level 1\|2]` | progressive hint (checks without expected values, worked-text excerpt) |
| `wt add-exercise <course> <chapter> --statement X [--starter X] --solution X [--number N]` | append a new problem + solution pair (solution encoded on write) |
| `wt solution-edit <course> <locator> --content X` | create/replace a solution cell (plaintext in, encoded stored) |
| `wt check <course>`                  | validate tagging, pairing, and encoding across all chapters |

Locator forms: `7.3`, `07-3`, `07 3`, `07-projection-and-orthogonalization 3`,
or a fuzzy chapter name like `projection 3`.


### Secrets (vault)

| Command                              | What it does                                              |
|--------------------------------------|-----------------------------------------------------------|
| `wt vault set <key> <value>`          | store secret                                              |
| `wt vault get <key>`                 | print secret value                                        |
| `wt vault rm <key>`                  | delete secret                                             |
| `wt vault ls`                        | list stored secret keys                                   |
| `wt vault export`                       | emit `export` lines for all secrets                       |

## Make targets

The Makefile covers only the generic dev workflows (external tools that
don't belong in `wt`).

| Target             | What it runs   |
|--------------------|----------------|
| `make bootstrap`   | setup skills + `uv sync` |
| `make setup-skills`| create and validate skill symlinks |
| `make test`        | `pytest`       |
| `make lint`        | `ruff check .` |
| `make typecheck`   | `pyright`      |

Run `make lint` and `make typecheck` before committing changes to anything
under `src/` or `projects/`. There is no pre-commit hook wired up.

## Dependencies

- `uv` (workspace + project management) — https://docs.astral.sh/uv
- `quarto` CLI (render `.ipynb` to PDF/HTML) — install separately from https://quarto.org
- `ripgrep` (`rg`) — used by `wt find` for searching cell sources — `brew install ripgrep`
- `jupyterlab` + `jupyterlab-quarto` — edit `.ipynb` in JupyterLab
- `nbformat` — read/write `.ipynb` files from `wt` wrappers
