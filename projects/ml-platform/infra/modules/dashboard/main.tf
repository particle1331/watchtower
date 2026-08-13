###############################################################################
# Workflow catalog + launcher dashboard ACA App (docs/06).
# Reads results DB (read-only) and starts Jobs via the ACA execution API.
# Runs as `id-dashboard`; human access is via Entra ID Easy Auth — operators
# can launch Jobs, viewers can read. The triggered_by identity is the
# signed-in user's Entra UPN (from Easy Auth), not the machine identity.
###############################################################################

resource "azurerm_container_app" "dashboard" {
  name                         = "${var.name_prefix}-dashboard"
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
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "dashboard"
      image  = var.dashboard_image
      cpu    = 0.25
      memory = "0.5Gi"

      # DefaultAzureCredential selects THIS identity (ACA jobs start + results DB read).
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      # Results DB — read-only (SELECT on results table per grants.sql).
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
      # Deep-link targets (no auth stored here — links open in the browser).
      env {
        name  = "MLFLOW_TRACKING_URI"
        value = var.mlflow_url
      }
      env {
        name  = "GRAFANA_URL"
        value = var.grafana_url
      }
      # ACA execution API context (for triggering Jobs).
      env {
        name  = "AZURE_SUBSCRIPTION_ID"
        value = var.subscription_id
      }
      env {
        name  = "AZURE_RESOURCE_GROUP"
        value = var.resource_group_name
      }
      env {
        name  = "PORT"
        value = "8080"
      }
    }

    readiness_probe {
      transport = "HTTP"
      path      = "/healthz"
      port      = 8080

      initial_delay           = 5
      period_seconds          = 10
      timeout                 = 3
      failure_count_threshold = 5
    }

    liveness_probe {
      transport = "HTTP"
      path      = "/healthz"
      port      = 8080

      initial_delay           = 5
      period_seconds          = 30
      timeout                 = 5
      failure_count_threshold = 3
    }
  }
}
