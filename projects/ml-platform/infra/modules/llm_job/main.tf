###############################################################################
# Shared LLM ACA Job adapter.
#
# The workload image is the same train image used by Compose and the local
# runner. Only the command and cloud connection environment differ between the
# registration and evaluation Job instances.
###############################################################################

resource "azurerm_container_app_job" "llm" {
  name                         = "${var.name_prefix}-job-${var.job_suffix}"
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

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "llm"
      image   = var.image
      command = var.command
      cpu     = var.cpu
      memory  = var.memory

      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      env {
        name  = "MLFLOW_TRACKING_URI"
        value = var.mlflow_tracking_uri
      }
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
      env {
        name  = "IMAGE_DIGEST"
        value = var.image
      }
      env {
        name  = "KEY_VAULT_URL"
        value = var.key_vault_url
      }
      env {
        name  = "MODEL_API_KEY_SECRET"
        value = var.model_api_key_secret
      }

      dynamic "env" {
        for_each = var.eval_dataset == "" ? [] : [var.eval_dataset]
        content {
          name  = "LLM_EVAL_DATASET"
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.eval_dataset == "" ? [] : [var.model_name]
        content {
          name  = "LLM_MODEL_NAME"
          value = env.value
        }
      }
      dynamic "env" {
        for_each = var.eval_dataset == "" ? [] : [var.model_version]
        content {
          name  = "LLM_MODEL_VERSION"
          value = env.value
        }
      }
    }
  }
}
