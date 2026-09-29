###############################################################################
# Workflow catalog + authorized launcher dashboard ACA App.
# Reads results DB (read-only) and starts Jobs via the ACA execution API.
# Runs as `id-dashboard`; human access is via Entra ID Easy Auth — operators
# can launch Jobs, viewers can read. The triggered_by identity is the
# signed-in user's Entra UPN (from Easy Auth), not the machine identity.
###############################################################################

terraform {
  required_providers {
    azapi = {
      source = "Azure/azapi"
    }
  }
}

resource "azurerm_container_app" "dashboard" {
  name                         = "${var.name_prefix}-dashboard"
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"
  tags                         = var.tags

  lifecycle {
    precondition {
      condition = (
        var.auth_tenant_id != "" &&
        var.auth_client_id != "" &&
        var.auth_client_secret != "" &&
        var.operator_group_id != ""
      )
      error_message = "Dashboard deployment requires an Entra tenant, client ID, client secret, and operator group ID."
    }
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  secret {
    name  = "dashboard-auth-client-secret"
    value = var.auth_client_secret
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
      # Deep-link target (auth happens in the browser).
      env {
        name  = "MLFLOW_TRACKING_URI"
        value = var.mlflow_url
      }
      env {
        name        = "DASHBOARD_AUTH_CLIENT_SECRET"
        secret_name = "dashboard-auth-client-secret"
      }
      env {
        name  = "DASHBOARD_OPERATOR_GROUP_ID"
        value = var.operator_group_id
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
        name  = "TRAIN_JOB_NAME"
        value = var.train_job_name
      }
      env {
        name  = "EVAL_JOB_NAME"
        value = var.eval_job_name
      }
      env {
        name  = "BATCH_JOB_NAME"
        value = var.batch_job_name
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

# Easy Auth authenticates all dashboard traffic except the probe endpoint.
# Fine-grained operator authorization stays in the app because viewers must be
# able to read while only one Entra group may call mutation routes.
resource "azapi_resource" "auth" {
  type      = "Microsoft.App/containerApps/authConfigs@2025-07-01"
  name      = "current"
  parent_id = azurerm_container_app.dashboard.id

  body = {
    properties = {
      platform = {
        enabled = true
      }
      globalValidation = {
        excludedPaths               = ["/healthz"]
        redirectToProvider          = "azureActiveDirectory"
        unauthenticatedClientAction = "RedirectToLoginPage"
      }
      httpSettings = {
        requireHttps = true
      }
      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId                = var.auth_client_id
            clientSecretSettingName = "DASHBOARD_AUTH_CLIENT_SECRET"
            openIdIssuer            = "https://login.microsoftonline.com/${var.auth_tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [var.auth_client_id]
          }
        }
      }
    }
  }
}
