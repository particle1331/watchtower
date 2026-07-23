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
- **Azure ML workspace + CPU compute cluster** (scale-to-zero) for training and evaluation jobs, deployed with the main platform
- **Optional GPU compute module** (`infra/gpu-training.bicep`) for future multi-GPU fine-tuning POCs, deployed separately after GPU quota is approved
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

## Document processing pipeline

Every worker task carries an exact model version, prompt version, release identifier, task contract version, and an idempotency key derived from the document's immutable identifier. Celery is configured as follows:

```python
# celeryconfig.py
broker_url = "redis://redis-container:6379/0"
result_backend = "redis://redis-container:6379/0"
result_expires = 604800           # 7 days
task_acks_late = True             # ack only after task completes
task_reject_on_worker_lost = True # redeliver immediately if worker crashes
worker_prefetch_multiplier = 1    # one task per worker at a time to respect quota
```


```python
# tasks.py
@app.task(bind=True, acks_late=True, task_reject_on_worker_lost=True,
          autoretry_for=(Exception,), retry_backoff=True,
          retry_backoff_max=600, retry_jitter=True, max_retries=5)
def process_document(self, doc_id, doc_content, model_version, prompt_version,
                     contract_version, release_id, idempotency_key):
    if contract_version != SUPPORTED_CONTRACT:
        logger.warning(f"Rejecting unsupported contract {contract_version}")
        return  # no retry — log and skip

    with idempotency_guard(idempotency_key):
        result = call_openai(
            deployment=DEPLOYMENT,
            prompt=load_prompt(prompt_version),
            content=doc_content,
        )
        store_result(doc_id, result, model_version, prompt_version)
    # Celery acknowledges here — if the worker dies before this line,
    # task_reject_on_worker_lost triggers immediate redelivery.
```

**`idempotency_guard(idempotency_key)`** is a context manager using `SETNX` (SET-if-Not-eXists) in Redis. It atomically writes a sentinel key with a 7-day TTL. If the key already exists, the task is a duplicate delivery and the guard skips processing — no duplicate OpenAI call, no duplicate side effect. If the key doesn't exist, the task proceeds normally. This is the single mechanism that makes Redis at-least-once delivery safe without broker-level acknowledgements.

**Why Redis over a second service.** At 30,000 documents per day (~21/minute), RabbitMQ's durable queues, dead-letter exchanges, and publisher confirms address problems that only emerge at two orders of magnitude more load. The task code above achieves the same correctness guarantee with three lines of Celery configuration, a 30-line `idempotency_guard`, and the Beat reconciliation schedule — all running on one Redis instance that also serves as the result backend. The operational surface stays at one self-hosted process instead of a separate stateful cluster you patch, monitor, back up, and pay for.
