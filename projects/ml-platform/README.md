# MLOps Proposal

ML platform plan for a 5-person team on Azure, centered on self-hosted MLflow 3 and portable Celery workers.

## Documents

| File | Purpose |
|---|---|
| `mlops-proposal.csv` | 21 activities x 7 columns: where we are, where we want to be, OSS option, Azure option, tradeoff, recommendation |
| `mlops-services-diagram.md` | Architecture overview (Mermaid), service-to-activity mapping, what is vs is not Azure ML |
| `mlops-delivery-plan.csv` | 3-phase, 10-week phased delivery plan with owners, deliverables, and done criteria |
| `mlops-risks.csv` | Hard questions with assumptions at risk and mitigations |

## What this is

A lightweight ML platform built from portable OSS components hosted on managed Azure infrastructure:

- **MLflow 3 on Azure Container Apps** for experiment tracking, model and prompt registries, evaluation, and LLM tracing
- **Azure Database for PostgreSQL + Blob Storage** as MLflow's backend and proxied artifact stores
- **Microsoft Entra ID + Key Vault** for MLflow user, workload, and secret management
- **Azure ML compute** (scale-to-zero) for training and evaluation jobs
- **Self-hosted Redis on Container Apps** as Celery broker and result backend with 7-day expiry
- **Celery + Celery Beat + Container Apps/KEDA** for portable batch inference that scales to zero
- **Idempotency-keyed task model** so Redis restarts are safe — the Beat reconciliation producer recovers any lost queue state
- **Azure Functions** for low-volume online inference
- **Azure OpenAI** for LLM calls
- **GitHub + GitHub Actions + ACR** for source control, CI/CD, and immutable container images
- **Azure Monitor + Log Analytics + Application Insights** for real-time service health, custom KQL dashboards, structured telemetry, and cost-effective sampling
- **Azure Cost Management** for budget and forecast alerts (separate from log ingestion caps)
- **Pandera** for data validation (OSS, logged to MLflow)
- **scikit-learn Pipeline** packaged in MLflow model for feature engineering

Worker releases use versioned Redis list keys. A new Container Apps revision consumes only its release-specific key; producers switch to the new key only after the new revision passes smoke tests. In-flight tasks complete under `acks_late` with warm `SIGTERM` handling, and the old revision is deactivated once its key is drained. Idempotency keys absorb any duplicate delivery from Redis at-least-once semantics. If the Redis container restarts and loses queue state, a Celery Beat reconciliation producer scans unprocessed documents and republishes them idempotently.

## What this is not

- Not managed MLflow: the team owns the MLflow image, schema migrations, authentication integration, restore tests, and upgrades
- Not Azure ML for everything (batch inference, online inference, deployment, and monitoring use other Azure services)
- Not Prompt Flow (retiring April 2027)
- Not a feature store (preprocessing is packaged with the model)
- Not Kubernetes (Container Apps is managed)
- Not branch-based deployment: Gitflow controls code integration, while immutable MLflow versions and aliases control artifact promotion
- Not a durable result store: Redis expires task results after 7 days; long-term prediction history lives in MLflow evaluation artifacts and structured logs

## Operational invariants

**Reconciliation producer.** A Celery Beat schedule wakes every N minutes, queries the document store for records without a completed status, diffs them against Redis result keys, and republishes missing work with the same idempotency key. This recovers from Redis restarts, transient publish failures, and race conditions without manual intervention. There is no separate service — it lives in the same worker container image.

**Result expiry.** `result_expires = 604800` (7 days) and per-result Redis TTLs keep the broker compact at ~210 MB for 30k daily documents with 1 KB result payloads. Idempotency keys share the same TTL — after expiry a document cannot be replayed without risking a duplicate, so the reconciliation window and result expiry window are aligned.

**Crash safety.** A Redis restart loses queued but unacknowledged messages. In-flight tasks complete normally and reconnect when Redis returns. Lost queue entries are recovered by the next reconciliation scan. No tasks require manual resubmission.
