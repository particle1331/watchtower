# autocode

`autocode` is the cumulative application for the Watchtower course **Shipping
the Agent**. It turns the headless `agent-harness` package into a browser-based,
local-first product:

- semantic HTML, responsive CSS, and browser-native JavaScript;
- FastAPI REST routes and a WebSocket event stream;
- one application-service layer shared by web and CLI adapters;
- an append-only journal plus a queryable SQLite projection;
- deterministic and live agent-runner implementations; and
- artifacts, search, sync, replay, jobs, updates, and operational drills.

The default agent is deterministic, so the complete request and event path can
run without an API key:

```console
$ uv sync --package autocode --extra service --dev
$ uv run --package autocode --extra service autocode serve
```

Open <http://127.0.0.1:8000/>. Create a session, send a task, then refresh the
browser. The timeline is reconstructed from `.autocode/sessions.db` and its
sibling journal.

Select the live harness only when its provider configuration is available:

```console
$ AUTOCODE_AGENT_MODE=harness uv run --package autocode --extra service autocode serve
```

Run the project evidence with:

```console
$ uv run --package autocode --extra service --dev pytest projects/autocode/tests -q
```

PostgreSQL, S3-compatible storage, managed identity, and a reverse proxy are
production adapters. The local course path already includes the frontend, API,
application logic, agent boundary, database, realtime transport, and tests.
