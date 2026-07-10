# projects/

Code projects, each a uv workspace member. Create one with:

```bash
wt new project my-app
```

That runs `uv init --package projects/my-app` and wires it into the workspace.
(project-specific rules live in `projects/<name>/AGENTS.md` if you want them.)

To depend on the shared watchtower SDK:

```toml
# projects/<name>/pyproject.toml
[tool.uv.sources]
watchtower = { workspace = true }
```

```python
from watchtower.vault import get_secret
from watchtower.paths import repo_root
```