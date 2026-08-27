# Legal Research Agent with LangGraph

Deterministic reference implementation for the Watchtower LangGraph course.
It researches a bounded Philippine Rule 65 question from pinned summaries of
official sources, preserves authority-level provenance, pauses for typed human
review, and emits a legal research memorandum plus a machine-readable run record.

```bash
uv run evidence-brief run --question-id conflict-01
uv run evidence-brief eval --variant full
```

The default adapter is fully offline. The optional OpenAI adapter is never
selected implicitly and is not used for stored course outputs.

Evaluation is split into three claims that must not be conflated:

- twelve course-authored Rule 65 cases form six one-fact counterfactual pairs
  across worked, validation, and challenge tiers;
- public Bar questionnaire records are contamination-prone regression metadata
  and remain excluded from scoring until a lawfully obtained suggested answer
  and qualified reviewer approval are supplied; and
- graph ablations measure workflow contracts such as review, reconciliation,
  provenance, and restart behavior.

The corpus is an educational fixture, not a substitute for checking the current
official text, the complete record, or advice from a qualified Philippine lawyer.
