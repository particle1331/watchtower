###############################################################################
# Batch scoring ACA Job (docs/04). An ephemeral, image-pinned Container Apps
# Job that runs as `id-jobs-batch`: reads a pinned model from MLflow (never
# writes MLflow runs), writes per-chunk results-DB rows, and applies the
# stateless continuation rule. Both a scheduled trigger (cron) and a manual
# trigger are enabled. No secrets in the image — all connection info is env,
# and auth is the managed identity.
###############################################################################

resource "azurerm_container_app_job" "batch" {
  name                         = "${var.name_prefix}-job-batch"
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

  # Scheduled batch (docs/04). Cron is UTC; disabled when schedule_cron == "".
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
      name   = "batch"
      image  = var.batch_image
      cpu    = var.cpu
      memory = var.memory

      # DefaultAzureCredential inside the container selects THIS identity.
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      # Self-hosted MLflow tracking + registry (read-only for batch).
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
      # Pinned image digest, visible in run metadata for reproducibility.
      env {
        name  = "IMAGE_DIGEST"
        value = var.batch_image
      }
      # Data source for the scheduled run (overridden per execution for ad-hoc).
      env {
        name  = "DATA_SOURCE"
        value = var.data_source
      }
      # Model name to score with (reads the @champion alias by default).
      env {
        name  = "MODEL_NAME"
        value = var.model_name
      }
    }
  }
}
