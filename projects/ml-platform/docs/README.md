Status: Draft
Owner: ML platform team
Canonical for: This document set's index, dependency order, and production-plan entry point
Last reviewed: 2026-07-29

# ML platform production plan

This directory is the implementation contract for the `projects/ml-platform`
production path. It documents the target Azure architecture separately from the
current local demo stack.

## P0 dependency order

Implement and review the documents in this order. `04` and `05` can proceed in
parallel after `03`; `06` joins them only after both are complete.

| Order | Document | Primary boundary |
|---|---|---|
| 1 | [00 — Production architecture](./00-production-architecture.md) | Target planes, fixed decisions, and cross-document invariants |
| 2 | [01 — Platform foundation](./01-platform-foundation.md) | Azure resources, identities, RBAC, networking, and governance |
| 3 | [02 — Reproducible ML](./02-reproducible-ml.md) | Manifest-driven stages, lineage contracts |
| 4 | [03 — GenAI release artifacts](./03-genai-release-artifacts.md) | The model-manifest contract, evaluation evidence, and release inputs |
| 5a (parallel) | [04 — Durable workflows](./04-durable-workflows.md) | Durable Functions orchestration, stage execution, checkpoints, and recovery |
| 5b (parallel) | [05 — Online serving](./05-online-serving.md) | ACA HTTP serving, readiness, and exact artifact loading |
| 6 | [06 — Release and operations](./06-release-and-operations.md) | Durable release workflow, CI, promotion, deployment records, rollback, and operations |
| 7 | [07 — Delivery journey](./07-delivery-journey.md) | Golden path and progress register |

## Fixed production invariants

- **Durable Functions is the workflow control plane.** Orchestrators are
  deterministic, registered, and versioned. They never perform network or
  filesystem I/O and never hold document bytes or model bytes. Durable history
  holds compact control state and pointers; it is not a business broker.
- **Azure Container Apps is the execution plane.** ACA Jobs run coarse offline
  container stages (training, evaluation, chunked batch). ACA Apps provide HTTP
  online serving only. Bicep deploys and version-controls all ACA Job/App
  definitions. Durable Functions starts, observes, and may cancel executions; it
  never deploys or mutates definitions.
- **No application queue by default.** Durable task-hub internals are not a
  business broker. Service Bus, Cosmos-ledger, outbox, KEDA queue scaling, DLQ,
  producer/worker, message locks, and reconciliation-as-queue requirements are
  all removed from the baseline architecture.
- **Blob Storage owns immutable input, output, and checkpoint manifests.**
  Blob digest/version is the canonical identity for all artifacts. An
  independently queryable business database is deferred until a proven retention,
  query, or transactional-side-effect requirement is documented.
- **Azure OpenAI calls ≤30–60 seconds run directly in bounded Durable
  activities.** Larger evaluations or batches use chunked ACA stages with
  bounded internal concurrency. No ACA Job is launched per document.
- **Azure ML is optional and narrow.** Optional tracking and model-catalog
  references; optional zero-minimum CPU/GPU clusters only after documented
  admission evidence showing distributed/RDMA or specialized GPU/capability
  that ACA cannot satisfy. No baseline AML jobs, pipelines, endpoints, Compute
  Instances, data assets, or model assets as runtime identity. Blob digest/
  version is canonical.
- The immutable-record chain is owned without circular schemas: `03` owns the
  current GenAI model manifest; `06` owns the release descriptor, hashed
  deployment intent, and individually hashed deployment-observation events.
  The descriptor follows evaluation and release approval; the intent precedes
  deployment and events record observations. See [03](./03-genai-release-artifacts.md).

## Current implementation versus target

**Existing, local demo only:** Docker Compose runs MLflow 3,
Redis/Celery, and the supporting local services; training uses synthetic data
and Pandera; inference is a demo/stub; and the repository contains demo Bicep.
The current `pyproject.toml` and `make up` path are not production
dependencies. Durable Functions, ACA stages, workflow definitions, and CI
remain planned.

**Planned:** Durable Functions orchestrators and activities, ACA Job stages
and Apps, Blob manifest-driven lineage, direct Azure OpenAI activities,
optional Azure ML tracking, CI/release workflows, and production
evaluation/observability. `make az-up` and the current Bicep are a local demo
deployment, not proof of a working Azure runtime or of the production
architecture.

## Acceptance boundary

An implementation is not complete because a local demo `make up`, `make az-up`,
or a demo Bicep deployment succeeds. Acceptance requires the exact references,
identity/RBAC tests, immutable manifests and Blob artifacts, evaluator aggregate
and row-level evidence, deployment intent/observation events, and rollback
evidence required by the documents above.

## References

- Current code: `docker-compose.yml`, `src/ml_platform/`, and `infra/`.
