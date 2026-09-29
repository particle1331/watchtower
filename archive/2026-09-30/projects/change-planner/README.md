# Change Planner Agent

Read-only reference implementation for the Watchtower LangGraph course. It
searches a versioned repository snapshot, relates implementation evidence to
tests and history, forms regression hypotheses, and exports a reviewable change
plan.

The default path is deterministic and offline:

```bash
uv run change-planner run --scenario dry-run-01
uv run change-planner run --root path/to/repository --request "increase client retries" --with-history
uv run change-planner eval
uv run change-planner index --root path/to/repository --with-history --output .tmp/index.json
```

The project separates responsibilities deliberately:

- retrieval and code-intelligence functions preserve evidence and scores;
- the LangGraph workflow plans, fans out, retries, verifies, pauses, and
  resumes investigations; and
- evaluation compares lexical, dense, hybrid, structural, and workflow paths
  on pinned repository fixtures with seeded change scenarios, reporting
  precision, recall, reciprocal rank, nDCG, estimated latency, and index cost.
- the `index` command ingests a local Python-first repository without changing
  it, extracting source kinds, symbols, test candidates, and a revision-bound
  content fingerprint.
- the `run --root` path feeds that indexed snapshot into the same planner, so
  local repository runs exercise the real ingestion boundary while remaining
  read-only by default. Use `--allow-targeted-tests` only when test execution
  is explicitly authorized.

The agent does not edit files, merge changes, deploy systems, or certify that a
repository snapshot represents the complete production environment.
