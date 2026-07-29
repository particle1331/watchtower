Status: Draft
Owner: ML platform team
Canonical for: Dataset, stage, compute, artifact, evaluation-input, and lineage contracts
Depends on: [00 — Production architecture](./00-production-architecture.md), [01 — Platform foundation](./01-platform-foundation.md)
Last reviewed: 2026-07-29

# 02 — Reproducible ML

## Outcome

A training or evaluation run can be recreated from Git, an immutable Blob
manifest, a pinned ACA Job definition/image, a Durable orchestration instance
recording stage attempts, and explicit parameters. A candidate artifact cannot
be promoted without lineage and evidence.

## Production decisions

- **ACA Jobs are the default training/evaluation plane.** Every stage runs as an
  ACA Job with a pinned definition digest and image digest. CPU is the default;
  optional GPU Jobs require documented admission evidence. All Jobs have minimum
  capacity `0`.
- **Manifests drive stages.** Blob manifests are the single source of truth for
  dataset identity, schema, checksums, and validation evidence. Blob digest/
  version is canonical — no Azure ML data assets are required.
- **Durable Functions records lineage.** Every stage is started by a Durable
  orchestrator. The orchestration instance ID, stage ID, attempt number, ACA
  Job execution ID, definition digest, and image digest form the lineage chain.
- **Azure ML is optional.** Optional managed MLflow tracking and model-catalog
  references; optional zero-minimum CPU/GPU clusters after documented admission
  evidence showing distributed/RDMA or specialized GPU/capability ACA cannot
  satisfy. No baseline AML jobs, pipelines, endpoints, data assets, or model
  assets as runtime identity.
- **Pandera runs at dataset creation and immediately before each consuming
  stage.**
- **The custom evaluator** is a separately versioned package that runs as an ACA
  Job stage. Its aggregate and row-level evidence contract is owned by
  [03](./03-genai-release-artifacts.md).
- **Direct Durable activity** may run bounded Azure OpenAI calls (≤30–60
  seconds) for lightweight evaluation; larger evaluation loads use ACA stages.

## Shared concepts

- **Dataset manifest:** machine-readable source, schema, checksums, row count,
  classification, and validation evidence stored beside immutable Blob payloads.
- **Stage lineage:** Git SHA → image/environment → Bicep definition digest →
  Durable orchestration instance → stage ID/attempt → ACA Job execution ID →
  input Blob manifest → output artifact manifest → evaluation evidence →
  release descriptor.
- **Stage identity:** `workflow_id`, `workflow_version`, `orchestration_instance_id`,
  `stage_id`, `stage_attempt`, `aca_execution_id`, `aca_resource_id`,
  `aca_definition_digest`, `image_digest`.
- **Dataset roles:** smoke for wiring, golden for curated regression, release
  for a frozen decision set, and feedback for separately governed production
  samples. A role may have many immutable versions.

## Target design/contracts

### Dataset manifest

Store the manifest beside immutable payloads, for example
`datasets/<dataset-name>/<version>/manifest.json`. The version may be a
content hash or approved semantic version, but the payload path is never
replaced.

```json
{
  "manifest_schema_version": "1",
  "dataset_name": "classifier-training",
  "dataset_version": "2026-07-29.sha256-abcd",
  "created_at": "2026-07-29T00:00:00Z",
  "source": {"system": "approved-source", "extract_code_sha": "<git-sha>"},
  "files": [
    {"uri": ".../part-000.parquet", "sha256": "<64 hex>", "rows": 1000, "bytes": 123456}
  ],
  "total_rows": 1000,
  "schema_name": "TrainingFeaturesSchema",
  "schema_version": "1",
  "classification": "internal",
  "pandera": {"package_version": "<tested-pin>", "status": "passed", "report_uri": "..."}
}
```

Rules:

1. Write payloads, calculate each file checksum, run Pandera, and write the
   manifest last. A partial or failed extraction is not an asset.
2. Verify checksums before stage input materialization.
3. Record the immutable Blob URI, version ID, and SHA-256 in the Durable
   orchestration history and output manifest.
4. Keep restricted content out of the manifest. Classification and references
   are required; access remains in the approved data plane.

### Stage and compute contract

Stage definitions live in Bicep and are deployed with an immutable definition
digest. A Durable orchestrator starts a stage by referencing its definition and
supplying input/output parameters:

```yaml
stage: train-or-evaluate
workflow_version: <workflow-definition-git-sha>
definition_digest: <bicep-definition-digest>
image_digest: <acr-image-digest>
compute: aca-job-cpu-cluster
inputs:
  input_manifest: <blob-uri-version-hash>
  manifest_sha256: <hash>
outputs:
  output_manifest_destination: <blob-path>
  checkpoint_destination: <blob-path>
parameters: <non-secret JSON>
timeout: 3600
retry_classification: transient
```

| Profile | Use | Capacity rule |
|---|---|---|
| `cpu-stage` | Training and smoke/golden/release evaluation in ACA Jobs | Min `0`, initial max `2` |
| `gpu-stage` | Approved fine-tuning or GPU evaluation (admission required) | Separate approved SKU; min `0`, initial max `1` |

Stages pin code/image digest, Python/dependency lock, random seeds, parameters,
input manifests, and output destinations. A retry creates a new stage attempt
within the same orchestration instance, retaining the same input references and
parent attempt ID.

### Artifact registration

Artifacts are identified by immutable Blob digest/version. An optional Azure ML
catalog reference may be recorded for discoverability but is not the runtime
identity:

```text
build deterministic model/artifact directory
  -> upload to immutable Blob path
  -> record Blob URI, version ID, byte length, SHA-256 in manifest
  -> (optional) register in Azure ML model catalog for discoverability
  -> run evaluation stage
  -> create release descriptor only when evaluation passes
```

For a prompt-as-model, the directory contains an actual
`mlflow.pyfunc.PythonModel`, its `MLmodel` loader and `predict` contract, not
only prompt text or a tracking URI. The exact patch compatibility test must
load the candidate and exercise its contract before the evaluator uses it. The
complete artifact/model-manifest contract is owned by
[03](./03-genai-release-artifacts.md).

### Run lineage contract

Every orchestration records these identifiers in Durable history:

`workflow_id`, `workflow_version`, `workflow_digest`, `orchestration_instance_id`,
stage IDs and attempt counts, ACA execution IDs, ACA resource IDs and definition
digests, image digests, environment lock hashes, compute profile, input dataset
manifest URIs/version/hashes, schema/Pandera version and status, random seed,
parameters, parent/attempt IDs, Blob artifact URI/version/hash, evaluator
package/version when applicable, evaluation dataset manifests, model-manifest
digest when applicable, provider model/API version when applicable,
configuration version, initiator, approval, and timestamps.

Required output artifacts include the copied manifest/checksum, validation
report, parameters, metrics, model signature, dependency metadata, and
evaluation-stage report. Row-level evaluation evidence follows
[03](./03-genai-release-artifacts.md) and is not copied into this generic
contract by default.

## Current implementation versus planned

**Existing, local demo stack only:** `train.py` creates 200 synthetic rows
with a fixed seed; `validate.py` uses Pandera; `model_pipeline.py` packages
preprocessing in a scikit-learn pipeline; and local MLflow 3 logs the model.
The score is a training-set metric, not production evaluation.

**Planned:** immutable Blob extraction/manifests, ACA Job stage definitions,
Durable-orchestrated training/evaluation, real train/validation/test evaluation,
immutable Blob-based artifact identity, the separate evaluator package, and CI
lineage gates. Production ACA stage definitions, workflows, and CI remain
planned; Durable Functions, ACA Jobs/Apps, and direct AOAI activities do not
exist in this demo.

## Runnable demonstration

```text
cd projects/ml-platform
make up
make train
```

This demonstrates deterministic synthetic data, schema validation, a packaged
scikit-learn model, and local MLflow 3 logging. It does not prove immutable
Blob manifests, ACA Job stages, Durable orchestration, or a production
evaluation.

## Production implementation

1. Implement a versioned extractor that writes immutable Blob payloads and the
   manifest; run Pandera at extraction and stage-input boundaries.
2. Build ACA Job stage definitions for validation, training, packaging, and
   evaluation. Add GPU only after documented admission.
3. Implement Durable orchestrators that start stages, record lineage, observe
   execution, and read result manifests.
4. Create explicit production dependency groups/lock data with exact tested
   pins.
5. Build and compatibility-test conventional or actual
   `mlflow.pyfunc.PythonModel` artifacts, upload to immutable Blob storage, and
   emit the lineage inputs required by [03](./03-genai-release-artifacts.md).
   Create a release descriptor only after evaluation and release approval.
6. Run smoke stages in CI and golden/release evaluation before environment
   approval; retain instance IDs, execution IDs, manifests, hashes, and reports.

## Failure modes/acceptance evidence

| Acceptance test | Pass condition/evidence |
|---|---|
| Manifest integrity | Payload alteration fails checksum and stage admission; unchanged input reproduces the same manifest hash |
| Immutability | Existing Blob versions cannot be overwritten; changed data receives a new path/version |
| Pandera gate | Invalid schema, duplicate ID, null, or invalid label fails extraction and pre-stage validation |
| Stage reproducibility | Re-run records equal code/image, manifest, parameter, and seed values and comparable outputs |
| Plane/compute | Stage uses declared ACA Job profile with min `0`; GPU requires admission evidence |
| Durable lineage | Orchestration instance ID, stage IDs, ACA execution IDs, definition digests, image digests, and manifests resolve |
| Release eligibility | Candidate artifact alone does not create a release descriptor; evaluator evidence and explicit release approval are both required |
| Lineage completeness | Git, image/lock, data manifest/checksum, parameters, output artifact, and evaluator evidence resolve |
| Evaluation separation | Smoke, golden, release, and feedback versions remain distinct |

Evidence is the Durable orchestration history, ACA execution record, copied
manifest/checksum, Pandera report, artifact Blob metadata, and CI result — not
a screenshot alone.

## Open decisions

- Choose each source-system extraction mechanism and schedule.
- Approve schema evolution and threshold ownership/minimum sample sizes.
- Confirm the first CPU SKU (ACA Job profile) and stage timeout values.
- Define feedback-label collection, redaction, trace linking, and admission to
  a future release dataset.

## References

- [Production architecture](./00-production-architecture.md)
- [Platform foundation](./01-platform-foundation.md)
- [GenAI release artifacts](./03-genai-release-artifacts.md)
- [Durable workflows](./04-durable-workflows.md)
- Current demo implementation: `src/ml_platform/train.py`, `validate.py`,
  and `model_pipeline.py`.
