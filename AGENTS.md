# Watchtower — agent rules

## Architecture
This repo is a personal system with three tiers of content with DIFFERENT visibility:
- `notes/src/*.ipynb` — private working notebooks (personal drafting surface)
- `writings/src/*.ipynb` — public essays (promoted from notes, published via Quarto)
- `projects/<name>/` — code projects (each a uv workspace member)

Mirrors live in `notes/mirror/*.md` and `writings/mirror/*.md`, regenerated via `wt sync`.

## CRITICAL: do NOT read past notebooks
- `*.ipynb` files are excluded from `grep`/`glob` via `.ignore` — past notebooks are NOT knowledge base material. YAML+JSON+base64 noise makes them poor retrieval sources.
- The canonical knowledge base is `notes/mirror/*.md` and `writings/mirror/*.md` (clean text, prose + code, no outputs).
- For PAST note context: use `wt find <query>` (searches mirrors) or `wt cat <name>` (reads one mirror). Do NOT grep across notebooks.
- For the CURRENT notebook (the one I'm actively editing): you may read it directly when I @-mention it.

## Navigation
- Run `wt map` first to get structured repo layout as JSON.
- Run `wt ls notes|writings|projects` for plain listings of mirrors (never source notebooks).

## Sync discipline
- I edit `.ipynb`. Mirrors are regeneratable. NEVER edit a `.md` mirror directly — they're auto-generated artifacts.
- Before commit, `make check` (or the pre-commit hook) regenerates mirrors and fails on drift.
- If a mirror appears out of sync, treat it as a sync bug — run `wt sync`, never hand-edit the mirror.

## Per-project rules
If working inside `projects/<name>/`, also read `projects/<name>/AGENTS.md` if present (project-specific rules stack on top of these).

## Vault (secrets)
- Secrets live in the OS keyring, accessed via `wt vault`. NEVER commit secret values.
- `wt vault env` emits export lines — projects use it via `eval $(wt vault env)` or `from watchtower.vault import get_secret`.

## CLI command reference (for the agent)
- `wt sync` — regenerate all mirrors from notebooks
- `wt check` — verify mirrors in sync (used by pre-commit)
- `wt new note|writing|project <name>` — scaffold new artifact
- `wt vault get|set|list|env <key>` — secret management
- `wt map` — JSON repo structure (orientation)
- `wt find <query>` — grep across mirrors only
- `wt cat <name>` — print one mirror
- `wt ls notes|writings|projects` — list mirrors
- `wt render <notebook>` — render notebook -> PDF (notes/pdf/)
- `wt preview` — serve the writings+portfolio site
- `wt publish` — render site to _site/