# watchtower

A personal system for notes, essays, projects, and course material — write in
Quarto markdown (`.qmd`), render to PDF or a website, and let an AI ingest the
plain-text source directly. No mirror, no sync — the `.qmd` IS the knowledge base.

## Tiers

| Tier      | Where                       | Effort | Audience | Listing             |
|-----------|-----------------------------|--------|----------|---------------------|
| Home      | `index.qmd`                 | —      | public   | resume landing page |
| Essays    | `essays/*.qmd`               | high   | public   | `essays/index.qmd`  |
| Portfolio | `portfolio.qmd`             | high   | public   | cards on one page   |
| Notes     | `notes/*.qmd`                | low    | you      | `notes/index.qmd`    |
| Learning  | `learning/*.qmd`             | mid    | you      | `learning/index.qmd` |
| Photos    | `photos.qmd`                | —      | public   | single gallery page  |

Source files are Quarto markdown — plain markdown with ```` ```{python} ```` code
chunks. The same file renders to HTML (site), PDF (read-back), and serves as
clean text for agent retrieval.

## Quick start

```bash
make bootstrap                       # uv sync (creates .venv)

wt new note my-note                  # notes/my-note.qmd
wt new essay my-essay                # essays/<YYYY-MM-DD>-my-essay.qmd
wt new project my-code-project       # uv init projects/my-code-project

wt render notes my-note              # render qmd -> PDF (notes/pdf/) and open
wt resume                             # compile assets/resume.tex -> assets/resume.pdf
wt preview                            # serve site on :4200
wt publish                            # render site to _site/
```

> **Note:** `wt new` only scaffolds `note`, `writing`, and `project` today. For
> `learning/`, drop a `.qmd` into the folder by hand. `wt ls` recognizes
> `notes | essays | projects` (not `learning` yet).

## Editing workflow

`.qmd` files are runnable notebooks, not just static markdown. Open them in
JupyterLab (with the `jupyterlab-quarto` extension, already installed) or VS
Code + the Quarto extension — run cells inline, see figures and math render.

Renders reuse cached outputs: `_quarto.yml` has `execute.freeze: true`, so
`quarto render` will NOT re-run cells unless you explicitly pass `--execute`
or change the source. Run things once in JupyterLab; the site picks up those
outputs on the first render and freezes them.

## Migrating legacy notebooks

```bash
wt convert old.ipynb                       # writes old.qmd next to it
wt convert old.ipynb notes/new.qmd         # explicit destination
```

`.ipynb` files are gitignored and excluded from agent retrieval — convert once,
then work in the `.qmd`.

## Site

The site (rendered to `_site/`) pulls together all five content tiers:

- `_quarto.yml` — project config, navbar, format, theme, freeze.
- Theme: `united` (Bootstrap), KaTeX math, lightbox images, justified text,
  back-to-top, reader-mode, breadcrumbs.
- `assets/styles.css` — layout + typography tweaks.
- Navbar: Portfolio · Essays · Learning · Notes · Photos.
- Each content tier has an `index.qmd` listing (Quarto auto-generates a
  paginated table of contents from sibling `.qmd` files).

Quarto needs to find Python with `jupyter` installed. The `wt` wrappers
(`wt preview`, `wt publish`) handle this by pointing `QUARTO_PYTHON` at the
venv interpreter. Calling `quarto` directly? Set it yourself:

```bash
QUARTO_PYTHON="$PWD/.venv/bin/python" quarto render
```

## Secrets

```bash
wt vault set OPENAI_API_KEY sk-...
wt vault list
eval $(wt vault env)        # export lines for current shell
```

Stored in the OS keyring; never committed. Projects read them via:

```python
from watchtower.vault import get_secret
get_secret("OPENAI_API_KEY")
```

## Layout

```
index.qmd                 # "Ron Medina — Resume" home page
portfolio.qmd             # hand-maintained project cards
photos.qmd                # personal photos (mountaineering, landscapes, kid)
_quarto.yml               # publishes all content tiers (incl. freeze: true)
assets/
  styles.css              # site styling
  img/                    # shared images
  resume.yaml             # canonical résumé source (single source of truth)
  resume.tex.j2           # Jinja2 template -> moderncv LaTeX (PDF)
  index.qmd.j2            # Jinja2 template -> site home page (HTML)
  resume.pdf              # built by `wt resume` (served as download link)
filters/
  center-images.lua        # Quarto lua filter (image centering for PDF)

notes/
  *.qmd                   # working notes
  index.qmd               # listing page
  pdf/                    # gitignored rendered PDFs
essays/
  *.qmd                   # YYYY-MM-DD-slug.qmd essays
  index.qmd               # listing page
  pdf/                    # gitignored rendered PDFs
learning/
  *.qmd                   # full course notes
  index.qmd               # listing page
projects/                 # uv workspaces (each member has its own pyproject.toml)
src/watchtower/           # the `wt` CLI + importable `watchtower` package
  cli.py                  # Typer application
  scaffold.py             # `wt new note|essay|project`
  convert.py              # `wt convert`
  render.py               # `wt render` / `preview` / `publish`
  inspect.py              # `wt map` / `find` / `cat` / `ls`
  vault.py                # OS keyring wrapper
```

## CLI reference (`wt`)

| Command                          | What it does                                              |
|----------------------------------|-----------------------------------------------------------|
| `wt new note <name>`             | create `notes/<name>.qmd`                                 |
| `wt new essay <slug>`           | create `essays/<YYYY-MM-DD>-<slug>.qmd`                   |
| `wt new project <name>`          | `uv init projects/<name>` and wire workspace              |
| `wt convert <ipynb> [dest.qmd]`  | one-time `.ipynb` → `.qmd` (jupytext)                     |
| `wt render notes <name>`         | render one qmd to PDF (`notes/pdf/`), open it             |
| `wt render essays <name>`        | render one qmd to PDF (`essays/pdf/`), open it           |
| `wt render <path/to.qmd>`        | render by full path                                       |
| `wt resume`                     | render `assets/resume.yaml` -> `assets/resume.tex` + `index.qmd`, then `pdflatex` -> `assets/resume.pdf` |
| `wt preview`                     | serve the site (blocking; :4200)                          |
| `wt publish`                     | render site to `_site/`                                   |
| `wt map`                         | print repo structure as JSON                              |
| `wt find <query>`                | grep across `.qmd` sources                                |
| `wt cat <name>`                  | print one `.qmd` source by stem                           |
| `wt ls notes\|essays\|learning\|projects` | list sources in a tier                              |
| `wt vault set <key> <value>`      | store secret                                              |
| `wt vault get <key>`              | print secret value                                        |
| `wt vault list`                   | list stored secret keys                                   |
| `wt vault env`                    | emit `export` lines for all secrets                       |

## Make targets

The Makefile covers only the generic dev workflows (external tools that
don't belong in `wt`). Watchtower-specific commands live in `wt`.

| Target             | What it runs   |
|--------------------|----------------|
| `make bootstrap`   | `uv sync`      |
| `make test`        | `pytest`       |
| `make lint`        | `ruff check .` |
| `make typecheck`   | `pyright`      |

Run `make lint` and `make typecheck` before committing changes to anything
under `src/` or `projects/`. There is no pre-commit hook wired up.

## Dependencies

- `uv` (workspace + project management) — https://docs.astral.sh/uv
- `quarto` CLI (render `.qmd` to PDF/HTML) — install separately from https://quarto.org
- `ripgrep` (`rg`) — used by `wt find` for searching `.qmd` sources — `brew install ripgrep`
- `jupytext` — used only by `wt convert` for one-time notebook migration
- `jupyterlab-quarto` — edit `.qmd` as notebooks in JupyterLab