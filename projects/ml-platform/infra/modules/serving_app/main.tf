###############################################################################
# Online serving ACA App (docs/05). A long-running ACA App that loads an exact
# MLflow model version at startup and exposes an HTTP inference endpoint. Runs
# as `id-serving` with read-only access to MLflow artefacts — no write access
# to the registry or training data. The served version is pinned in the App
# definition; rollback = repoint definition at a prior version or digest.
###############################################################################

resource "azurerm_container_app" "serving" {
  name                         = "${var.name_prefix}-serving"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    transport        = "auto"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "serving"
      image  = var.serving_image
      cpu    = var.cpu
      memory = var.memory

      # DefaultAzureCredential selects THIS identity (read-only MLflow artefacts).
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      # Self-hosted MLflow registry — model downloaded at startup.
      env {
        name  = "MLFLOW_TRACKING_URI"
        value = var.mlflow_tracking_uri
      }
      # Exact model version pinned in the App definition (never a floating alias).
      env {
        name  = "MODEL_NAME"
        value = var.model_name
      }
      env {
        name  = "MODEL_VERSION"
        value = var.model_version
      }
      # HTTP port.
      env {
        name  = "PORT"
        value = "8080"
      }
    }

    # Readiness: wait until /readyz returns 200 (model loaded + canary passed).
    readiness_probe {
      transport = "HTTP"
      path      = "/readyz"
      port      = 8080

      initial_delay    = 15
      period_seconds   = 10
      timeout          = 5
      failure_count_threshold = 10
    }

    # Liveness: restart if /healthz stops responding.
    liveness_probe {
      transport = "HTTP"
      path      = "/healthz"
      port      = 8080

      initial_delay    = 10
      period_seconds   = 30
      timeout          = 5
      failure_count_threshold = 3
    }
  }
}
