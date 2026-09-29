# autocode quickstart

Install the service dependencies and start the full browser application from
the repository root:

```console
uv sync --package autocode --extra service --dev
uv run --package autocode --extra service autocode doctor
uv run --package autocode --extra service autocode serve
```

Open <http://127.0.0.1:8000/>. The default demo agent streams deterministic
events and needs no provider credentials. Create a session, submit a task, and
refresh the page to prove that the browser restores its state through the API.

The application creates `.autocode/sessions.db` and a sibling write-ahead
journal. The journal is the first durable record; SQLite is the queryable
projection used by the session browser and resume path. The CLI reaches the
same application service:

```console
uv run --package autocode autocode run "inspect the current project" --json
uv run --package autocode autocode resume SESSION_ID
```

Back up both the database and journal while writes are stopped, then run the
restore drill before treating the backup as evidence. Update checks remain
opt-in. Debug bundles pass through the central secret scrubber.

To use the live agent harness, provide its normal model configuration and set
`AUTOCODE_AGENT_MODE=harness`. Before an external deployment, also choose the
database, object store, token secret, reverse proxy, backup policy, retention
policy, and rollback owner explicitly.
