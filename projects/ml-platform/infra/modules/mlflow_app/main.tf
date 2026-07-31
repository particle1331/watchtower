###############################################################################
# Self-hosted MLflow — an ACA App running our own pinned MLflow image (docs/00,
# docs/02). Postgres `mlflow` DB is the metadata backend; a Blob container is the
# artifact store. The App runs as `id-mlflow` and authenticates to both with that
# managed identity (no passwords). The registered model VERSION produced here is
# the canonical model identity used by serving and batch inference.
###############################################################################

resource "azurerm_container_app" "mlflow" {
  name                         = "${var.name_prefix}-mlflow"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  # Pull the pinned image from ACR using the same managed identity.
  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 5000
    transport        = "auto"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "mlflow"
      image  = var.mlflow_image
      cpu    = 0.5
      memory = "1Gi"

      # DefaultAzureCredential inside the container selects THIS managed identity.
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      env {
        name  = "MLFLOW_HOST"
        value = "0.0.0.0"
      }
      env {
        name  = "MLFLOW_PORT"
        value = "5000"
      }
      # Postgres metadata backend (Entra auth; entrypoint fetches an access token).
      env {
        name  = "PGHOST"
        value = var.postgres_fqdn
      }
      env {
        name  = "PGDATABASE"
        value = "mlflow"
      }
      env {
        name  = "PGUSER"
        value = var.mlflow_pg_principal
      }
      # Blob artifact store, e.g. wasbs://mlflow-artifacts@<account>.blob.core.windows.net/
      env {
        name  = "MLFLOW_ARTIFACTS_DESTINATION"
        value = var.artifacts_destination
      }
    }
  }
}
