Status: Draft
Owner: ML platform team
Canonical for: GenAI model manifest, evaluator evidence, release inputs, promotion, rollback, and provider upgrades
Depends on: [00 — Production architecture](./00-production-architecture.md), [02 — Reproducible ML](./02-reproducible-ml.md)
Last reviewed: 2026-07-29

# 03 — GenAI release artifacts

## Outcome

Build an immutable, inspectable `mlflow.pyfunc.PythonModel` GenAI artifact from
reviewed Git content, test it against an exact supported MLflow patch, upload it
to immutable Blob storage, evaluate it with independent evidence, and deploy or
roll it back without changing the artifact. Blob digest/version is the canonical
artifact identity; Azure ML registration is optional and only for catalog
discoverability.

## Production decisions

- Prompt and template source is Git. A change requires a reviewed commit and a
  new model manifest/artifact. Runtime uses the bundled content only.
- **Blob artifact identity is canonical.** The artifact is identified by its
  immutable Blob URI, version ID, byte length, and SHA-256. An optional Azure
  ML model catalog reference may be recorded for discoverability but is never
  resolved at runtime or used as the release identity.
- A prompt-as-model is a real `mlflow.pyfunc.PythonModel` artifact tested
  against the exact supported MLflow patch: it contains an `MLmodel` loader and
  `predict` contract, bundled prompt/template files, schemas, and deterministic
  adapter code. Prompt text alone is not a model artifact.
- The evaluator is a separate versioned package that runs as an ACA Job stage.
  It logs aggregate metrics and row-level evidence artifacts. Bounded evaluations
  (≤30–60 second Azure OpenAI calls) may run directly in a Durable activity.
  Evaluation results are not part of the model manifest.
- Only evaluation and explicit release approval determine eligibility to create
  the immutable release descriptor. The descriptor is owned by [06 — Release
  and operations](./06-release-and-operations.md).
- Actual Azure OpenAI deployment names, endpoints, API deployment settings, and
  quota profiles belong to an environment-specific provider configuration. A
  later 06-owned deployment intent references that configuration.
- Azure Container Apps is the default runtime. ACA Apps serve HTTP; ACA Jobs
  run evaluation and batch stages. The release descriptor pins the workflow
  definition digest and ACA definition/image digests, not AML asset references.
- The current `pyproject.toml` `mlflow>=3.0.0` is a separate local-demo
  dependency. Production requires explicit dependency groups and exact tested
  pins, not accidental reuse of the demo environment.
- **Direct Durable activity** may run bounded Azure OpenAI calls (≤30–60 seconds)
  for evaluation or lightweight inference. Larger loads use chunked ACA stages
  with bounded internal concurrency.

## Record ownership and canonical hashing

This document owns the current GenAI model manifest and its canonical hash. The
release descriptor, deployment intent, and deployment-observation event
schemas are owned by [06 — Release and operations](./06-release-and-operations.md).
This document specifies only their required interfaces; it does not copy or
claim ownership of their full schemas. The serving contract remains owned by
[05 — Online serving](./05-online-serving.md).

The model manifest and the 06-owned records are append-only JSON records with
`schema_version`, `record_type`, a deterministic `spec`, `digest`, and any
declared audit metadata. For a record type that declares nondeterministic
envelope fields, compute its digest as:

```text
sha256(UTF-8(canonical_json(record minus "digest" and only the
                                nondeterministic fields declared for that type)))
```

`canonical_json` sorts object keys, uses no insignificant whitespace, uses
normalized JSON numbers, and preserves arrays in their declared semantic order.
The model-manifest `created_at` is declared audit metadata and is omitted from
its digest rather than treated as manifest content. The 06-owned deployment
intent is hashed over its descriptor digest, environment configuration
references, and desired route (plus its other deterministic fields).
Deployment-observation events use a stricter rule:
their `event_sequence`, `observed_at`, outcome, health, failure details, and
observed revision/digests are all included in each event's individual hash.
Timestamps and outcomes are **not** excluded from an observation-event hash.
Each changed observation therefore appends a new event with a new digest; no
mutable deployment attestation is edited in place. The digest is an envelope
value, not a self-hash field inside `spec`.

### 1. GenAI model manifest — owned here

`model-manifest.json` is the current contract for the artifact before
evaluation or release. Its semantic contents are limited to reviewed
prompt/template content and model code, their content hashes, request/response
schemas, logical provider capability/model family/version/API behavior, and
inference parameters. It contains no evaluator or evaluation-data/evidence
references, image digest, actual environment deployment name or endpoint,
quota configuration, provider-configuration digest, mutable alias, or
self-referential artifact hash.

```json
{
  "schema_version": "1",
  "record_type": "genai-model-manifest",
  "spec": {
    "prompt": {
      "source_commit": "<40 hex>",
      "files": [{"path": "prompt/system.txt", "sha256": "<64 hex>"}],
      "templates": [{"path": "prompt/templates/classify.j2", "sha256": "<64 hex>"}]
    },
    "content_hashes": {
      "MLmodel": "<64 hex>",
      "code/adapter.py": "<64 hex>",
      "code/loader.py": "<64 hex>",
      "schemas/request.json": "<64 hex>",
      "schemas/response.json": "<64 hex>"
    },
    "model_code": {
      "files": [
        {"path": "code/adapter.py", "sha256": "<64 hex>"},
        {"path": "code/loader.py", "sha256": "<64 hex>"}
      ],
      "runtime_type": "mlflow.pyfunc.PythonModel"
    },
    "schemas": {
      "request": {"path": "schemas/request.json", "version": "1"},
      "response": {"path": "schemas/response.json", "version": "1"}
    },
    "logical_provider": {
      "provider": "azure-openai",
      "capability": "<stable capability name>",
      "model_family": "<logical model family>",
      "model_version": "<logical/provider model version>",
      "api_behavior": "<stable request-response API behavior>"
    },
    "inference": {
      "parameters": {"temperature": 0, "max_tokens": 512}
    },
    "contract_version": "genai.request-response.v1"
  },
  "digest": "sha256:<64 hex>",
  "created_at": "2026-07-29T00:00:00Z"
}
```

The artifact directory is deterministic and allow-listed:

```text
genai-model/
├── MLmodel
├── model-manifest.json
├── prompt/                 # prompt files and templates
├── schemas/                # request/response schemas
├── code/                   # loader, adapter, and post-processing
└── checksums.sha256        # files listed by content_hashes, not itself/manifest
```

The builder rejects undeclared files, secrets, PII, and runtime configuration.
`checksums.sha256` does not include `model-manifest.json` or itself, avoiding a
file-hash cycle. The model-manifest digest is computed from canonical JSON, not
from a field that points back to itself.

The actual Azure OpenAI deployment name, endpoint, API deployment settings, and
quota profile live in an environment-specific provider configuration with its
own immutable reference/content digest. A 06-owned deployment intent references
that environment configuration. Later, the operation-level processing policy
resolves the exact provider-configuration digest for an operation; neither the
deployment name nor that digest is added to this model manifest.

### 2. Release descriptor — current interface, owned by 06

The release descriptor is created only when the candidate has passed
evaluation and release approval is recorded. Its deterministic `spec` must
consume:

| Required input | Meaning |
|---|---|
| `model_manifest_digest` | Digest of the model manifest above |
| `artifact_blob` | Immutable Blob URI, version ID, byte length, SHA-256 of the artifact. This is the canonical runtime identity |
| `workflow_definition_digest` | Digest of the registered release/promotion workflow definition |
| `aca_definition_digests[]` | ACA Job/App definition digests for each deployment component |
| `image_digests[]` | Immutable ACR image digests, never deployment-only tags |
| `dataset_refs[]` | Dataset manifests with URIs, version IDs, and content hashes |
| `evaluation_evidence[]` | Evidence IDs plus content hashes and evaluator package/version |
| `source_commit` | Repository and source commit used for the release |
| `config_version` | Non-secret release-configuration version and content hash; secret names/references only |
| `provider_config_ref` | Reference/digest for environment-neutral provider behavior metadata |

The descriptor may also carry contract version, approval, and logical provider
version references. It must not point to mutable content. Its complete schema
and promotion ownership are in [06](./06-release-and-operations.md).

### 3. Deployment intent and observation events — interfaces owned by 06

There is no single mutable or partially unhashed environment-deployment record
in this contract. [06 — Release and operations](./06-release-and-operations.md)
owns these two append-only record types:

1. **Hashed deployment intent.** The intent requests deployment of an exact
   `release_descriptor` digest, references the immutable environment-specific
   configuration (including the provider-configuration reference/digest), and
   states the desired route. It records what is requested, not that an ACA or
   approved exception actually succeeded.
2. **Individually hashed deployment-observation event.** Each event has its own
   digest and records the intent, an `event_sequence`, `observed_at` timestamp,
   outcome, health/failure details, and observed revision/digests. Events may
   record progress, success, or failure and never rewrite an intent, release
   descriptor, or prior event.

The complete operational schemas remain owned by 06; [05](./05-online-serving.md)
owns API/readiness behavior.

## Evaluator package and evidence contract

The evaluator is a separate package with a package name, exact version, source
commit, content hash, thresholds version, and dependency lock. It runs as an
ACA Job stage (or a Durable activity for bounded evaluations) and must:

1. Read exact smoke, golden, release, or approved feedback assets and the exact
   artifact's Blob manifest/model-manifest digest.
2. Emit stable `row_id` values and deterministic checks before any optional
   judge-model call.
3. Log aggregate metrics including `eval/rows`, `eval/pass_rate`,
   `eval/failure_rate`, `eval/invalid_output_rate`,
   `eval/safety_violation_rate`, and `eval/latency_p95_ms` (plus token/cost
   metrics when available).
4. Log row-level artifacts such as `evaluation/rows.jsonl`,
   `evaluation/failures.jsonl`, and `evaluation/schema.json`. Each row has the
   row ID, dataset hash, model-manifest/artifact hash, provider/API version,
   verdict, failure category, output hash, latency, token counts, and trace ID.
   Raw input/output is omitted unless classification and retention explicitly
   allow it.
5. Record evaluator version/commit, thresholds, seed, judge version if used,
   and redaction status as metadata.

Missing metrics/evidence or a threshold violation is fail-closed. The resulting
evidence ID/content hash is an input to the release descriptor, never an edit
to the model manifest.

## Promotion, provider upgrade, and rollback

1. A reviewed Git change builds the deterministic model artifact and manifest;
   CI performs secret/sensitivity, schema, artifact, and exact
   `mlflow.pyfunc.PythonModel` compatibility checks with the supported
   MLflow patch.
2. The artifact is uploaded to an immutable Blob path. Its URI, version ID,
   byte length, and SHA-256 are recorded in the artifact manifest. Optional
   Azure ML catalog registration may follow for discoverability but is not the
   runtime identity.
3. The separate evaluator runs as an ACA Job stage (or bounded Durable activity)
   against the exact artifact and writes aggregate metrics and row-level
   evidence. CI verifies hashes, thresholds, and required evidence.
4. Only after evaluation passes and release approval is recorded may the
   release descriptor be created. The descriptor is owned by 06 and references
   exact workflow definition digest, ACA definition/image digests, Blob artifact
   refs, and evidence.
5. A 06-owned deployment intent references the descriptor digest, environment
   configuration/provider-configuration digests, and desired route. Deploy its
   exact ACA definitions and images, then append individually hashed observation
   events.
6. Smoke tests verify schemas, model-manifest digest, logical provider/API
   behavior, the resolved provider-configuration digest, readiness, and
   telemetry before traffic or stage triggers are enabled.
7. Rollback redeploys the prior complete release descriptor through a new
   deployment intent and records new observation events. It never mutates a
   model artifact or descriptor.

For an Azure OpenAI upgrade, provision a separately versioned deployment,
compare the unchanged artifact on the release set, review correctness/safety/
latency/token regressions, build a new model manifest when behavior or provider
metadata changes, evaluate it, and promote only with a new descriptor. Keep the
prior descriptor as the recovery point.

## Data sensitivity

| Classification | Default allowed | Required handling |
|---|---|---|
| Public | Prompt text and redacted examples | Secret scan and checksum |
| Internal | IDs, hashes, aggregate metrics, approved redacted rows | Entra/RBAC, retention, and audit |
| Confidential | Metadata and redacted evidence | Private-network gate, approved store, explicit retention |
| Restricted/PII | No raw content in Git, image, artifact, MLflow metadata, or logs | Tokenized IDs, redaction, approved private store, deletion procedure |

Runtime secrets and environment values remain in Key Vault/deployment
configuration. A failed sensitivity or secret scan blocks the artifact.

## Current implementation versus planned

**Existing, local demo stack only:** `producer.py` passes literal
model/prompt fields; `tasks.py` simulates inference; Docker Compose uses local
MLflow 3 and Redis/Celery; training is synthetic/Pandera-backed; and Bicep is a
demo.
There is no real Azure OpenAI call, `mlflow.pyfunc.PythonModel` release
artifact, evaluator package, Durable orchestration, ACA stage, or production
deployment intent/observation path.

**Planned:** the builder, immutable Blob artifact identity, separate
evaluator running as ACA stage or Durable activity, 06-owned release
descriptor/deployment intent/observation events, environment provider
configuration, provider upgrade comparison, and exact rollback workflow.
Production workflow definitions, ACA stages/apps, and CI remain planned.

## Runnable demonstration

```text
cd projects/ml-platform
make up
make worker       # separate terminal
make producer     # separate terminal
```

This demonstrates local Redis/Celery task fields, retry/late-ack semantics,
and synthetic idempotency only. It does not prove Durable orchestration, ACA
stages, Blob artifact identity, evaluation evidence, or ACA release behavior.

## Failure modes/acceptance evidence

| Acceptance test | Pass condition/evidence |
|---|---|
| Artifact determinism | Same Git/input set yields the same allow-listed files, content hashes, and canonical manifest digest |
| Manifest boundary | Manifest contains prompt/model code, content hashes, request/response schemas, logical provider capability/model family/version/API behavior, inference parameters, and contract version, but excludes evaluator/data/evaluation evidence, image digest, actual environment deployment/endpoint/quota config, mutable aliases, and self-reference |
| Artifact identity | Blob URI, version ID, byte length, and SHA-256 are recorded and verifiable; optional AML catalog reference is secondary |
| Evaluator evidence | Separate package/version logs all required aggregate metrics and row-level artifacts with hashes/redaction metadata; runs as ACA stage or Durable activity |
| Release ordering | No release descriptor exists before evaluation evidence and approval; descriptor fields resolve to immutable inputs |
| Deployment intent/events | 06-owned hashed intent names the descriptor digest, environment/provider configuration refs, and desired route; each individually hashed observation event includes sequence, observed timestamp, outcome/health/failure, and revision/digests |
| Secret boundary | Secrets and forbidden raw data are absent from artifact, image, MLflow metadata, logs, and records |
| Runtime smoke | Default ACA App returns schema-valid output and reports exact manifest/artifact/config references |
| Rollback | Prior descriptor redeploys within the target budget without artifact mutation |

## Open decisions

- Set metric thresholds, sample sizes, and human-review ownership per use case.
- Decide whether judge-model calls are allowed by classification and set their
  private-network and token-budget requirements.
- Confirm Azure OpenAI deployment naming and ACA canary mechanism.
- Set retention overrides for artifact/evidence Blobs with data owners.

## References

- [Production architecture](./00-production-architecture.md)
- [Platform foundation](./01-platform-foundation.md)
- [Reproducible ML](./02-reproducible-ml.md)
- [Durable workflows](./04-durable-workflows.md)
- [Online serving](./05-online-serving.md)
- [Release and operations](./06-release-and-operations.md)
- Current demo code: `src/ml_platform/tasks.py` and `producer.py`.
