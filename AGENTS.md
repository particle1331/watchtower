# Watchtower — agent rules

## Architecture
This repo is a personal system with three tiers of content with DIFFERENT visibility:
- `notes/*.ipynb` — private working notes (personal drafting surface)
- `essays/*.ipynb` — public essays (promoted from notes, published via Quarto)
- `learning/*.ipynb` — full course notes
- `projects/<name>/` — code projects (each a uv workspace member)

Canonical source files are Jupyter notebooks (`.ipynb`). Authors edit them
in JupyterLab (running cells, getting outputs); Quarto renders the notebooks
to the website using **inline outputs, no re-execution** — so heavy compute
done once in JupyterLab (or imported from Colab/Kaggle) is preserved as-is.

## Knowledge base
- The canonical knowledge base is `notes/*.ipynb` and `essays/*.ipynb`.
- Raw `.ipynb` JSON is noisy — do NOT `grep`/`read` it directly. Use the
  `wt` wrappers below, which expose cell sources as plain markdown.
- `.ipynb_checkpoints/` is excluded from listings and resolution.

## Environment
- All `wt` commands require the venv. Use `.venv/bin/wt` (from repo root)
  or activate the venv first. Never run bare `wt`.

## Navigation
- Run `wt map` first to get structured repo layout as JSON.
- Run `wt ls notes|essays|learning|projects` for plain listings of notebooks.
- `<name>` for any cell command (`cat`, `edit-cell`, `append-cell`, `insert-cell`,
  `remove-cell`, `tag`, `count`, `render`) resolves as: bare stem (`001-testnote`),
  tier-prefixed stem (`notes/001-testnote`), or full path (`notes/001-testnote.ipynb`).

## Reading notebooks
- `wt cat <name>` — print all cells as markdown (`> cell N [code|markdown] ...` headers; `>` marks tool meta, not notebook content).
- `wt cat <name> --index N` — just cell N.
- `wt cat <name> --tag foo` — cells with Jupyter tag `foo` (may be multiple).
- `wt cat <name> --label fig-x` — cell whose first line is `#| label: fig-x`.
- `wt cat <name> --index N --offset 500 --limit 1000` — slice chars 500:1500
  of cell N's source. Header carries `src[start:end] of total` so you can
  chain reads without re-paying for bytes you've already seen.
- `wt cat <name> --index N --with-outputs` — also print the cell's outputs,
  each with its own `>> cell N output K [stream stdout|error ...]` header.
  Use `--out-offset` / `--out-limit` to slice each output's body the same
  way `--offset` / `--limit` slice the source. Image/base64 payloads are
  summarized (`[image/png, N chars — not shown]`), not dumped.

## Editing notebooks
- Cell writes (`edit-cell`, `append-cell`, `insert-cell`) are hard-capped at
  20k chars per source — break large content into smaller cells.
- **Cell mutations (`edit-cell`, `insert-cell`, `remove-cell`) take a numeric
  `--index` only.** Tags and labels are read-only locators, usable with
  `wt cat` to *find* a cell — they are not accepted on writes. To target a
  cell by tag or label, first run `wt cat <name> --tag foo` or
  `wt cat <name> --label foo` to read the `> cell N ...` index from the
  output, then pass that `N` to the mutation. One cell, one index, one
  auditable locator.
- **Indices shift after insert/remove.** Any `insert-cell` or `remove-cell`
  bumps the index of every cell that comes after the anchor by ±1. So:
  - When planning multiple mutations, do them right-to-left (highest index
    first) so earlier indices stay valid. `edit-cell` does NOT shift
    anything — it only rewrites the source of cell N.
  - After an insert/remove, do NOT reuse indices you resolved before that
    mutation — re-run `wt cat` (or `wt count`) to get fresh indices.
- `wt edit-cell <name> --index N --content "..."` — replace a cell's source
  (outputs + metadata preserved). Source may come from `--content` or stdin
  (useful for multi-line via heredoc).
- `wt append-cell <name> --type md|code [--content "..."]` — push to end.
- `wt insert-cell <name> --after N | --before N --type md|code [--content "..."]`
  — insert below/above the cell at index N.
- `wt remove-cell <name> --index N` — delete the cell at index N. To remove a
  range, resolve each index via `wt cat --tag/--label` (or `wt count` for a
  tail) and delete from highest to lowest (see index-shift rule above).
- `wt tag <name> --index N --add foo --remove bar` — manage Jupyter cell tags.
  With neither `--add` nor `--remove`, prints the cell's current tags.

## Importing notebooks
- `wt import <path.ipynb> notes|essays|learning [<name>]` — copy a notebook
  produced elsewhere (Colab, Kaggle, a teammate) into a tier dir, preserving
  inline outputs. Quarto will render with those outputs, no re-execution.

## Rendering
- `wt docs` serves the site on :4200 (publishing is handled by the
  `publish.yml` GitHub Action on push to `main`).
- `wt render <tier> <name> | <path.ipynb>` renders one notebook to PDF
  (`notes/pdf/` or `essays/pdf/`) using inline outputs.
- `_quarto.yml` sets `execute.enabled: false`. Quarto never runs your
  code at render time — it uses whatever outputs already live in the `.ipynb`.

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
  `eval $(wt vault export)` or `from watchtower.vault import get_secret`.

## CLI command reference (for the agent)
- `wt new note|essay|project <name>` — scaffold new artifact (`.ipynb` stub)
- `wt map` — JSON repo structure (orientation)
- `wt ls notes|essays|learning|projects` — list sources in a tier
- `wt find <query>` — grep across `.ipynb` cell sources
- `wt count <name>` — cell count (plan ranges before `--index N:M`)
- `wt cat <name> [--index N|N:M | --tag foo | --label foo] [--offset O --limit L]
  [--with-outputs] [--out-offset O --out-limit L]`
  — read notebook cells as markdown. `--index` accepts a single 0-based index
  or a Python-style slice (`N:M`, `:M`, `N:`) to scan a range of cells quickly.
  Default per-cell limit is 4096 chars (`--limit 0` = unlimited).
- `wt edit-cell <name> --index N [--content X]`
  — replace a cell's source (outputs preserved); --index only
- `wt append-cell <name> --type md|code [--content X]`
  — append a new cell
- `wt insert-cell <name> --after N | --before N --type md|code [--content X]`
  — insert a new cell; --index only
- `wt remove-cell <name> --index N`
  — delete matching cell; --index only (delete ranges from highest to lowest)
- `wt tag <name> --index N [--add foo] [--remove bar]` — manage cell tags
- `wt import <path.ipynb> notes|essays|learning [<name>]`
  — import an external notebook (Colab/Kaggle) into a tier
- `wt render <tier> <name> | <path.ipynb>` — render notebook -> PDF
- `wt resume` — render `assets/resume.yaml` -> `assets/resume.tex` + `index.ipynb`
  via Jinja2 templates, then `pdflatex` -> `assets/resume.pdf` (builds in a
  temp dir). The YAML is the single source; edit it, never the generated
  `.tex`/`.ipynb`.
- `wt docs` — serve the site (blocking; :4200)
- `wt vault get|set|list|env <key>` — secret management