# Watchtower — agent rules

## Architecture
This repo is a personal system with three tiers of content with DIFFERENT visibility:
- `notes/*.qmd` — private working notes (personal drafting surface)
- `essays/*.qmd` — public essays (promoted from notes, published via Quarto)
- `projects/<name>/` — code projects (each a uv workspace member)

Source files are Quarto markdown (`.qmd`) — plain text, prose + code. There is
no mirror or sync step: the `.qmd` source IS the knowledge base.

## Knowledge base
- The canonical knowledge base is `notes/*.qmd` and `essays/*.qmd`.
- `*.ipynb` files are excluded from `grep`/`glob` via `.ignore` — legacy
  notebooks are NOT knowledge base material and are gitignored. Convert any
  dropped-in notebook with `wt convert <foo.ipynb>` before working with it.
- For PAST note context: use `wt find <query>` (searches sources) or
  `wt cat <name>` (reads one source). You may also grep `*.qmd` directly.

## Navigation
- Run `wt map` first to get structured repo layout as JSON.
- Run `wt ls notes|essays|projects` for plain listings of source files.

## Editing
- Edit `.qmd` files directly — they are plain markdown with ```{python} code
  chunks. No sync, no mirrors, no regeneration step.
- Before commit there is no hook; run `make lint` and `make typecheck` if you
  changed Python under `src/` or `projects/`.

## Legacy notebooks
- `.ipynb` is not tracked. To migrate one: `wt convert <path.ipynb>` writes a
  `.qmd` next to it (or `wt convert <in.ipynb> <out.qmd>` for an explicit dest).
- `jupytext` is kept as a dependency solely for this one-time conversion.

## Per-project rules
If working inside `projects/<name>/`, also read `projects/<name>/AGENTS.md` if
present (project-specific rules stack on top of these).

## Vault (secrets)
- Secrets live in the OS keyring, accessed via `wt vault`. NEVER commit secret values.
- `wt vault env` emits export lines — projects use it via `eval $(wt vault env)` or `from watchtower.vault import get_secret`.

## CLI command reference (for the agent)
- `wt convert <ipynb> [dest.qmd]` — one-time convert legacy notebook to qmd
- `wt new note|essay|project <name>` — scaffold new artifact (`.qmd` stub)
- `wt map` — JSON repo structure (orientation)
- `wt find <query>` — grep across .qmd sources only
- `wt cat <name>` — print one .qmd source
- `wt ls notes|essays|projects` — list sources in a tier
- `wt render <tier> <name> | <path.qmd>` — render source -> PDF (`notes/pdf/` or `essays/pdf/`)
- `wt resume` — render `assets/resume.yaml` -> `assets/resume.tex` + `index.qmd` via Jinja2 templates, then `pdflatex` -> `assets/resume.pdf` (builds in a temp dir). The YAML is the single source; edit it, never the generated `.tex`/`.qmd`.
- `wt docs` — serve the essays+portfolio site (publishing is handled by the
  `publish.yml` GitHub Action on push to `main`, output goes to `gh-pages`).
- `wt vault get|set|list|env <key>` — secret management

## Freeze / CI execution policy
- `_quarto.yml` sets `execute.freeze: true` and the `_freeze/` directory is
  tracked.
- The GitHub Action renders with `--no-execute`, so the runner never runs code
  in `.qmd` files. Outputs must already be cached in `_freeze/`.
- After adding or editing executable cells locally, run `quarto render` or
  `wt docs` to update the freeze cache, then commit both the `.qmd` source and
  the matching `_freeze/` changes.