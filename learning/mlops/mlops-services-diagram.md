# MLOps Services Diagram

## Architecture overview

```mermaid
flowchart TB
    subgraph Dev["Developer workflow"]
        GH[GitHub<br/>code + prompts + IaC]
        GHA[GitHub Actions<br/>CI/CD + approvals]
        GE[GitHub Environments<br/>test / prod approval]
    end

    subgraph Data["Data layer"]
        BLOB[(Azure Blob Storage<br/>raw + immutable snapshots)]
        DA[Azure ML Data Assets<br/>versioned references]
        PV[Pandera<br/>schema + quality checks]
    end

    subgraph Platform["MLflow 3 control plane"]
        MLF[MLflow 3 on Container Apps<br/>pinned image, min 1 replica]
        PG[(Azure Database for PostgreSQL<br/>metadata + automated backups)]
        MLAB[(Azure Blob Storage<br/>proxied artifacts + soft delete)]
        MLR[MLflow registries<br/>immutable models + prompts + aliases]
        ENTRA[Microsoft Entra ID<br/>users + workload identities]
        KV[Key Vault<br/>database and broker secrets]
    end

    subgraph Train["Training + evaluation compute"]
        AMLC[Azure ML Compute Cluster<br/>scale-to-zero CPU]
    end

    subgraph LLMServices["LLM + prompt layer"]
        AOAI[Azure OpenAI<br/>GPT-4o etc.]
        PROMPTS[prompt files in Git<br/>versioned, hash-logged]
        MLFEVAL[MLflow 3 evaluation + tracing<br/>prompt + model runs]
    end

    subgraph BatchInf["Batch inference - 30k docs/day"]
        PROD[Uploader or reconciliation producer<br/>task contract + idempotency key]
        RMQ[(Managed RabbitMQ<br/>versioned queues + DLQ)]
        CA[Celery on Container Apps + KEDA<br/>workers scale 0 to N<br/>on queue depth]
        STATUS[(PostgreSQL status store<br/>task state + deduplication)]
        ACR[(ACR<br/>immutable images)]
    end

    subgraph OnlineInf["Online inference - low volume"]
        FUNC[Azure Functions<br/>event-driven predictions]
    end

    subgraph Monitor["Monitoring + feedback"]
        AI[Application Insights<br/>errors, latency, tokens]
        AM[Azure Monitor<br/>metrics + operational alerts]
        COST[Azure Cost Management<br/>budgets + forecast alerts]
        QJOB[Scheduled Azure ML job<br/>weekly quality evaluation]
        TEAMS[Teams feedback<br/>exported to Blob/Table]
    end

    GH --> GHA --> GE
    GHA -->|build image| ACR
    GHA -->|deploy revision| CA
    GHA -->|deploy| FUNC

    BLOB --> DA
    DA --> PV
    PV -->|reports| MLF

    GH -->|job YAML| AMLC
    DA --> AMLC
    AMLC -->|runs| MLF

    MLF --> PG
    MLF -->|proxied artifacts| MLAB
    MLF --> MLR
    ENTRA -->|authenticate| MLF
    KV -->|secret references| MLF

    PROMPTS -->|register immutable version| MLR
    CA -->|calls| AOAI
    FUNC -->|calls| AOAI
    MLFEVAL --> MLF

    BLOB --> PROD
    PROD -->|publish to release queue| RMQ
    RMQ -->|versioned tasks| CA
    ACR -->|pull image| CA
    CA --> AOAI
    CA --> STATUS
    CA -->|structured logs| AI

    FUNC --> MLR
    FUNC -->|logs| AI

    AI --> AM
    AM --> COST
    QJOB --> MLF
    TEAMS -->|ingest| BLOB
    BLOB --> QJOB
```

## Service-to-activity mapping

```mermaid
flowchart LR
    subgraph Activities
        A1[Dataset extraction]
        A2[Dataset versioning]
        A3[Data validation]
        A4[Feature engineering]
        A5[Model training]
        A6[Compute provisioning]
        A7[Experiment tracking]
        A8[Model registry]
        A9[Model evaluation]
        A10[Prompt development]
        A11[Prompt evaluation]
        A12[Batch inference]
        A13[Online inference]
        A14[Packaging]
        A15[Deployment]
        A16[Rollback]
        A17[CI/CD]
        A18[Environments]
        A19[Service monitoring]
        A20[Quality monitoring]
        A21[Audit + governance]
    end

    subgraph Services
        S1[Azure Blob Storage]
        S2[Azure ML Data Assets]
        S3[Pandera OSS]
        S4[scikit-learn Pipeline]
        S5[Azure ML Compute]
        S6[Bicep / Terraform]
        S7[Self-hosted MLflow 3]
        S8[MLflow Model Registry]
        S9[pytest + MLflow]
        S10[Git + MLflow Prompt Registry]
        S11[Azure OpenAI]
        S12[Celery + RabbitMQ + Container Apps KEDA]
        S13[Azure Functions]
        S14[MLflow Models + ACR]
        S15[GitHub Actions + workload identity]
        S16[Container Apps revisions]
        S17[GitHub Environments]
        S18[Application Insights]
        S19[Azure Monitor + Cost Management]
        S20[Scheduled Azure ML job]
        S21[GitHub releases + MLflow aliases]
    end

    A1 --> S1
    A2 --> S2
    A3 --> S3
    A4 --> S4
    A5 --> S5
    A6 --> S6
    A7 --> S7
    A8 --> S8
    A9 --> S9
    A10 --> S10
    A11 --> S9
    A12 --> S12
    A13 --> S13
    A14 --> S14
    A15 --> S15
    A16 --> S16
    A17 --> S15
    A18 --> S17
    A19 --> S18
    A20 --> S20
    A21 --> S21
```

## Stale-worker-safe rollout

Queue workers do not receive HTTP traffic, so Container Apps traffic splitting cannot stop an old revision from fetching a new task. Batch releases therefore use multiple-revision mode and release-specific queues such as `documents.v3`.

```mermaid
sequenceDiagram
    participant CI as GitHub Actions
    participant New as New worker revision
    participant Producer as Task producer
    participant QNew as documents.v3
    participant QOld as documents.v2
    participant Old as Old worker revision

    CI->>New: Deploy immutable image digest, consuming only documents.v3
    CI->>QNew: Publish compatibility smoke task
    New->>QNew: Process smoke task
    New-->>CI: Readiness and contract checks pass
    CI->>Producer: Switch active task contract and route to documents.v3
    Producer->>QNew: Publish all new tasks
    Old->>QOld: Finish ready and unacknowledged tasks
    CI->>QOld: Verify ready = 0 and unacknowledged = 0
    CI->>Old: Deactivate old Container Apps revision
```

Every task includes `task_contract_version`, `producer_release`, an idempotency key, and exact model and prompt versions. Celery workers consume only their configured release queue, use late acknowledgement, reject tasks with unsupported contracts, and handle `SIGTERM` as a warm shutdown. Deactivation occurs only after RabbitMQ reports no ready or unacknowledged tasks; otherwise the workflow stops and alerts. Rollback routes producers back to the preceding queue and revision only when the task contract is backward-compatible.

## What is NOT Azure ML

| Activity | Service used | Why not Azure ML |
|---|---|---|
| Batch inference (30k docs) | Celery + managed RabbitMQ + Container Apps + KEDA | Azure ML batch endpoints wrap a scoring script; this workload is durable task orchestration around Azure OpenAI calls. Celery and AMQP are portable, while Container Apps provides managed scale-to-zero compute. |
| Online inference (low volume) | Azure Functions | Managed online endpoints charge always-on compute; Functions scale to zero between requests. |
| LLM calls | Azure OpenAI | Azure ML has no LLM hosting role here; it only logs runs. |
| Prompt management | Git + MLflow 3 Prompt Registry | Git reviews prompt source; immutable registry versions and aliases control deployment. Azure ML's MLflow integration cannot provide the required MLflow 3 APIs. |
| CI/CD | GitHub Actions + ACR | Azure ML pipelines are for ML jobs, not app deployment. |
| Service monitoring | Application Insights + Azure Monitor | Azure ML's built-in monitoring covers jobs and endpoints, not Functions or Container Apps. |
| Deployment + rollback | Versioned queues, Container Apps revisions, and immutable Function packages | Queue routing prevents stale worker revisions from accepting new task contracts. Azure ML's deployment surface only covers its own endpoints. |
| Data validation | Pandera (OSS) | Azure ML has no built-in data validation; it must be added as a pipeline step. |
| Feature engineering | scikit-learn Pipeline (OSS) | Azure ML has no feature store; pipeline packaging in MLflow model is standard OSS. |

## What is self-hosted MLflow 3

| Capability | Implementation | Operating implication |
|---|---|---|
| Tracking, evaluation, and tracing | Pinned MLflow 3 image on Container Apps | The team owns image updates, availability monitoring, and client compatibility. |
| Metadata and registry state | Azure Database for PostgreSQL | Automated backups are enabled; schema migrations require a pre-upgrade backup and tested restore. |
| Model, evaluation, and trace artifacts | Blob Storage through MLflow's artifact proxy | Clients need MLflow access, not direct Blob credentials. Enable soft delete and lifecycle rules. |
| Model and prompt promotion | Immutable versions plus `candidate`, `staging`, and `champion` aliases | Only CI may mutate protected aliases; deployments resolve and record the exact version. |
| Authentication | Entra ID for users and workloads; secrets in Key Vault | Browser and noninteractive MLflow clients must both be tested before production use. |

## What IS Azure ML

| Activity | Service used | Why Azure ML |
|---|---|---|
| Training jobs | Azure ML compute cluster (scale-to-zero) | Quota-backed, reproducible environments, job definitions in Git. |
| Dataset versioning | Azure ML data assets | Immutable references to Blob paths; integrated with jobs. |
| Quality monitoring | Scheduled Azure ML evaluation job | Uses scale-to-zero compute and logs results to the self-hosted MLflow 3 server. |
