###############################################################################
# Training / evaluation ACA Job (docs/02). An ephemeral, image-pinned Container
# Apps Job that runs as `id-jobs-train`: it logs to the self-hosted MLflow and
# writes a results-DB record. Manual trigger for ad-hoc/backfill runs; a
# scheduled trigger drives the nightly retrain. No secrets in the image — all
# connection info is env, and auth is the managed identity.
###############################################################################

resource "azurerm_container_app_job" "train" {
  name                         = "${var.name_prefix}-job-train"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  container_app_environment_id = var.container_app_environment_id
  tags                         = var.tags

  replica_timeout_in_seconds = var.replica_timeout_seconds
  replica_retry_limit        = 1

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  # Ad-hoc / backfill runs: `az containerapp job start`.
  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  # Nightly retrain (docs/02). Cron is UTC; disabled when schedule_cron == "".
  dynamic "schedule_trigger_config" {
    for_each = var.schedule_cron == "" ? [] : [var.schedule_cron]
    content {
      cron_expression          = schedule_trigger_config.value
      parallelism              = 1
      replica_completion_count = 1
    }
  }

  template {
    container {
      name   = "train"
      image  = var.train_image
      cpu    = var.cpu
      memory = var.memory

      # DefaultAzureCredential inside the container selects THIS identity.
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      # Self-hosted MLflow tracking + registry (Phase 0 App).
      env {
        name  = "MLFLOW_TRACKING_URI"
        value = var.mlflow_tracking_uri
      }
      # Results-DB record (Entra auth; entrypoint fetches an access token).
      env {
        name  = "PGHOST"
        value = var.postgres_fqdn
      }
      env {
        name  = "PGUSER"
        value = var.results_pg_principal
      }
      env {
        name  = "RESULTS_DB"
        value = "results"
      }
      # Pinned image digest, recorded on the MLflow run for reproducibility.
      env {
        name  = "IMAGE_DIGEST"
        value = var.train_image
      }
    }
  }
}
