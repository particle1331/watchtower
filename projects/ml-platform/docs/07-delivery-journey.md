Status: Draft
Owner: ML platform team
Canonical for: Golden path and factual MLOps delivery progress register
Depends on: [production architecture](./00-production-architecture.md), [platform foundation](./01-platform-foundation.md), [reproducible ML](./02-reproducible-ml.md), [GenAI release artifacts](./03-genai-release-artifacts.md), [durable workflows](./04-durable-workflows.md), [online serving](./05-online-serving.md), [release and operations](./06-release-and-operations.md)
Last reviewed: 2026-07-29

# 07 — Delivery journey

## Outcome

The target golden path is: explore in a notebook, cross a tested package
boundary, train reproducibly in an ACA stage, evaluate an immutable artifact,
deploy an exact release descriptor, serve it via ACA App, process durable
workflows with stage execution, and operate the deployment. This document is
also a factual progress register. It distinguishes current code from planned
production work; examples are development aids, not platform guarantees.

## Production decisions

- Notebooks are for exploration, explanation, and captured evidence. Runtime
  code lives in the canonical Python package, Durable orchestrators/activities,
  and ACA stage entry points; notebooks are not imported by serving or batch
  workers.
- Container Apps is the default runtime for online serving (Apps) and offline
  stages (Jobs). No Functions or Azure ML managed online endpoints serving
  alternatives exist.
- Durable Functions is the workflow control plane: orchestrators are
  deterministic, versioned, and registered. They start/observe/cancel ACA Job
  executions but never deploy or mutate ACA definitions.
- Durable workflows handle stage execution, checkpoints, retries,
  external-approval pauses, and recovery as specified in
  [04 — Durable workflows](./04-durable-workflows.md).
- All large batch-style work runs as chunked ACA Job stages with bounded
  concurrency. Direct Durable activities handle only bounded Azure OpenAI calls
  (≤30–60 seconds). No per-document ACA Jobs.
- Redis/Celery is a failure-analysis example only. It is not a
  production-correctness stepping stone, and a local SETNX result does not
  prove duplicate safety.
- Every stage produces versioned contracts and evidence that the next stage can
  consume. A notebook cell, local producer, or Bicep declaration is not an
  acceptance result by itself.

## Shared concepts

The path carries Git SHA, workflow definition digest, orchestration instance ID,
ACA definition digest, image digest, immutable input/output Blob manifests,
model-manifest digest, environment-neutral behavior/provider metadata,
`release_id`, API/stage contract version, environment provider-configuration
reference/hash, processing-policy hash, operation key, and correlation ID.
`operation_key` is derived from immutable input identity/hash plus the exact
processing policy. A provider call may repeat after a crash; durable workflows
promise at most one committed result manifest per stage attempt, not exactly
one invocation. External side effects require downstream idempotency.

## Target design/contracts

### Canonical target repository and ownership layout

This is the target ownership boundary; it is not a claim that the current tree
already has these directories:

```text
examples/
├── celery_redis/             # failure-analysis example; archived, never production
└── compose/                  # current local compose stack; demo only
infra/
├── demo/                     # current demo Bicep, explicitly non-production
└── modules/
    ├── durable/               # Durable Functions host + task-hub storage
    ├── aca/                   # ACA environment + versioned Job/App definitions
    └── azureml/               # optional Azure ML workspace + compute (admission only)
schemas/
├── workflows/                 # workflow/stage/checkpoint manifest contracts
├── api/                       # HTTP API contracts
└── release/                   # release descriptor, intent, observation contracts
src/ml_platform/
├── workflows/                 # Durable orchestrators
├── activities/                # bounded Durable activities
├── stages/                    # ACA Job stage entry points (training, evaluation, batch)
├── online/                    # authenticated Container Apps HTTP runtime
├── genai/                     # artifact builder, evaluator, provider adapter
└── training/                  # reusable training adapters
tests/
├── unit/                      # pure package behavior
├── contract/                  # schemas and compatibility
└── integration/               # provisioned/disposable Azure boundary tests
.github/
└── workflows/                 # OIDC CI, build, evaluation, deploy, rollback
```

The platform team owns `infra/modules`, `schemas`, `src/ml_platform`, tests, and
workflows; the ML/training owner owns training adapters and stage definitions;
GenAI owners own `genai` artifacts/evaluators; service owners approve `online`
and workflow contracts. `examples/` and `infra/demo` are owned as
current demo evidence and must remain visibly non-production.

Current files must not be evolved as production by accident: flat
`src/ml_platform/tasks.py`, `producer.py`, `idempotency.py`, `celeryconfig.py`,
`docker-compose.yml`, `infra/main.bicep`, and `infra/gpu-training.bicep` remain
legacy/local baselines until deliberately migrated, tested, and replaced by the
canonical boundaries above.

### Notebook-to-package boundary

1. A notebook may explore data, validate an idea, and record exploratory output.
2. Move selected deterministic logic into the typed package with a CLI/job
   entry point. It accepts a versioned data manifest, not notebook globals or
   local paths.
3. Unit tests cover pure transformations and wrappers. Contract tests cover
   data, model signatures, API/workflow messages, release records, and durable
   stage transitions. Integration tests exercise identity and Azure resource
   boundaries.
4. A training/evaluation stage records Git SHA, dataset hash, parameters,
   metrics, environment hash, evaluation evidence, and exact artifact version.
   A release consumes that artifact without rerunning a notebook.

### Golden path

```text
notebook exploration
  -> package + fixture tests
  -> reproducible ACA Job CPU stage + exact artifact
  -> GenAI model manifest/evaluation (when applicable)
  -> Durable release workflow
  -> hashed deployment intent + deployment-observation events
  -> Durable stage orchestration + checkpoint manifests
  -> ACA online serving
  -> feedback/evaluation and optional approved AML extensions
```

The [release and operations](./06-release-and-operations.md) workflow is
explicit: build and upload the immutable Blob artifact, run the evaluation
stage, create the release descriptor, deploy via pinned workflow definition,
pause for production approval (`waitForExternalEvent`), deploy to production,
and append observation events. Stage orchestration follows
[04 — Durable workflows](./04-durable-workflows.md).

## Runnable demonstration

The current local path is deliberately a local demo:

```text
cd projects/ml-platform
make up
make train
make worker
make beat
make producer
make down
```

`make train` uses synthetic data, current Pandera validation, a scikit-learn
pipeline, and local MLflow. The current producer/worker exercise Redis/Celery;
unique documents and successful outputs only exercise those paths and do not
prove Durable orchestration, ACA stage execution, checkpoint recovery, or
provider call idempotency. SETNX is useful for failure analysis around crashes
and expiry, not for production correctness. Current Bicep declarations are
baselines and do not prove a runnable Azure runtime. The proof requires
`az bicep build`, a Durable orchestration instance ID with stage attempts,
ACA execution IDs, checkpoint manifests, and integration evidence against the
provisioned resources.

## Production implementation

### Migration plan

1. **Freeze and classify:** inventory the current flat source, local compose
   stack, and Bicep baseline as current demo evidence. Do not add
   production features to them. Record the gap against this document.
2. **Create boundaries:** establish the target directories, schemas, ownership,
   package entry points, and unit/contract test harness. Move demo code
   to `examples/` without implying equivalence.
3. **Build infrastructure:** put reusable production resources in
   `infra/modules`, including Durable host, ACA environment and versioned
   Job/App definitions, Blob containers, identities/RBAC, and monitoring.
   Keep `infra/demo` separate.
4. **Build execution planes:** add Durable orchestrators, activities, ACA stage
   entry points (`src/ml_platform/{workflows,activities,stages,online,genai}`),
   and immutable artifact/release-descriptor/deployment-intent/observation-event
   validators.
5. **Add CI/CD:** create `.github/workflows` with federated Entra OIDC,
   deterministic build/scan, Bicep definition registration, evaluation stage
   start, test deployment, approval, exact deployment, and rollback.
6. **Prove and cut over:** run explicit orchestration crash/recovery, checkpoint
   restore, approval timeout, suspend/resume, direct activity, ACA stage
   observation, and identity tests; attach deployment and integration evidence;
   then retire or clearly archive superseded baselines.

### Phase gates

**Phase 1 — Reproducible CPU training.** Dependencies are a real or approved
redacted dataset manifest, Python lock, ACA Job CPU stage definition, Blob
manifest-driven lineage, and evaluation schema. Exit evidence is a repeatable
stage with lineage (orchestration instance ID, stage ID, ACA execution ID,
definition digest, image digest), validation report, exact artifact Blob refs,
reload test, and signed metrics. The current local training is synthetic and
scores on training data; it is not this evidence.

**Phase 2 — Controlled serving.** Use the Phase 1 artifact, exact image,
ACA App definition, managed identity, API/auth contract, quota profile,
and release records. Exit evidence includes fail-closed startup, honest
readiness, authenticated contract tests, load/timeout/throttle results,
deployment intent/observation evidence, and exact-version rollback. The current
repository has no online handler; `infra/main.bicep` is only a baseline.

**Phase 3 — Durable workflows.** Use Blob containers, Durable Functions host,
ACA Job definitions, Durable orchestrators/activities, checkpoint/result
manifests, and approval events. Exit evidence includes:
- ACA stage start/observation/cancel from Durable orchestrator
- Durable activity for bounded Azure OpenAI call
- External approval via `waitForExternalEvent` (approved and timeout)
- Suspend/resume at checkpoint
- Orchestration crash recovery with idempotent stage commit
- Checkpoint manifest verification and restore
- Chunked batch stage with bounded concurrency
- Deployment intent/observation evidence and provisioned integration evidence

At most one result manifest is committed per stage attempt; provider invocation
count is not exactly one.

**Phase 4 — Feedback, GPU, and optional AML.** Require privacy-approved samples,
an evaluation owner, GPU quota/budget (or AML admission evidence for
exceptional clusters), and a real workload. Exit evidence links redacted
feedback to prediction/operation IDs, reproduces a quality report, and records
GPU correctness/utilization/cost and an exact artifact. This phase is optional
and does not block the previous phases.

## Failure modes/acceptance evidence

The register is complete only when each phase's evidence is attached to the
immutable release descriptor and the relevant deployment intent/observation
events. Do not infer claims from the current producer's unique documents, local
logs, or Bicep resource declarations.

| Claim | Required evidence | Current status |
|---|---|---|
| Reproducible training | Pinned ACA Job CPU stage, immutable Blob manifest, lineage (orchestration instance/stage/execution IDs), reload test | Planned beyond local synthetic run |
| Controlled serving | ACA App image, startup validation, auth/load/rollback tests, deployment intent/observation evidence | Planned; no serving code |
| Durable orchestration | Durable host, orchestrator starts/observes ACA Job, bounded activity, checkpoint manifest, approval event, suspend/resume, crash recovery | Planned; local Redis/Celery only |
| CI/release | OIDC federated Entra identity, scans/digest, artifact Blob refs, Bicep definition digests, immutable release descriptor, deployment intent/observation events, approval pause, exact deploy | Planned; no workflow |
| IaC/runtime | `az bicep build`, successful deployment, identity/RBAC checks, provisioned integration results | Current Bicep is not runtime proof |
| Monitoring/SLO | Correlated telemetry, dashboards, alerts, runbooks, restore evidence | Planned; declarations are only a baseline |
| GPU / AML extension | Quota-approved ACA GPU stage or documented AML admission, utilization/correctness/cost report, exact artifact | Optional and planned |

## Open decisions

- Which pilot and acceptance owner provide the real dataset, labels, traffic
  profile, batch window, and privacy classification?
- What are the final API/stage compatibility policy, artifact/config registry,
  Azure OpenAI quotas, SLOs, RPO/RTO, and cost ceiling?
- Which local demonstrations remain local-only and which require a disposable
  Azure environment with workload identity and integration evidence?
- What evidence threshold triggers optional GPU/AML feedback work rather than
  more CPU, serving, or workflow hardening?
- Which Durable Functions host plan (Consumption, Flex Consumption, dedicated)
  matches expected throughput and cold-start requirements?

## References

- [Durable workflows](./04-durable-workflows.md)
- [Online serving](./05-online-serving.md)
- [Release and operations](./06-release-and-operations.md)
- [Production architecture](./00-production-architecture.md)
- [Reproducible ML](./02-reproducible-ml.md)
