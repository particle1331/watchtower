Status: Draft
Owner: ML platform team
Canonical for: This document set's index, dependency order, and pragmatic-plan entry point
Last reviewed: 2026-07-30

# ML platform plan

This directory is the implementation contract for `projects/ml-platform`. It
describes a **deliberately small, low-ops platform** for a team of ML engineers
who are not full-time platform/DevOps engineers. The guiding rule is: use the
fewest moving parts that deliver reproducible training, honest evaluation,
scheduled and on-demand batch/inference workflows, and observable operations —
and only add machinery when a concrete need forces it.

## Design philosophy

We reject the "enterprise control-plane" build (durable orchestration engine,
hash-chained deployment ledgers, per-identity authorization proofs, bespoke
message brokers) because it costs more to build and operate than a small ML team
can sustain, and buys guarantees we do not yet need. Instead we lean on
**ephemeral, image-pinned Azure Container Apps Jobs**, a **self-hosted MLflow**
we fully control, and a **generic results database** for run state.

Every decision below was chosen to preserve two things the team cares about most:
**implementation freedom** (our own container images, our own library and MLflow
versions) and **low operational burden** (no long-running worker fleets, no
broker to babysit by default).

## Reading order

| Order | Document | Primary boundary |
|---|---|---|
| 1 | [00 — Production architecture](./00-production-architecture.md) | Target planes, fixed decisions, cross-document invariants |
| 2 | [01 — Platform foundation](./01-platform-foundation.md) | Azure resources, identities, RBAC, IaC, networking |
| 3 | [02 — Reproducible ML](./02-reproducible-ml.md) | Training/eval as ACA Jobs, self-hosted MLflow, lineage |
| 4 | [03 — LLM release artifacts](./03-llm-release-artifacts.md) | MLflow `pyfunc` artifact, evaluator, release inputs |
| 5 | [04 — Periodic & batch workflows](./04-periodic-and-batch-workflows.md) | Scheduling, manual triggers, results DB, batch granularity, continuation |
| 6 | [05 — Online serving](./05-online-serving.md) | ACA App HTTP serving, exact artifact loading |
| 7 | [06 — Release & operations](./06-release-and-operations.md) | CI/CD, promotion, rollback, observability, dashboard |
| 8 | [07 — Delivery journey](./07-delivery-journey.md) | Golden path and phased progress register |
| — | [08 — Multi-GPU training](./08-multi-gpu-training.md) | Admission-gated Azure ML clusters for distributed training |

## Fixed invariants

These hold across every document. A change to any of them is an architecture
decision, not an implementation detail.

1. **ACA Jobs are the execution plane.** Every workflow — training, evaluation,
   batch inference, ad-hoc task — runs as an Azure Container Apps **Job**:
   ephemeral, started from a pinned image digest, scaled to zero when idle. Jobs
   support `Schedule` (cron), `Manual` (on-demand), and `Event` triggers. There
   are **no long-running workers**, so a code deploy can never leave a stale
   worker running old code — the next execution simply pulls the new image.
2. **No workflow control-plane service.** Linear multi-step workflows are an
   ordinary script inside one Job. We do **not** run Durable Functions or any
   orchestration engine. Fan-out and continuation are expressed as parent/child
   rows in the results DB plus a small stateless rule (see [04](./04-periodic-and-batch-workflows.md)).
3. **No application broker/queue by default.** No Service Bus, Redis broker,
   Celery worker fleet, or KEDA queue scaling in the baseline. If large-fan-out
   scale ever demands it, the documented upgrade path is Celery-as-a-library
   with workers running as **short-lived KEDA-triggered ACA Jobs** (drain-and-exit,
   still image-pinned), backed by managed Redis — not a long-lived worker fleet.
4. **Self-hosted MLflow is the tracking + model registry.** We run our own
   MLflow at an exact pinned version (Postgres metadata backend, Blob artifact
   store). We do **not** use Azure ML managed MLflow, whose server-side version
   lags and constrains registry/evaluation features. The registered model
   **version number** is the canonical model identity.
5. **A generic results database is the run store.** One Celery-result-backend-style
   table records `status`, `output` (JSON metadata), and `error` for **every**
   job. Parent/child rows give per-item granularity for batch inference. Large
   payloads go to Blob; only metadata/status live in the results DB.
6. **MLflow is scoped to model lifecycle.** Training and evaluation log runs and
   register versions. **Batch inference only reads** a pinned model version — it
   does not write MLflow experiment runs; its status/output lives in the results DB.
7. **GitHub Actions is CI/CD only.** It builds/tests/scans images and updates
   ACA Job/App definitions. It is **never** used as a workflow scheduler or
   orchestrator.
8. **Least-privilege managed identities; OIDC for CI.** Each workload (Job, App,
   dashboard, CI) has its own identity with minimal roles. No shared broad
   identity, no long-lived secrets in images or Git.
9. **Distributed/multi-GPU training is an admission-gated exception.** It runs on
   Azure ML `command` jobs against min-zero clusters, logging to the same
   self-hosted MLflow. It is not part of the baseline.

## Current implementation versus target

**Existing (local demo only):** the repository's local Compose stack, synthetic
training data with Pandera validation, a stubbed inference path, and demo IaC.
These prove local wiring, not a production runtime.

**Planned:** ACA Job stages, self-hosted MLflow, the results DB, the workflow
dashboard, IaC-deployed Job/App definitions, and CI/release workflows. None of
these exist yet; a passing `make up` is not acceptance evidence.

## Acceptance boundary

An implementation is complete when it demonstrates the evidence required by each
document — reproducible ACA Job stages with MLflow lineage, results-DB run
records with batch granularity, exact-version serving and rollback, and the
observability/dashboard wiring — not when a local demo runs.

## References

- Current code: `docker-compose.yml`, `src/ml_platform/`, and `infra/`.
- UI mockup: [`mockups/workflow-dashboard.html`](./mockups/workflow-dashboard.html).
