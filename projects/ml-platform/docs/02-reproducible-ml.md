Status: Draft
Owner: ML platform team
Canonical for: Reproducible training/evaluation as ACA Jobs, self-hosted MLflow lineage
Depends on: [00 — Production architecture](./00-production-architecture.md), [01 — Platform foundation](./01-platform-foundation.md)
Last reviewed: 2026-07-30

# 02 — Reproducible ML

## Outcome

Training and evaluation run as ordinary ACA Jobs from pinned images, log to the
self-hosted MLflow, and produce a registered model version whose lineage — code
digest, tracked dataset, params, metrics — can be reconstructed from MLflow alone.
Re-running the same inputs yields the same registered artifact, and every run is
also visible in the results DB as a run record.

## Production decisions

### What "model" means here

A **model** is anything with **learned weights** produced by a training run: a
classical tabular estimator (scikit-learn, XGBoost) *and* a fine-tuned
transformer classifier are both models, and both travel the identical registry
path described below — trained as an ACA Job, logged to MLflow, and registered
as a version loaded by `models:/<name>/<version>`. The fine-tuning of a
transformer differs only in the training code and image; the lineage,
registration, promotion, serving, and batch machinery are the same.

This is distinct from an **LLM** app (prompt + config + a model reference, no
weights trained here), which is packaged as a pyfunc version in the *same*
registry — see [03](./03-llm-release-artifacts.md). Taxonomy in one line:
**LLM = prompt-based; model = learned weights** — different producers, one
registry and one promotion path.

### Training and evaluation are ACA Jobs

A training run is a `Manual`- or `Schedule`-triggered ACA Job execution from a
pinned image digest. The script:

1. Builds an **MLflow dataset** from its source with `mlflow.data` (e.g.
   `mlflow.data.from_pandas(df, source=<blob-path>)`), which captures the
   source location, a content **digest** (hash), and the schema — not just
   "the latest table".
2. Starts an MLflow run, logging params, the **code image digest**, and the
   dataset via `mlflow.log_input(dataset, context="training")`, plus metrics.
3. Trains, evaluates on a held-out set, logs metrics and artifacts.
4. **Registers** the model as a new version in the self-hosted MLflow registry.
5. Writes a results-DB run record (`name='train:<model>'`, `status`, `output`
   carrying the MLflow run ID and registered version).

The dataset-tracking core of steps 1–2 looks like this:

```python
import mlflow

raw_data = pd.read_csv(dataset_source_url, delimiter=";")

# Capture source + content digest + schema as an MLflow dataset.
dataset = mlflow.data.from_pandas(
    raw_data, 
  	source=dataset_source_url, 
  	name="wine-quality-white", 
  	targets="quality"
)

with mlflow.start_run():
    mlflow.log_input(dataset, context="training")   # dataset lineage
    mlflow.sklearn.log_model(model, "model")		# training ...
    mlflow.register_model(...) 						# -> new registered version
```

Because the image is pinned and the dataset's source + digest are logged, the run
is reproducible: same image + same dataset digest + same params ⇒ same registered
version content. MLflow's dataset tracking gives this for free — no separate
data-versioning tool (DVC, LakeFS) is introduced.

### Self-hosted MLflow is the system of record for lineage

Everything needed to explain "where did this model version come from" lives in the
MLflow run linked to the registered version: parameters, metrics, the code image
digest, the tracked dataset (source + digest + schema), and evaluation artifacts.
We do not maintain a separate lineage store. Because MLflow is self-hosted at a
pinned version, this lineage is under our control and not subject to a managed
provider's version lag.

### Data validation at the boundary

Input data is validated (e.g. Pandera schemas) at the start of the job, before
training. A schema violation fails the run early with a `FAILURE` results-DB
record and a clear error, rather than silently training on malformed data.

### Evaluation gates registration/promotion

Evaluation computes the metrics that gate promotion. A model version can be
**registered** even if it is not promotable, but promotion to a serving/batch
stage requires meeting the evaluation thresholds recorded with the run (see
[03](./03-llm-release-artifacts.md) for LLM artifacts and
[06](./06-release-and-operations.md) for promotion).

### Results DB record for every run

Even though MLflow holds the ML lineage, the operational fact "a training job ran,
succeeded/failed, took this long, was triggered by this person" is a results-DB
record like every other job. This keeps the dashboard's view of all workflows
uniform (training, eval, batch all look the same operationally) while MLflow holds
the ML-specific detail.

## Shared concepts

- **Tracked dataset** — an MLflow dataset (`mlflow.data` + `mlflow.log_input`)
  capturing the source, a content digest, and schema of the exact data a run
  consumed; never an implicit "latest". This is our data-versioning mechanism.
- **Registered version** — the immutable model identity produced by a training run.
- **Run linkage** — the MLflow run ID stored in the results-DB `output`, tying the
  operational record to the ML lineage.

## Target design

- A `train` job image and an `eval` job image (or one image with a subcommand),
  each an IaC-defined ACA Job bound to `id-jobs-train`.
- MLflow tracking URI and registry point at the self-hosted MLflow App.
- Params and data references passed as job arguments; recorded in both MLflow and
  the results-DB `output`.
- Nightly retrain as a `Schedule`-triggered Job; ad-hoc retrain via `Manual`
  trigger from the dashboard with `triggered_by` audit.

## Runnable demonstration

The current repo trains on synthetic data with Pandera validation locally. Reuse
this as the job's inner logic, but acceptance requires it running as an ACA Job
logging to the self-hosted MLflow and producing a registered version plus a
results-DB record — not the local Compose run.

## Failure modes and acceptance evidence

| Failure mode           | Prevented by                                            | Acceptance evidence                                                              |
| ---------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Non-reproducible model | Pinned image digest + tracked dataset (source + digest) | Re-run with same inputs yields equivalent registered version; lineage shows both |
| Training on bad data   | Boundary validation                                     | Schema violation produces early`FAILURE` record with clear error               |
| Lost lineage           | MLflow run linked to registered version                 | From a version, recover code digest, tracked dataset, params, metrics            |
| Operational blind spot | Results-DB record per run                               | Dashboard shows the training run alongside all other workflows                   |

## Open decisions

- Whether eval is a separate Job or a stage in the train Job.

## References

- MLflow rationale and identity model — [00](./00-production-architecture.md).
- LLM-specific artifacts and evaluators — [03](./03-llm-release-artifacts.md).
- Promotion and rollback — [06](./06-release-and-operations.md).
