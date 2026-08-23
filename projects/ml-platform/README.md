# ml-platform

A deliberately small, low-ops ML platform for a team of ML engineers who are not
full-time platform engineers. Built step by step in the
[ML platform course](../../courses/ml-platform/) on this site; the source here is the real
implementation each chapter references.

**Design rule:** use the fewest moving parts that deliver reproducible training,
honest evaluation, scheduled and on-demand batch inference, and observable
operations — and only add machinery when a concrete need forces it.

---

## Architecture — four planes

| Plane | Technology |
|---|---|
| **Execution** | Azure Container Apps Jobs — ephemeral, image-pinned, cron + manual triggers |
| **Model lifecycle** | Self-hosted MLflow (ACA App) + Postgres `mlflow` DB + Blob artifacts |
| **Operational state** | Generic results DB (Postgres `results`) — one table for every job type |
| **Serving** | ACA App — loads an exact `models:/name/version` at startup |

Auth is managed-identity / Entra throughout — **no passwords in images or Git**.
Infrastructure is Terraform (`azurerm ~> 4.0`), two-pass deploy, local state for dev.

---

## Repo layout

```
ml-platform/
├── src/
│   ├── ml_platform/
│   │   ├── common/         # mlflow_client, datasets, schemas, results context mgr
│   │   ├── results/        # schema.sql, store.py, continuation.py
│   │   └── llm/            # pyfunc model, artifact_builder, evaluator
│   ├── mlflow_app/         # self-hosted MLflow container image
│   ├── train_job/          # train.py, evaluate.py, register_llm.py, Dockerfile
│   ├── batch_job/          # score.py, worker.py (broker upgrade), Dockerfile
│   ├── serving_app/        # FastAPI serving App — /healthz, /readyz, /v1/predictions
│   ├── dashboard/          # FastAPI catalog + launcher — reads results DB, starts Jobs
│   └── train_aml/          # distributed training via AML command job (exception only)
├── infra/
│   ├── main.tf             # root module — composes all phases
│   ├── variables.tf
│   ├── outputs.tf
│   ├── grants.sql          # idempotent Postgres principals + least-priv grants
│   ├── environments/
│   │   └── dev.tfvars
│   └── modules/
│       ├── foundation/     # RG, ACR, ACA env, Postgres, storage, Grafana, 6 identities
│       ├── mlflow_app/     # self-hosted MLflow ACA App
│       ├── train_job/      # training/eval ACA Job (id-jobs-train)
│       ├── batch_job/      # batch scoring ACA Job (id-jobs-batch)
│       ├── serving_app/    # online serving ACA App (id-serving)
│       ├── observability/  # 4 Log Analytics alert rules
│       ├── dashboard/      # workflow catalog + launcher ACA App (id-dashboard)
│       ├── aml/            # AML workspace + min-zero GPU cluster (exception only)
│       └── broker/         # managed Redis + KEDA scale rule (conditional upgrade)
├── deploy/
│   ├── deploy.ps1          # full 4-pass platform deploy
│   └── smoke-tests.ps1     # end-to-end golden path verification
├── docs/                   # design documents (00–08)
└── .github/workflows/
    └── ci.yml              # build / Trivy scan / push / update ACA definitions (OIDC)
```

---

## Prerequisites

- Azure CLI (`az login`) with **User Access Administrator** on the target resource
  group (needed for role assignments in `identities.tf`; see `docs/01` open decisions)
- Terraform ≥ 1.6
- `psql` client
- Docker (or `az acr build` for server-side builds)
- PowerShell 7+

---

## Quick start

### 1 — Fill in secrets

Create `infra/secret.auto.tfvars` (gitignored, auto-loaded by Terraform):

```hcl
subscription_id               = "<your-subscription-id>"
postgres_admin_object_id      = "<your-entra-object-id>"
postgres_admin_principal_name = "you@example.com"
```

Set your deployer IP in `infra/environments/dev.tfvars`:

```hcl
deployer_ip = "<output of: Invoke-RestMethod https://api.ipify.org>"
```

### 2 — Deploy

```powershell
cd projects/ml-platform

./deploy/deploy.ps1 `
  -TfVars infra/environments/dev.tfvars `
  -PgAdminUpn you@example.com
```

Four passes run automatically:

1. **Foundation** — ACR, Postgres, storage, 6 managed identities
2. **MLflow** — build + push image; run `grants.sql` (Postgres principals) and
   `schema.sql` (results table DDL); apply MLflow App
3. **Images** — build + push train, batch, serving, and dashboard images
4. **Full apply** — all modules active; smoke tests run at the end

To promote a model version to serving after training:

```powershell
./deploy/deploy.ps1 ... -ServingModelVersion 3
```

### 3 — Verify

```powershell
./deploy/smoke-tests.ps1 -TfVarsFile infra/environments/dev.tfvars
```

Checks all phases: MLflow `/health`, train Job execution, serving `/readyz` version
report, dashboard `/api/runs`.

---

## CI/CD

`.github/workflows/ci.yml` authenticates via **OIDC** as `id-ci` and:

1. Lints (`ruff`) and runs tests — no cloud required.
2. Builds each image, runs a **Trivy CRITICAL** vulnerability scan.
3. Pushes to ACR by digest.
4. Updates ACA Job/App definitions with the new pinned digest.

CI never schedules or orchestrates workflows (those live in ACA Job cron triggers).

Required GitHub repository variables: `ACR_NAME`, `ACR_LOGIN_SERVER`,
`RESOURCE_GROUP`, `TRAIN_JOB_NAME`, `BATCH_JOB_NAME`, `SERVING_APP_NAME`,
`DASHBOARD_APP_NAME`. Secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`.

---

## Results DB status vocabulary

Every job writes to one `results` table. Valid `status` values:

| Status | Meaning |
|---|---|
| `PENDING` | Created, not yet started |
| `STARTED` | Currently executing |
| `SUCCESS` | Completed successfully |
| `RETRY` | Failed transiently; eligible for retry |
| `FAILURE` | Failed permanently |
| `REVOKED` | Cancelled |

Batch workflows use **parent/child rows**: one parent per batch, one child per
chunk/item. The continuation rule (`ml_platform/results/continuation.py`) drives
"run until done" as a stateless SQL query — no orchestration engine.

---

## Fixed invariants

These hold across all design decisions. Changing any is an architecture decision,
not an implementation detail.

1. **ACA Jobs are the execution plane** — no long-running workers; a code deploy
   is a digest bump and the next execution runs new code automatically.
2. **No workflow control-plane** — linear pipelines are scripts; fan-out is
   parent/child rows + the continuation rule.
3. **No broker by default** — the Celery/Redis upgrade (`src/batch_job/worker.py`,
   `infra/modules/broker/`) is adopted only when fan-out demonstrably forces it.
4. **Self-hosted MLflow** — not Azure ML managed MLflow.
5. **Results DB is the canonical run store** — one table, never duplicated.
6. **MLflow is read-only for batch inference** — only training/eval writes runs.
7. **GitHub Actions is CI/CD only** — never a scheduler or orchestrator.
8. **Least-privilege managed identities; OIDC for CI** — no shared credentials.
9. **Distributed/multi-GPU training is admission-gated** — `src/train_aml/` and
   `infra/modules/aml/` are provisioned only when explicitly approved.

---

## Design documents

| Doc | Covers |
|---|---|
| `docs/00-production-architecture.md` | Target planes, fixed decisions, cross-document invariants |
| `docs/01-platform-foundation.md` | Azure resources, identities, RBAC, IaC, networking |
| `docs/02-reproducible-ml.md` | Training/eval as ACA Jobs, self-hosted MLflow, lineage |
| `docs/03-llm-release-artifacts.md` | MLflow `pyfunc` artifact, LLM evaluator |
| `docs/04-periodic-and-batch-workflows.md` | Scheduling, results DB, continuation rule |
| `docs/05-online-serving.md` | ACA App HTTP serving, exact version pinning, rollback |
| `docs/06-release-and-operations.md` | CI/CD, promotion, rollback, observability, dashboard |
| `docs/07-delivery-journey.md` | Golden path and phased progress register |
| `docs/08-multi-gpu-training.md` | Admission-gated AML clusters for distributed training |
