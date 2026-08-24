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

Machine auth uses managed identities; dashboard users authenticate with Entra
Easy Auth. No passwords or client secrets live in images or Git. Development
Terraform state is local and contains the dashboard app-registration secret, so
protect it before sharing or moving deployment into CI.

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
│   ├── batch_job/          # score.py + Dockerfile (worker.py is a dormant upgrade path)
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
│       ├── foundation/     # RG, ACR, ACA env, Postgres, storage, logs, 6 identities
│       ├── mlflow_app/     # self-hosted MLflow ACA App
│       ├── train_job/      # reusable training/eval ACA Job adapter
│       ├── batch_job/      # batch scoring ACA Job (id-jobs-batch)
│       ├── llm_job/        # shared register/evaluate ACA Job adapter
│       ├── serving_app/    # online serving ACA App (id-serving)
│       ├── observability/  # 2 batch-signal Log Analytics alert rules
│       ├── dashboard/      # catalog/launcher ACA App + Easy Auth
│       ├── aml/            # AML workspace + min-zero GPU cluster (exception only)
│       └── broker/         # managed Redis + KEDA scale rule (conditional upgrade)
├── deploy/
│   ├── deploy.ps1          # full 4-pass platform deploy
│   └── smoke-tests.ps1     # end-to-end golden path verification
└── .github/workflows/
    └── ci.yml              # build / Trivy scan / push / update ACA definitions (OIDC)
```

---

## Prerequisites

- Azure CLI (`az login`) with **User Access Administrator** on the target resource
  group (needed for role assignments in `identities.tf`)
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
dashboard_auth_client_id      = "<dashboard-app-client-id>"
dashboard_auth_client_secret  = "<dashboard-app-client-secret>"
dashboard_operator_group_id   = "<operator-group-object-id>"
```

The app registration can be created without a redirect URI initially. After the
first dashboard apply, add the value of
`terraform output -raw dashboard_auth_callback_url` as a Web redirect URI, then
configure its token to emit security-group claims and verify sign-in. The group
claim is what lets the app distinguish operators from authenticated viewers.
This breaks the hostname/app-registration bootstrap cycle.

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

1. **Foundation** — ACR, Postgres, storage, Log Analytics, 6 managed identities
2. **MLflow** — build + push image; run `grants.sql` (Postgres principals) and
   `schema.sql` (results table DDL); apply MLflow App
3. **Images** — build + push train, batch, serving, and dashboard images
4. **Full apply** — all modules active; smoke tests run at the end

Evaluate a candidate before promoting it. The same train image supplies the
separate eval Job, and `demo/promote.py` rejects a version without a passing
evaluation record for its exact `models:/name/version` URI.

To pin an already evaluated version during deployment:

```powershell
./deploy/deploy.ps1 ... -ServingModelVersion 3
```

### 3 — Verify

```powershell
./deploy/smoke-tests.ps1 -TfVarsFile infra/environments/dev.tfvars
```

Checks MLflow health, train/eval/batch executions, serving readiness and model
identity, dashboard health, and the anonymous-access boundary. Authenticated
operator/viewer checks use real Entra principals and remain deployment
acceptance steps.

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
bounded retries during one execution. A fresh invocation creates a fresh parent
unless its caller deliberately reuses `RESULTS_RUN_ID`; automatic cross-execution
crash resume is not part of the baseline.

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
