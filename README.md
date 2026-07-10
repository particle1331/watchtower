# watchtower

A personal system for notes, writings, and projects — designed so you write
in notebooks, read PDFs, and let an AI ingest mirrored markdown.

## Three tiers

| Tier      | Where                 | Effort   | Audience |
|-----------|-----------------------|----------|----------|
| Notes     | `notes/src/*.ipynb`   | low      | you      |
| Writings  | `writings/src/*.ipynb`| medium   | public   |
| Portfolio | `portfolio.qmd`       | high     | public   |

## The mirror principle

You edit `.ipynb`. The CLI regenerates plain markdown mirrors in `notes/mirror/`
and `writings/mirror/` via `jupytext` (prose + code, no outputs — clean text
for retrieval). The AI agent's knowledge base is the mirrors, never the
notebooks — `*.ipynb` is excluded from grep/glob via `.ignore`.

## Quick start

```bash
make bootstrap       # uv sync + pre-commit install
wt new note my-first-note        # create notes/src/my-first-note.ipynb (paired)
# ...write in the notebook...
wt sync             # regenerate mirrors
make render F=notes/src/my-first-note.ipynb   # open a PDF for read-back
wt preview          # serve the writings+portfolio site
```

## Secrets

```bash
wt vault set OPENAI_API_KEY sk-...
wt vault list
eval $(wt vault env)        # populate current shell
```

Stored in OS keyring; never committed. Projects can read via
`from watchtower.vault import get_secret`.

## Layout

```
notes/
  src/                       # working notebooks (git-tracked)
  mirror/                    # jupytext-generated md (the knowledge base)
  pdf/                       # gitignored rendered PDFs
writings/
  src/                       # YYYY-MM-DD-slug.ipynb essays
  mirror/                    # mirrors, LLM-reads-this
projects/                    # uv workspaces
src/watchtower/              # the `wt` CLI + importable `watchtower` package
portfolio.qmd                # hand-maintained curated cards
index.qmd                    # site landing page
_quarto.yml                  # publishes writings+portfolio, never notes/
```

## Dependencies

- `uv` (workspace + project management)
- `quarto` CLI (rendering notebooks to PDF/HTML) — install separately from https://quarto.org
- `jupytext` and `nbconvert` — installed via `uv sync`