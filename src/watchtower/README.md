# watchtower

Personal notes, articles, courses, and projects system. This package provides
the `wt` CLI, which manages the notebook-based knowledge base in the repo
root, and the `core` tools library containing helpers for ML-based code.

## Modules

| Module | Purpose |
|---|---|
| `cli.py` | Typer application (`wt`) assembling all subcommands |
| `convert.py` | Import an external Jupyter notebook into a content tier |
| `inspect.py` | Agent-facing inspection helpers: repo structure, search, file content |
| `notebook.py` | Read and edit cells in `.ipynb` files |
| `paths.py` | Repo path resolution helpers for workspace projects |
| `render.py` | Quarto wrappers: render notebooks to PDF, serve the site |
| `resume.py` | Resume builder; YAML is the single source for both outputs |
| `scaffold.py` | Scaffold new artifacts: notes, articles, courses, projects |
| `vault.py` | Secrets vault backed by the OS keyring |
| `core/` | Core helpers for ML notebooks (reproducibility + plotting) |

## Usage

Run the CLI from the repo root:

```
.venv/bin/wt --help
```

See `AGENTS.md` and `README.md` at the repo root for the full CLI reference.
