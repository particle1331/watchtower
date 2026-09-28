# watchtower

Personal posts, courses, and projects system. This package provides
the `wt` CLI, which manages the notebook-based knowledge base in the repo
root, and the `core` tools library containing helpers for ML-based code.

## Modules

| Module | Purpose |
|---|---|
| `cli.py` | Typer application (`wt`) for notebook operations and core tools |
| `convert.py` | Import an external Jupyter notebook into a content tier |
| `inspect.py` | Agent-facing inspection helpers: repo structure, search, file content |
| `notebook.py` | Read and edit cells in `.ipynb` files |
| `outputs.py` | Read stored cell outputs and extract image payloads into `ROOT_PATH / ".tmp"` for inspection |
| `paths.py` | Repo path resolution helpers for workspace projects |
| `scaffold.py` | Scaffold posts, courses, chapters, and sections |
| `vault.py` | Secrets vault backed by the OS keyring |
| `core/` | Core helpers for ML notebooks (reproducibility + plotting) |

## Usage

Run the CLI from the repo root:

```
.venv/bin/wt --help
```

See `AGENTS.md` and `README.md` at the repo root for the full CLI reference.

Repository utilities use `make docs`, `make resume`, `make project NAME=<name>`. Core secret management stays in `wt vault`. Run `make help` for the task list.

The PDF, site, résumé, and project Make targets call standalone scripts under
`scripts/`. Their implementations live outside this package and do not import it.
