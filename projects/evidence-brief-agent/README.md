# Evidence Brief Agent

Deterministic reference implementation for the Watchtower LangGraph course.
It turns a fixture-backed technical question into a provenance-preserving brief,
pauses for typed review, and emits a machine-readable run record.

```bash
uv run evidence-brief run --question-id conflict-01
uv run evidence-brief eval --variant full
```

The default adapter is fully offline. The optional OpenAI adapter is never
selected implicitly and is not used for stored course outputs.
