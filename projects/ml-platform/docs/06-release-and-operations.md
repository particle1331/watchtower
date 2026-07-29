Status: Draft
Owner: ML platform team
Canonical for: Release engineering, production operations, and service ownership
Depends on: [production architecture](./00-production-architecture.md), [platform foundation](./01-platform-foundation.md), [reproducible ML](./02-reproducible-ml.md), [GenAI release artifacts](./03-genai-release-artifacts.md), [durable workflows](./04-durable-workflows.md), [online serving](./05-online-serving.md)
Last reviewed: 2026-07-29

# 06 — Release and operations

## Outcome

Every production deployment is approved, reproducible, and traceable to exact
code, image bytes, workflow definitions, ACA definitions, Blob artifacts,
contracts, configuration, tests, and an operator. The release record sequence
separates the immutable release descriptor, the hashed deployment intent, and
individually hashed deployment-observation events. Rollback selects a
known-compatible descriptor and creates a new intent and observation sequence;
it does not edit a release artifact or use telemetry as business state.

## Production decisions

- **Release and promotion is a registered Durable workflow.** CI builds
  immutable artifacts and Bicep definitions, then starts the pinned release-
  promotion workflow and waits for its completion or failure. Production
  approval is an external event (`waitForExternalEvent`) so CI does not block.
- `main` is protected. Changes arrive by pull request with code-owner review;
  direct pushes, force pushes, and unreviewed production changes are disabled.
- **CI identity:** GitHub Actions authenticates with OIDC to a federated Entra
  application/service principal. It has separate least-privilege test and
  production permissions and no long-lived Azure secret. **Managed identities
  are for Azure workloads** such as Durable host, ACA Jobs, and ACA Apps, not
  for GitHub Actions.
- Pull requests run formatting, lint, type, unit/contract, secret, dependency,
  IaC, and deterministic evaluation checks. A release adds integration, image,
  artifact/startup, quota, workflow, and rollback checks.
- The merge workflow builds once, publishes the digest to ACR, runs `az bicep
  build` for every production Bicep entry point, and produces the candidate
  records below. It never rebuilds different bytes for test and production.
- Container Apps is the default online and batch runtime. ACA Jobs run offline
  stages; ACA Apps serve HTTP traffic. No Functions or Azure ML managed online
  endpoints serving alternatives exist.
- The release descriptor pins the workflow definition digest, ACA definition
  digests, image digests, artifact Blob refs, and config — not AML model assets.
- ACR images are scanned and deployed by immutable digest. Tags are human
  conveniences only.
- Business status and result references remain in Durable orchestration history
  and immutable Blob manifests. Logs, traces, evaluations, and dashboards are
  evidence.

## Shared concepts

`git_sha` identifies source, `image_digest` identifies executable bytes, the
GenAI model manifest identifies prompt/model code, templates, schemas, and
environment-neutral behavior/provider metadata, and `contract_version`
identifies compatibility. `release_id` identifies an immutable release
descriptor. `workflow_definition_digest` identifies the exact release-promotion
workflow version.

The release descriptor contains separate dataset and evaluator-evidence inputs.
Its release approval is approval of that immutable set of contents. A
deployment intent is a separate hashed record for one environment promotion;
it references the descriptor digest, environment and provider configuration
references, desired routes, and the test/prod promotion approval. The resulting
deployment-observation events are append-only evidence. SLOs have one named
owner and deputy; alerts link to a runbook and an evidence query.

## Target design/contracts

### Branch, CI, and supply-chain gates

Repository rules require a PR, code-owner review, green required checks, and an
up-to-date branch. Required checks are:

1. Markdown/link validation and JSON/schema validation.
2. Python format/lint/type checks and unit tests.
3. API, message, output, and compatibility contract tests, including
   invalid and unknown fields.
4. Disposable-service integration tests and deterministic model/prompt
   evaluation with synthetic or redacted data.
5. Secret/dependency/license scans, `az bicep build`, container build, SBOM,
   image scan, and digest/provenance verification.

The merge workflow builds once, publishes the digest to ACR, runs `az bicep
build` for every production Bicep entry point, and produces the candidate
records below. It never rebuilds different bytes for test and production.

### Workload identity and RBAC

Each GitHub `test` and `prod` Environment has a federated credential on the
Entra application/service principal restricted by repository, branch/event, and
environment claims. `azure/login` obtains a short-lived token for CI deployment
and verification. Azure workloads use their own system- or user-assigned
managed identity with least-privilege roles for Blob, Key Vault, ACR, ACA,
Durable host, Azure OpenAI, and optional Azure ML tracking. A CI service
principal is not substituted for a Durable host or ACA workload identity at
runtime.

Build images from pinned inputs, emit an SBOM, scan/sign or attest provenance,
and deploy as `repo@sha256:<digest>`. Deployment verifies both the approved
descriptor and the running revision's reported digest/release ID.

### Release and promotion workflow

The release-promotion Durable orchestrator follows this sequence:

1. **Build and register phase (CI).** CI merges to protected `main`, runs gates,
   builds once, scans/signs, produces the `mlflow.pyfunc.PythonModel` artifact,
   uploads it to immutable Blob, and runs `az bicep build`.
2. **Release workflow start (CI).** CI starts the pinned release-promotion
   Durable workflow with the candidate artifact Blob refs, Bicep definition
   digests, image digests, and evaluation evidence. CI records the
   `orchestration_instance_id` and waits for the workflow to complete (or fail).
3. **Evaluation stage.** The workflow runs the evaluator as an ACA Job stage (or
   bounded Durable activity). The evaluator writes aggregate metrics and row-
   level evidence to Blob.
4. **Release descriptor creation.** After evaluation passes, the workflow
   creates the immutable release descriptor joining the model-manifest digest,
   artifact Blob refs, workflow definition digest, ACA definition digests, image
   digests, dataset refs, evaluation evidence, source commit, and config version.
   Release approval is recorded in the descriptor.
5. **Test deployment.** The workflow creates a hashed test deployment intent
   with the descriptor digest, isolated test environment/provider configuration
   references, and desired routes. It deploys Bicep definitions by digest and
   appends individually hashed observation events while running startup, API,
   workflow contract, quota, and telemetry tests.
6. **Production approval pause.** The workflow pauses via `waitForExternalEvent`
   for production promotion approval. CI does not block — the external reviewer
   sends the approval event (approved/rejected + metadata). A timeout without
   approval cancels the production promotion.
7. **Production deployment.** After approval, the workflow creates a separate
   hashed production deployment intent with the same release descriptor digest,
   production environment/provider configuration references, and desired routes.
   It deploys the same definition and image digests, appends observation events,
   verifies readiness, and enables traffic.
8. **Rollback.** Rollback selects the previous compatible descriptor, verifies
   artifact availability, obtains the applicable environment promotion approval,
   creates a new rollback intent, and appends its observation events.

### Release record sequence

Do not collapse these records into a mutable or self-referential release
manifest. The sequence is:

1. **GenAI model manifest — defined by [03 — GenAI release artifacts](./03-genai-release-artifacts.md).**
   The immutable model artifact's manifest records only prompt/model code,
   templates, schemas, environment-neutral behavior/provider metadata, and
   their hashes. The artifact is identified by its immutable Blob URI, version
   ID, byte length, and SHA-256.
2. **Release descriptor — created after evaluator pass and release approval.**
   It references the exact model-manifest digest, artifact Blob refs, workflow
   definition digest, ACA definition/image digests, contracts, separate dataset
   references, separate evaluator evidence, and the release approval. Once
   issued, its body is immutable.
3. **Deployment intent — created for each test, production, or rollback
   promotion.** This is an individually hashed record referencing the release
   descriptor digest, environment-configuration references, actual provider-
   configuration references, desired routes, and the environment promotion
   approval.
4. **Deployment-observation events — appended for each deployment event.** Each
   event is individually hashed and records its event sequence/timestamp, actual
   revision and image digests, health, outcome, and failure reason.

Minimum release descriptor (`release-descriptor.v1`), using the common envelope
and canonical digest rule defined by 03:

```json
{
  "schema_version": "1",
  "record_type": "release-descriptor",
  "spec": {
    "release_id": "rel-2026-07-29.abc123",
    "source_commit": {"repository": "particle1331/watchtower", "git_sha": "abc123..."},
    "model_manifest_digest": "sha256:...",
    "artifact_blob": {"uri": "https://<account>.blob.core.windows.net/artifacts/genai-classifier/17", "version_id": "2026-07-29T12:00:00Z.1234", "byte_length": 1048576, "sha256": "..."},
    "workflow_definition_digest": "sha256:...",
    "aca_definition_digests": [
      {"component": "online", "digest": "sha256:..."},
      {"component": "training", "digest": "sha256:..."},
      {"component": "evaluation", "digest": "sha256:..."},
      {"component": "batch", "digest": "sha256:..."}
    ],
    "image_digests": [
      {"component": "online", "reference": "mlplatform.azurecr.io/online@sha256:..."},
      {"component": "batch", "reference": "mlplatform.azurecr.io/batch@sha256:..."}
    ],
    "dataset_refs": [{"name": "golden", "version": "2026-07-28.2", "manifest_sha256": "..."}],
    "contracts": {"api_version": "v1", "workflow_contract_version": "1.0", "output_schema_version": 1},
    "config_version": {"name": "release-behavior-v1", "sha256": "..."},
    "behavior": {"capability": "document-classification", "provider": "azure-openai", "model_family": "<model family>", "provider_model_version": "<provider version>", "api_version": "<pinned API version>", "parameters_sha256": "..."},
    "evaluation_evidence": [{"id": "orchestration-instance-id", "sha256": "..."}],
    "evidence": {"test_report_uri": "https://...", "image_scan_uri": "https://..."},
    "release_approval": {"approver": "release-owner", "decision": "approved", "change_ref": "pr-123", "approved_at": "2026-07-29T12:30:00Z"}
  },
  "digest": "sha256:<canonical-record-digest>",
  "created_at": "2026-07-29T12:30:00Z"
}
```

The JSON above is illustrative; the implementation must validate exact schema,
hashes, evidence, and release approval. `config_version` is release-level,
environment-neutral configuration. Environment-specific provider deployment
and quota are not in this descriptor; they belong in deployment intent. The
envelope `digest` is computed over canonical record bytes excluding `digest`
and declared audit timestamps.

Minimum deployment intent (`deployment-intent.v1`):

```json
{
  "schema_version": "1",
  "record_type": "deployment-intent",
  "spec": {
    "intent_id": "intent-2026-07-29.prod.4",
    "release_descriptor": {"release_id": "rel-2026-07-29.abc123", "digest": "sha256:<canonical-record-digest>"},
    "environment": "prod",
    "environment_config_refs": [{"name": "aca-prod", "version": "prod-7", "sha256": "..."}],
    "provider_config_refs": [{
      "provider": "azure-openai",
      "ref": "aoai-config/classify-prod-v2",
      "version": "2",
      "sha256": "provider-config...",
      "endpoint": {"ref": "aoai-endpoint/prod", "version": "7", "sha256": "..."},
      "deployment": {"ref": "aoai-deployment/classify", "version": "17", "sha256": "..."},
      "quota_profile": {"ref": "aoai-quota/classify-prod", "version": "2", "sha256": "..."}
    }],
    "desired_routes": {"online_route": "api-prod", "workflow_stage": "batch"},
    "promotion_approval": {"approver": "github-prod-reviewer", "decision": "approved", "change_ref": "pr-123", "approved_at": "2026-07-29T12:35:00Z"}
  },
  "digest": "sha256:<canonical-intent-digest>",
  "created_at": "2026-07-29T12:35:00Z"
}
```

Minimum deployment observation event (`deployment-observation.v1`):

```json
{
  "schema_version": "1",
  "record_type": "deployment-observation",
  "spec": {
    "observation_id": "obs-2026-07-29.prod.4.2",
    "deployment_intent": {"intent_id": "intent-2026-07-29.prod.4", "digest": "sha256:<canonical-intent-digest>"},
    "event_sequence": 2,
    "observed_at": "2026-07-29T12:42:00Z",
    "observed_revision": "api--abc",
    "observed_image_digests": ["sha256:..."],
    "observed_aca_definition_digests": [{"component": "online", "digest": "sha256:..."}],
    "health": {"status": "healthy", "ready": true},
    "outcome": "succeeded",
    "failure_reason": null
  },
  "digest": "sha256:<canonical-observation-digest>"
}
```

All four record types use 03's canonical JSON rules: sorted object keys,
normalized values, semantic array order, and an envelope `digest` computed over
the canonical record with that record's own `digest` removed. Descriptor and
intent audit timestamps may use 03's declared audit-field exclusion. In
contrast, `event_sequence`, `observed_at`, `observed_revision`,
`observed_image_digests`, `health`, `outcome`, and `failure_reason` are the facts
of an observation event and are included in its hash.

### Telemetry, SLOs, and ownership

Emit structured logs and OpenTelemetry traces to Application Insights/Log
Analytics with trace/correlation IDs, `orchestration_instance_id`,
`release_id`, service, contract, outcome, and duration. Default to metadata and
redaction; payload capture requires an approved privacy policy.

| Service | Starting SLO | Owner/dashboard |
|---|---|---|
| Online API | 99.5% successful authorized requests/month; p95 under approved budget | Online owner: rate, p95/p99, 4xx/5xx/429, readiness |
| Workflow execution | 99% of accepted orchestrations terminal inside the agreed window; zero silent loss | Workflow owner: instance age, stages, attempts, approvals, throughput |
| Release | Compatible rollback under 15 minutes; every deployment descriptor-verified | Platform owner: workflow, versions, smoke/rollback |
| Control plane | Approved Durable host, Blob, ACA, and provider targets | Platform owner: access, service errors, restore, identity |

Alert on API failure/readiness, orchestration failure/stuck activity, ACA
execution errors, checkpoint failures, provider throttling/quota, missing
telemetry, scan policy violations, Blob capacity, backup failure, Azure service
incidents, and cost thresholds. Dashboards distinguish application failure
from provider/Azure platform failure.

### Runbooks, recovery, and capacity

Keep versioned runbooks for:

- ACA App readiness and rollback
- Stuck Durable activity or orchestration
- ACA Job execution failure
- Checkpoint manifest corruption or missing
- Suspend/resume and emergency cancellation
- Provider quota exhaustion and Azure OpenAI throttling
- Bad release or rollback
- Identity or Key Vault access failure
- Blob corruption, version recovery, or deletion
- Durable task-hub recovery (storage account failover, replay troubleshooting)
- Azure service incidents (Durable host, ACA, Blob, Azure OpenAI)

Recovery tests cover:

- Durable task-hub restore and replay integrity
- Blob version/recovery with manifest hash verification
- ACA definition redeployment from Bicep
- Identity permission restoration
- Exact artifact availability and deployment-intent/observation integrity

Define RPO/RTO before production. Capacity records measured p95 tokens/latency,
quota, ACA concurrency/replicas, orchestration throughput, storage growth, and
a 2x-peak forecast.

## Runnable demonstration

The repository currently contains a local MLflow/Postgres/MinIO/Redis compose
stack and Bicep demo baselines. The local training and Celery commands in
[07 — Delivery journey](./07-delivery-journey.md) are local demo exercises only.
There is no CI workflow, release descriptor generator, Durable release
workflow, production ACA serving, or managed deployment intent/observation path
today. A local green build and the current Bicep declarations do not prove a
runnable Azure runtime.

The implementation target is a Durable release workflow that validates the
candidate artifact, evaluator inputs, immutable descriptor, creates hashed test
intent/events, pauses for production approval via external event, creates hashed
production intent/events, deploys exact ACA definitions, and records every
observation event.

## Production implementation

1. Add repository rules, code owners, GitHub Environment protection, OIDC
   federated Entra application/service-principal credentials, and least-
   privilege Azure workload identities.
2. Implement schemas and validators for the GenAI model manifest reference,
   immutable release descriptor, hashed deployment intent, individually hashed
   deployment-observation events, and workflow definition digests.
3. Implement the Durable release-promotion orchestrator: evaluation stage,
   release descriptor creation, test deployment, production approval pause via
   `waitForExternalEvent`, production deployment, and rollback.
4. Implement PR/release workflows, deterministic builds, SBOM/signing/scanning,
   digest promotion, and evidence storage.
5. Implement test deployment and startup/contract/quota/workflow/integration
   checks; create deployment intents and observation events.
6. Implement production approval, compatibility-aware rollback, Azure service
   incident handling, orchestration runbooks, dashboards, budgets, backups, and
   restore drills.

## Failure modes/acceptance evidence

| Failure/drill | Required evidence |
|---|---|
| OIDC claim/permission failure | Federated Entra app/service principal fails safely without a static secret; workload RBAC remains separate |
| Vulnerable image or mutable tag | Promotion blocks; running revision reports the approved digest |
| Artifact/config/definition mismatch | Descriptor validation or workflow startup fails closed |
| Evaluation failure | Release descriptor is not created; workflow transitions to terminal failed |
| Test passes, prod approval absent | Workflow pauses on `waitForExternalEvent`; no production deployment |
| Production approval timeout | Workflow cancels production promotion; no change is deployed |
| Bicep drift/syntax | `az bicep build` passes for every production entry point and the deployment intent/events reference the deployed template/version |
| Azure deployment | Provisioned integration test reaches Blob, ACA, Durable host, and Azure OpenAI; records identities, definitions, hashes, and outcomes |
| Orchestration stuck on activity | Runbook detects stuck activity; operator can terminate, recover checkpoint, or restart |
| Rollback | Previous compatible descriptor redeploys under a new approved intent and individually hashed observation events capture the result |
| Checkpoint/Blob restore | References and hashes verify after restore; signed RPO/RTO report exists |

## Open decisions

- Who are the primary/deputy owners and approvers for online, workflow, Durable
  host, identity, cost, and Azure service incidents?
- Which GitHub-hosted or approved self-hosted runners, signing service,
  scanner policy, and retention satisfy organizational controls?
- What are the final SLO, RPO/RTO, retention, privacy, cost, and quota budgets?
- What is the Durable release workflow's orchestration timeout and approval
  wait duration?

## References

- [Durable workflows](./04-durable-workflows.md)
- [Online serving](./05-online-serving.md)
- [Delivery journey](./07-delivery-journey.md)
- [Production architecture](./00-production-architecture.md)
- [GenAI release artifacts](./03-genai-release-artifacts.md)
