Status: Draft
Owner: ML platform team
Canonical for: Durable workflow orchestration, stage execution, checkpoints, and recovery
Depends on: [production architecture](./00-production-architecture.md), [platform foundation](./01-platform-foundation.md), [reproducible ML](./02-reproducible-ml.md), [GenAI release artifacts](./03-genai-release-artifacts.md)
Last reviewed: 2026-07-29

# 04 — Durable workflows

## Outcome

An operator or CI system can start a Durable orchestration that executes
container stages (training, evaluation, batch inference) as ACA Jobs and
bounded activities against Azure OpenAI, with retries, external-approval pauses,
suspend/resume at checkpoints, and a verifiable result manifest. The correctness
promise is **at most one committed result manifest per stage attempt**.
Provider calls may repeat after a crash; downstream side effects must be
idempotent under the operation key.

## Production decisions

- **Durable Functions is the workflow control plane.** Orchestrators are
  deterministic, versioned, and registered. They never perform network or
  filesystem I/O and never hold document or model bytes. Durable history holds
  compact control state and Blob pointers. Task-hub storage (Azure Storage
  queues/tables/blobs by default) is an implementation detail of the Durable
  extension, not a business broker or application queue.
- **ACA Jobs are the default execution plane for container stages.** Durable
  Functions starts an ACA Job via the Azure management API, records the returned
  execution ID, observes completion (success, failure, timeout), and reads the
  terminal result manifest. Durable Functions never deploys or mutates ACA
  definitions — Bicep owns that.
- **Direct Durable activities** run bounded work: Azure OpenAI calls ≤30–60
  seconds, data validation, manifest hashing, and lightweight computation. Never
  launch an ACA Job per document.
- **No application queue.** Service Bus, Cosmos-ledger, outbox, KEDA queue
  scaling, DLQ, producer/worker, message locks, and reconciliation-as-queue
  requirements are absent. Durable task-hub internals are not a business broker.
- **Blob Storage owns all manifests.** Input manifests, output manifests,
  checkpoint manifests, and result manifests are immutable Blob objects.
  Durable history stores only compact pointers (Blob URI, version ID, SHA-256).
- **At most one committed result manifest.** The stage commit is idempotent.
  A crash after a provider call may repeat the call and its cost, but the
  committed result manifest is written at most once per stage attempt.
- **Chunked batch stages** for larger workloads: an ACA stage processes a
  bounded chunk of documents, writes a partial result manifest, and the
  orchestrator fans out across chunks with bounded internal concurrency. No
  per-document ACA Job.

## Shared concepts

`operation_key` identifies one logical business operation and is stable across
retries. `orchestration_instance_id` identifies one Durable orchestration run.
`stage_id` and `stage_attempt` identify the current stage and its retry number.
`aca_execution_id` is the ACA Job execution ID returned by the start API.
`worker_release_id` identifies the actual release descriptor that a stage
executed under for each attempt.

Derive keys from canonical JSON (sorted keys, normalized strings):

```text
processing_policy_hash = SHA256({
  artifact_blob_uri, artifact_blob_version, model_manifest_digest,
  provider_config_ref, provider_config_digest, contract_version
})
operation_key = SHA256({
  immutable_source_identity, input_sha256, operation_type,
  processing_policy_hash
})
```

The actual implementation must hash the canonical serialized bytes, not this
notation. Every Durable event, manifest, trace, and evaluation record carries
the `orchestration_instance_id`, `operation_key`, and policy hash where safe.

Durable history is the source of truth for control state. ACA execution status
alone is not valid business-result evidence — only the committed result manifest
is. A provider call is at-least-once from the business perspective. For
external effects (email, payment, database writes), pass `operation_key` as the
idempotency key to an idempotent downstream API or use a Durable activity with
a conditional write.

## Pause semantics

- **External approval** uses `waitForExternalEvent` with a timeout. The
  orchestrator pauses scheduling at the next checkpoint and waits for the
  named event payload (approved/rejected + metadata). A timeout without
  approval cancels the orchestration.
- **Suspend/resume** pauses scheduling at the next deterministic checkpoint
  (end of a stage or activity). It does not freeze an in-flight ACA Job or
  activity — the running execution completes before the orchestrator can
  process suspension. Resume replays history from the last committed
  checkpoint and continues scheduling.
- **Emergency cancellation** is distinct and best-effort: the orchestrator
  requests cancellation of any in-flight ACA Job execution (best-effort via
  management API) and transitions to a terminal cancelled state.
- **Workflow graph changes** require a new workflow definition/version. Old
  orchestration instances replay compatible code; incompatible changes deploy
  as a new workflow version and do not affect running instances.

## Target design/contracts

### Azure resource and identity requirements

| Resource | Required production configuration |
|---|---|
| Durable Functions host | Isolated-process Function App with Durable extension, Azure Storage backend for task hub, managed identity, VNet integration if required, diagnostic settings |
| ACA environment | Environment with network integration, managed identity, and diagnostic settings |
| ACA Job definitions | Versioned Bicep-defined Job for each stage (training, evaluation, batch-chunk); min-zero replicas, bounded timeout, managed identity |
| ACA App definition | Versioned Bicep-defined App for online serving (see [05](./05-online-serving.md)) |
| Blob Storage | Separate immutable input/output/checkpoint containers, versioning/soft delete and lifecycle policy, SHA-256/size metadata, no overwrite of committed paths |
| Provider | Environment-specific Azure OpenAI endpoint/deployment/quota configuration, resolved by deployment intent |
| Optional Azure ML | Only after documented admission evidence; workspace, managed tracking, optional zero-min clusters |

Azure workload identities receive least-privilege data-plane roles:

- **Durable host identity:** start/read/cancel ACA Job executions; read input
  Blobs; write output and checkpoint Blobs; invoke Azure OpenAI for bounded
  activities.
- **ACA stage-job identity:** ACR pull; read input Blobs; write output and
  checkpoint Blobs; invoke Azure OpenAI if the stage makes provider calls.
- **ACA online-app identity:** ACR pull; read artifact Blobs at startup (Blob
  version ID + SHA-256 verification); named Key Vault secrets; telemetry write.

### Workflow and stage contract

Every Durable orchestration follows this general structure:

```text
orchestrator (deterministic)
  ├── activity: validate input manifest, derive operation_key
  ├── activity: bounded provider call (≤60s) if applicable
  ├── stage: ACA Job for training/evaluation/chunked batch
  │     ├── start ACA Job -> record execution ID
  │     ├── wait for completion (polling or event)
  │     ├── read result manifest -> verify hashes
  │     └── on failure: retry or fail according to policy
  ├── activity: aggregate results, write checkpoint manifest
  ├── pause for external approval (waitForExternalEvent) [optional]
  ├── stage: next ACA Job [optional]
  └── activity: write terminal result manifest
```

Stage contract JSON stored as checkpoint manifest in Blob:

```json
{
  "schema_version": "1",
  "record_type": "stage-checkpoint",
  "spec": {
    "orchestration_instance_id": "uuid",
    "stage_id": "training",
    "stage_attempt": 1,
    "aca_execution_id": "aca-job-exec-uuid",
    "aca_resource_id": "/subscriptions/.../containerApps/jobs/training",
    "aca_definition_digest": "sha256:...",
    "image_digest": "sha256:...",
    "input_manifest": {"uri": "...", "version_id": "...", "sha256": "...", "byte_length": 12345},
    "output_manifest": {"uri": "...", "version_id": "...", "sha256": "...", "byte_length": 67890},
    "checkpoint_destination": {"uri": "...", "version_id": "...", "sha256": "..."},
    "provider_config_digest": "sha256:...",
    "operation_key": "sha256:...",
    "workflow_version": "<git-sha>",
    "workflow_digest": "sha256:..."
  },
  "digest": "sha256:<canonical-record-digest>",
  "created_at": "2026-07-29T12:00:00Z"
}
```

### Orchestrator flow

1. **Start.** The orchestrator receives inputs: operation type, immutable input
   Blob refs, processing policy (artifact manifest digest, provider config ref),
   and optional overrides. It validates inputs, derives `operation_key`, and
   records the start event in Durable history.
2. **Activity phase (bounded).** Validates input manifest, runs Pandera, hashes
   payloads. If the Azure OpenAI call fits the bounded budget (≤30–60 seconds),
   runs it directly as a Durable activity with timeout and retry policy.
3. **Stage phase (ACA Job).** For larger work, starts an ACA Job by its Bicep-
   deployed definition digest, supplying input/output parameters via environment
   variables or mounted Blob references. Records `aca_execution_id` in history.
   Polls or waits for the terminal ACA Job status.
4. **Result manifest.** The ACA Job writes an immutable result manifest to Blob
   on completion (success or terminal failure). The orchestrator reads the
   manifest, verifies hashes, and records the content digest in history.
5. **Checkpoint.** The orchestrator writes a checkpoint manifest at the end of
   each stage, enabling resume from the last committed stage on recovery.
6. **Approval pause (optional).** If the workflow requires external approval,
   the orchestrator emits a `waitForExternalEvent` and pauses scheduling at the
   current checkpoint. The external system sends an `approval` event with
   approve/reject + metadata.
7. **Repeat.** The orchestrator continues to the next stage or terminates.
8. **Terminal manifest.** On completion, the orchestrator writes a terminal
   result manifest containing the full lineage, output references, evidence
   hashes, and any approval metadata.

### Start ACA Job contract

The orchestrator calls the Azure Container Apps Job execution API:

```text
POST /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.App/jobs/{job-name}/start
```

With a request body containing the stage's environment overrides (input Blob
refs, output destinations, image digest, timeout). The response contains the
`execution ID` that the orchestrator records.

The ACA Job:

1. Reads its input manifest from Blob (supplied as environment variable or
   mounted config).
2. Verifies Blob byte length and SHA-256 before processing.
3. Executes the stage workload (training, evaluation, batch chunk).
4. Writes output and checkpoint manifests to the configured Blob destinations.
5. Exits with exit code 0 (success) or non-zero (failure). The orchestrator
   interprets the exit code and reads the result manifest for detailed status.

### Idempotent stage commit

- The ACA Job writes its result manifest to a deterministic Blob path derived
  from `operation_key`, `stage_id`, and `stage_attempt`.
- The orchestrator checks for an existing manifest before starting a stage
  attempt: if one exists and is valid, it skips execution (idempotent replay).
- The stage-job container is stateless and reads all inputs from Blob.
- A crash after a provider call may repeat the call; the idempotent result
  write ensures at most one committed manifest.

### Retry and timeout

| Parameter | Rule |
|---|---|
| `stage_timeout` | Finite deadline covering the measured stage tail but bounding cost and stuck work |
| `activity_timeout` | Bounded deadline for Durable activity; 60 seconds for direct AOAI calls |
| `retry_policy` | Explicit max attempts, backoff schedule, and classification (transient vs permanent) |
| `orchestration_timeout` | Maximum wall-clock time for the entire workflow |

A permanent failure or exhausted retries transitions the orchestration to a
terminal failed state with a recorded error manifest.

### Concurrency and quota

For token-driven concurrency in batch stages, let `S` be approved tokens/minute
(TPM), `T` the safety fraction (`0 < T < 1`), `L` the target or measured p95
provider latency window in seconds, and `E` measured p95 tokens/request:

```text
chunk_concurrency = floor(S * T * L / (60 * E))
```

If `R` is approved requests/minute, also use
`request_concurrency = floor(R * T * L / 60)` and cap by the smaller nonzero
limit. Measure representative p95 tokens/request and p95 provider latency
before setting `E`, `L`, or chunk size; guessed values do not establish a safe
quota. Apply a token-aware limiter in the stage activity, honor `Retry-After`,
and partition online and batch budgets. A load test must complete the batch
within the agreed window without sustained 429s.

### Checkpoint and recovery

- Checkpoints are written at the end of each stage (deterministic point).
- On host restart or partition, Durable Framework replays history from the
  last checkpoint. Deterministic orchestrators re-execute to reconstruct state.
- If an ACA Job execution was in-flight during a crash, the orchestrator on
  replay either observes the completed execution (result manifest exists) or
  re-starts it (idempotent start with existing manifest check).
- Emergency cancellation is best-effort: the orchestrator requests cancellation
  of in-flight ACA executions and transitions to cancelled. Partial results
  may exist in Blob but are not committed as terminal.
- Resume uses the last committed checkpoint; in-flight activities/stages at
  the time of suspension complete before the checkpoint is persisted.

### External effects idempotency

For email, payment, notification, database writes, or other external effects:

- Pass `operation_key` as the idempotency key to a downstream API that
  supports idempotency.
- Or persist the effect in a Durable activity with a conditional write guard
  (check before create).
- A Durable activity result alone is not proof of external-side-effect
  deduplication; the downstream system must enforce idempotency.

## Runnable demonstration

The current local demonstration is intentionally not the production design:

```text
make up
make train
make worker       # local Celery worker
make beat         # local reconciliation stub
make producer     # synthetic documents
```

The Redis/Celery and SETNX code is a failure-analysis exercise: use
it to discuss duplicate delivery, expiry, and crashes between a sentinel,
provider call, and result write. Unique producer documents and successful
outputs only exercise paths; they do **not** prove Durable orchestration,
ACA stage execution, checkpoint recovery, or provider call idempotency. The
current Bicep is a baseline and does not prove a runnable Azure runtime.

## Production implementation

1. Provision the Durable Functions host with Azure Storage task hub, ACA
   environment and versioned Job/App definitions, Blob containers, identities,
   RBAC, networking, retention, and alerts. Run `az bicep build` for every
   production Bicep entry point.
2. Implement the Durable orchestrator, activities, and stage-start observer.
   Implement checkpoint/result manifest schemas and Blob repositories.
3. Implement the approval event contract (`waitForExternalEvent`), suspend/
   resume at checkpoints, and emergency cancellation.
4. Implement chunked batch stage with bounded concurrency, token-aware
   limiting, and idempotent result commit.
5. Add measured quota-derived scaling and explicit duplicate/crash, checkpoint
   recovery, approval timeout, suspend/resume, and integration tests against
   Azure-provisioned resources.

## Failure modes/acceptance evidence

| Drill | Required evidence |
|---|---|
| Orchestrator crash during stage | Replay observes existing result manifest or re-starts ACA Job; at most one committed result |
| Provider call followed by orchestrator crash | Repeat invocation/cost is allowed; idempotent commit yields at most one result manifest |
| ACA Job killed during execution | Restart with same input produces same result; result manifest is idempotent |
| External side effect retry | Downstream idempotency-key evidence; no duplicate effect |
| Approval timeout | Orchestration cancels within the timeout; no stage is started after timeout |
| Suspend/resume | Suspension pauses after current checkpoint; resume replays correctly and continues |
| Emergency cancellation | In-flight ACA execution is cancelled (best-effort); orchestration transitions to terminal cancelled |
| Payload/hash/policy failure | No provider call or stage start; terminal failure with recorded error manifest |
| Quota storm | Measured p95 inputs, formula, bounded concurrency, and batch completion without sustained 429s |

Acceptance requires Durable orchestration history, checkpoint manifests, Blob
hashes, traces, deployment intent/observation records, and signed
integration/crash-test results. A local producer log or a unique document ID is
not evidence of duplicate safety. A log line alone is never proof of committed
business state.

## Open decisions

- What are the first workload's completion window, input/output retention, PII
  policy, RPO/RTO, and maximum chunk size?
- What is the Durable Functions host plan (Consumption, Flex Consumption, or
  dedicated) based on expected throughput and cold-start tolerance?
- What exact Azure OpenAI deployment/config registry, quota partition, retry
  schedule, stage timeout values, and chunk concurrency are supported by
  measured p95/p99 evidence?
- Which workflow versions require backward-compatible orchestration code, and
  how are incompatible versions deployed?

## References

- [Online serving](./05-online-serving.md)
- [Release and operations](./06-release-and-operations.md)
- [Delivery journey](./07-delivery-journey.md)
- [Production architecture](./00-production-architecture.md)
- [GenAI release artifacts](./03-genai-release-artifacts.md)
