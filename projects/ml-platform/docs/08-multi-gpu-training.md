Status: Draft
Owner: ML platform team
Canonical for: The admission-gated distributed/multi-GPU training exception
Depends on: [00 — Production architecture](./00-production-architecture.md), [02 — Reproducible ML](./02-reproducible-ml.md)
Last reviewed: 2026-07-30

# 08 — Multi-GPU training

## Outcome

The rare workload that genuinely needs distributed or multi-GPU training has a
supported path — Azure ML `command` jobs on a min-zero cluster — without pulling
that complexity into the baseline. Such jobs log to the **same self-hosted
MLflow** and register versions in the **same registry**, so a distributed-trained
model is operationally identical to any other model downstream.

This is an **exception, admission-gated**, not part of the golden path
([07](./07-delivery-journey.md)). Most training stays on ACA Jobs
([02](./02-reproducible-ml.md)).

## Production decisions

### When this path is allowed

The Azure ML path is used **only** when a workload cannot fit single-node training
on an ACA Job — genuine multi-GPU/distributed need (model or batch size, data
parallelism). A request to use it is admission-gated: it must state why single-node
is insufficient and is approved explicitly. Default answer is "use an ACA Job."

### Azure ML command jobs on min-zero clusters

Distributed training runs as an Azure ML `command` job submitted against a GPU
compute cluster scaled to **minimum zero nodes**, so it costs nothing when idle and
spins up only for a run. We use `command` jobs with **our own container image** —
not curated environments or Compute Instances — to preserve the same
implementation freedom (pinned library/CUDA versions, our deps) we have on ACA.
This avoids the managed-environment version lock-in that motivated self-hosting
MLflow in the first place ([00](./00-production-architecture.md)).

### Unified lineage in self-hosted MLflow

The distributed job sets its MLflow tracking URI to the **self-hosted MLflow**,
logs params/metrics/artifacts, and registers the resulting version in the shared
registry. It records the same run linkage (code image digest, tracked dataset) as
an ACA training job ([02](./02-reproducible-ml.md)), and writes a results-DB record
so it appears in the dashboard alongside every other workflow. Downstream —
promotion, serving, batch inference — treats it identically to an ACA-trained
version.

### What stays out of the baseline

No Azure ML workspace, cluster, or managed environment exists until this exception
is triggered. When it is, only the minimum is provisioned: a workspace, a min-zero
GPU cluster, and the identity/roles to submit jobs and reach the self-hosted MLflow
and Blob.

## Shared concepts

- **Admission gate** — an explicit, justified approval to use the AML path instead
  of an ACA Job.
- **Min-zero cluster** — GPU compute that costs nothing idle and scales up per run.
- **BYO command job** — our container image on AML, avoiding curated-environment
  lock-in.
- **Unified registry** — AML-trained versions live in the same self-hosted MLflow.

## Target design

- IaC module (applied only when the exception is approved) for an AML workspace +
  min-zero GPU cluster + submit identity.
- A distributed training entry point in our image that logs to self-hosted MLflow
  and writes a results-DB record.
- Same promotion/serving/batch path as [06](./06-release-and-operations.md),
  [05](./05-online-serving.md), [04](./04-periodic-and-batch-workflows.md).

## Runnable demonstration

Not applicable until an admitted workload requires it. Acceptance (when triggered):
a `command` job on a min-zero cluster using our image, logging to the self-hosted
MLflow, registering a version, and writing a results-DB record.

## Failure modes and acceptance evidence

| Failure mode | Prevented by | Acceptance evidence |
|---|---|---|
| Distributed complexity leaks into baseline | Admission gate; nothing provisioned until needed | Phases 0–5 ship with no AML resources |
| Managed-environment lock-in | BYO `command` job image | Pinned deps/CUDA in our image, not a curated env |
| Split lineage/registry | Log to shared self-hosted MLflow | AML-trained version appears in the same registry + dashboard |
| Idle GPU cost | Min-zero cluster | Cluster reports zero nodes when no run is active |

## Open decisions

- GPU SKU/region for the cluster (set at admission time).
- Whether the tracked dataset should also be copied to Blob before submission
  (MLflow already records its source + digest).

## References

- Baseline training and lineage — [02](./02-reproducible-ml.md).
- Why BYO images / self-hosted MLflow — [00](./00-production-architecture.md).
- Where this sits in the plan — [07](./07-delivery-journey.md).
