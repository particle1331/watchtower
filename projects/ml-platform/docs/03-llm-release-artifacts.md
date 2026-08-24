Status: Draft
Owner: ML platform team
Canonical for: LLM release artifact (MLflow pyfunc), evaluator, release inputs
Depends on: [00 — Production architecture](./00-production-architecture.md), [02 — Reproducible ML](./02-reproducible-ml.md)
Last reviewed: 2026-07-30

# 03 — LLM release artifacts

## Outcome

An LLM workflow (prompt + model + retrieval/config) is packaged as a single
MLflow `pyfunc` model version, evaluated by a repeatable evaluator, and released
by the same promotion mechanism as any other model. There is no separate LLM
control path — an LLM app is a kind of model version in the self-hosted registry.

## Production decisions

### An LLM app is packaged as a pyfunc model version

An LLM application is captured as an MLflow `pyfunc` artifact that bundles:

- the prompt template(s) and configuration,
- the model/endpoint reference and generation parameters,
- any retrieval/index configuration,
- the signature (inputs/outputs) and dependencies.

Registering it produces a **version number** in the same self-hosted MLflow
registry used by classical models. Serving and batch inference load it by
`models:/<name>/<version>` exactly like any other model — no special path.

### Evaluation is a repeatable job

LLM evaluation runs as an ACA Job that scores the candidate version against a
fixed evaluation set with defined metrics (task-appropriate quality/faithfulness
checks, plus cost/latency where relevant). Results are logged to MLflow (attached
to the run) and summarized in a results-DB record. Promotion requires meeting the
recorded thresholds, identical in spirit to classical evaluation in
[02](./02-reproducible-ml.md).

### Config and secrets

Prompts and config travel inside the artifact so a version is self-contained. Any
external model/API credentials are resolved at runtime from Key Vault via the
workload's managed identity — never embedded in the artifact or image.

### No bespoke release ledger

We do **not** build hash-chained release descriptors or deployment-intent event
records. A release is: a registered version + its evaluation record + a Git tag +
the Job/App definition digest that references it. That chain is sufficient to
answer "what is live and where did it come from" (see
[06](./06-release-and-operations.md)).

## Shared concepts

- **Pyfunc artifact** — the self-contained LLM unit: prompt + config + model
  reference + signature + deps.
- **Evaluation record** — MLflow-logged metrics plus a results-DB summary that
  gates promotion.
- **Uniform identity** — an LLM release is a registry version, indistinguishable
  operationally from a classical model version.

## Implemented path

- `src/train_job/register_llm.py` and `ml_platform.llm.evaluator` are copied
  into the shared train image. The Compose profile and the
  `infra/modules/llm_job` adapter invoke those exact entrypoints.
- The optional cloud evaluation Job is bound to `id-jobs-train`, reads the
  configured dataset, writes metrics to MLflow, and records the result.
- The packaging helper in `src/ml_platform/` builds and registers the pyfunc
  version from prompt/config source under version control.

## Runnable demonstration

Compose exposes `llm-register` and `llm-evaluate` as profile-gated Jobs using
the shared train image and the bundled `demo/llm/eval.jsonl` fixture. Azure uses
manual ACA Jobs from that same train image; set `LLM_EVAL_DATASET` to enable the
evaluation Job and let the managed identity resolve the model credential from
Key Vault.

## Failure modes and acceptance evidence

| Failure mode | Prevented by | Acceptance evidence |
|---|---|---|
| LLM drifts to a special path | Pyfunc version in the same registry | Serving/batch load an LLM version by `models:/name/version` unchanged |
| Unrepeatable evaluation | Fixed eval set + defined metrics as a Job | Re-running evaluator on the same version reproduces metrics |
| Secret baked into artifact | Runtime Key Vault resolution | Artifact contains no credentials; run resolves via identity |
| Opaque release provenance | Version + eval record + Git tag + digest | From what is live, recover version, evaluation, and code digest |

## Open decisions

- Evaluation metric set per LLM task type.
- Whether to snapshot external model endpoint versions in the artifact metadata.

## References

- Classical training/eval and lineage — [02](./02-reproducible-ml.md).
- Promotion/rollback mechanics — [06](./06-release-and-operations.md).
- Serving a pyfunc version — [05](./05-online-serving.md).
