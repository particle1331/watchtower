Status: Draft
Owner: ML platform team
Canonical for: Production Azure foundation, security, governance, and IaC
Depends on: [00 — Production architecture](./00-production-architecture.md)
Last reviewed: 2026-07-29

# 01 — Platform foundation

## Outcome

Provision a least-privilege Azure foundation from Bicep so Durable Functions can
start ACA Job stages, publish immutable Blob outputs, and deploy exact ACA App
releases without portal work or long-lived credentials.

## Production decisions

- **Durable Functions is the workflow control plane.** Deploy a Durable host
  (isolated Functions runtime with Durable extension) in a plan that supports
  the expected orchestration throughput. Task-hub storage is an implementation
  detail of the Durable extension (Azure Storage queues/tables/blobs by
  default), not a business broker or application queue.
- **Azure Container Apps is the default execution plane.** ACA Jobs run offline
  stages (training, evaluation, chunked batch). ACA Apps run HTTP online
  serving. Bicep defines every ACA Job/App and deploys them by immutable
  definition digest. Durable Functions starts, observes, and may cancel ACA Job
  executions; it never deploys or mutates definitions.
- **Blob Storage owns all payloads and manifests.** Blob digest/version is the
  canonical identity for inputs, outputs, checkpoints, and model artifacts.
  No Azure ML data assets or model assets are required as runtime identity.
- **No application queue.** Service Bus, Cosmos DB ledger, outbox, KEDA queue
  scaling, DLQ, producer/worker identities, and reconciliation-as-queue are not
  in the baseline. Durable task-hub storage is not a business broker.
- **Azure ML is optional and narrow.** If used, optional managed MLflow tracking
  and model-catalog references. Optional zero-minimum CPU/GPU clusters only
  after documented admission evidence showing distributed/RDMA or specialized
  GPU/capability ACA cannot satisfy. No baseline AML jobs, pipelines, endpoints,
  or Compute Instances.
- **A separately queryable business database** is deferred until a proven
  retention, query, or transactional-side-effect requirement is documented.
- **Azure OpenAI** is provisioned as an explicit provider dependency with quota
  controls. Calls ≤30–60 seconds run in bounded Durable activities; larger work
  uses chunked ACA stages.
- The current `pyproject.toml` `mlflow>=3.0.0` dependency is local-demo-only.
  Production needs explicit dependency groups and exact tested pins.

## Existing versus planned

`infra/main.bicep` is a local demo Bicep monolith containing
self-hosted MLflow 3, PostgreSQL, Redis, a **non-Durable** Function app, and an
admin-enabled ACR. The Function app is not a Durable Functions host and must
not be evolved in place — it is a local demo resource that will be replaced by
the production Durable host. Local Docker uses MLflow 3 and MinIO.
`infra/gpu-training.bicep` demonstrates a min-zero GPU cluster. These are
examples of Bicep mechanics, not a working Azure runtime proof or the
production baseline.

Production modular Bicep for the Durable host + state backend, ACA environments
and versioned definitions, Blob containers, Azure OpenAI, OIDC, and least-
privilege identities remains planned, as does the optional Azure ML path.

## Target design/contracts

### Module and deployment order

The orchestrator must call these modules in order. A module may export resource
IDs to a later module, but may not create an undeclared side-effect resource.
Identity role assignments are applied only after their target scopes exist and
before the workload is activated.

1. **Governance and diagnostics:** resource-group tags, policy, locks where
   approved, budgets, Log Analytics, Application Insights, action groups, and
   diagnostic settings.
2. **Identity bootstrap:** GitHub Actions OIDC deploy identity, Durable host
   managed identity, ACA stage-job identity, ACA online-app identity, and
   optional Azure ML job identity (only if AML exception is approved).
3. **Data/security:** Blob input, output, and checkpoint containers with
   versioning/soft delete; Key Vault; and private endpoints/DNS when the
   network gate requires them. No Cosmos DB, Service Bus, or application queue.
4. **Build:** ACR with admin access disabled, scanning/content-trust policy,
   and CI push identity.
5. **Durable host:** Function App (isolated process) with Durable extension,
   storage-account backend for task hub, managed identity, and diagnostic
   settings. No self-hosted tracking service.
6. **ACA platform and definitions:** ACA environment, network integration,
   versioned Job definitions for each stage (training, evaluation, chunked
   batch), versioned App definition for online serving, and Key Vault references.
   Bicep exports each definition's digest for release-descriptor pinning.
7. **Provider:** environment-specific Azure OpenAI provider configuration for
   the resource/deployment, endpoint, explicit model/API version, quota,
   network, and invocation policy.
8. **Optional Azure ML:** workspace, managed identity, storage/Key Vault/ACR
   connections, and managed tracking. Only after documented admission evidence.
   No self-hosted MLflow service. No Compute Instances.
9. **Optional AML compute:** min-zero CPU job cluster/profile; invoke the
   separate GPU module only after quota and cost approval. Only after documented
   admission evidence.
10. **RBAC activation:** bind the identities below at the smallest scopes,
    run positive/negative authorization tests, then enable job/app triggers.

### Identity and RBAC contract

Identities are separate even when workloads share an ACA environment or Durable
host. A role is scoped to the named container, deployment, or resource where
Azure supports that scope.

| Principal | Required access | Must not have |
|---|---|---|
| GitHub Actions deploy identity | Federated OIDC; test/prod-scoped deployment; `AcrPush`; ACA Job/App definition deployment; Durable host management | Client secrets, routine subscription Owner, production payload reads |
| Durable host identity | Start/read/cancel ACA Job executions; Blob input read; Blob output/checkpoint write; Azure OpenAI invoke (for bounded activities) | ACA definition mutation, broad storage keys, model registration |
| ACA stage-job identity | ACR pull, Blob input read, Blob output/checkpoint write, Azure OpenAI invoke (if stage makes provider calls) | Durable host management, ACA definition mutation, CI permissions |
| ACA online-app identity | ACR pull, Blob artifact read (startup artifact loading), named Key Vault secrets, telemetry write | Durable host management, stage-job interference, CI permissions |
| Optional AML job identity | Submit/read its workspace jobs (AML exception only) | Storage keys, broad Key Vault access, unrelated environment data |
| Operators | JIT roles and audited read access; break-glass only when approved | Shared admin accounts and routine Owner access |

Role assignments are named by environment and tested negatively: a stage job
cannot deploy ACA definitions, an online app cannot start ACA Jobs, the Durable
host cannot mutate definitions, and a pull-request identity cannot activate
production.

### Network, governance, and capacity gates

Record the gate result in the environment configuration before production data
or ingress is enabled.

| Gate | Required control |
|---|---|
| Confidential/restricted data exists | VNet/private endpoints and private DNS for Blob, Key Vault, ACR, Azure OpenAI, Durable host, and ACA environment; deny public access where supported |
| Internet-facing API is required | Authenticated ACA ingress plus approved WAF/front door and rate limits; no admin endpoint |
| Durable host reachable from ACA | Approved network integration (VNet injection or private endpoint) |
| Private endpoint unavailable | Record data scope, compensating controls, owner, and expiry before exception |
| Capacity/cost | ACA Jobs min `0` replicas; optional GPU min `0`, initial max `1`; ACA App replicas/concurrency from latency and Azure OpenAI RPM/TPM budgets |

Required tags are `application=ml-platform`, `environment`,
`owner=ml-platform-team`, `costCenter`, `dataClassification`, `managedBy=bicep`,
`lifecycle`, and `criticality`. Set retention, soft delete, recovery, audit,
and budget policies per environment; legal hold or stricter data-owner policy
wins.

## Runnable demonstration

```text
cd projects/ml-platform
make az-up SUFFIX=demo LOCATION=southeastasia
make az-status SUFFIX=demo
make az-down SUFFIX=demo
```

This runs the existing Bicep demo exercise and teardown. Because it deploys
legacy/self-hosted MLflow 3 and a non-Durable Function app, success is not
proof of a working production Azure runtime, Durable host, ACA definitions,
or the identity contract.

## Production implementation

1. Add parameter files with no secret values and explicit environment/resource
   scopes. Use Key Vault references and managed identities.
2. Implement the modules in the order above: governance, identities, Blob/Key
   Vault/ACR, Durable host, ACA environment and versioned definitions, Azure
   OpenAI, optional Azure ML, then RBAC/network.
3. Bind OIDC and RBAC, then run `az bicep build`, lint, `what-if`, policy,
   resource-inventory, cost, and negative authorization checks.
4. In a test environment, start one ACA Job stage, observe its execution from
   the Durable host, publish one Blob output, deploy one exact ACA App image,
   and run one bounded Durable activity against Azure OpenAI before requesting
   production access.

## Failure modes/acceptance evidence

| Acceptance test | Pass condition/evidence |
|---|---|
| IaC boundary | Bicep/lint/what-if are repeatable and contain only approved resources; no production Service Bus, Cosmos ledger, legacy Function (non-Durable), or self-hosted MLflow |
| Required foundation | Durable host, ACA environment/definitions, Blob containers, Azure OpenAI, ACR, and diagnostics are present |
| Identity separation | Durable host, ACA stage, ACA app, and CI role tests show distinct least-privilege permissions |
| Durable orchestration | Orchestrator starts an ACA Job, records execution ID in history, observes completion, and reads the result manifest |
| Scale-to-zero | ACA Jobs report min `0`; no Compute Instance; GPU is blocked without admission evidence |
| Secret boundary | No secret appears in Git, image, Bicep parameters, deployment output, or logs |
| Network/governance | Selected private/public gate, tags, retention, diagnostics, budgets, and recovery tests pass |

## Open decisions

- Select VNet/private endpoint scope and whether ACA ingress is public behind an
  approved front door.
- Confirm retention with data owners and legal/security.
- Confirm Durable host plan (Consumption, Flex Consumption, or dedicated) based
  on expected throughput and cold-start tolerance.
- Approve CPU/GPU SKU, Azure OpenAI RPM/TPM, and environment budgets.
- Decide whether and when an independently queryable business database is
  required.

## References

- [Production architecture](./00-production-architecture.md)
- [Reproducible ML](./02-reproducible-ml.md)
- [GenAI release artifacts](./03-genai-release-artifacts.md)
- [Durable workflows](./04-durable-workflows.md)
- Current demo IaC: `infra/main.bicep` and `infra/gpu-training.bicep`.
