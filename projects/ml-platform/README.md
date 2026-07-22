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
- **Managed RabbitMQ + Celery + Container Apps/KEDA** for portable batch inference that scales to zero
- **Azure Functions** for low-volume online inference
- **Azure OpenAI** for LLM calls
- **GitHub + GitHub Actions + ACR** for source control, CI/CD, and immutable container images
- **Application Insights + Azure Monitor + Cost Management** for service, ingestion, and cost monitoring
- **Pandera** for data validation (OSS, logged to MLflow)
- **scikit-learn Pipeline** packaged in MLflow model for feature engineering

Worker releases use versioned RabbitMQ queues. A new Container Apps revision is validated against a new queue before producers switch to it; the old revision drains its old queue and in-flight tasks before it is deactivated. Old and new revisions never compete for new tasks from the same queue.

## What this is not

- Not managed MLflow: the team owns the MLflow image, schema migrations, authentication integration, restore tests, and upgrades
- Not Azure ML for everything (batch inference, online inference, deployment, and monitoring use other Azure services)
- Not Prompt Flow (retiring April 2027)
- Not a feature store (preprocessing is packaged with the model)
- Not Kubernetes (Container Apps is managed)
- Not branch-based deployment: Gitflow controls code integration, while immutable MLflow versions and aliases control artifact promotion
