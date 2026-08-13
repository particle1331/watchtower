###############################################################################
# Root — composes the Phase 0 foundation and (once its image exists) the
# self-hosted MLflow App. See docs/01. Deploy in two passes via deploy.ps1:
#   1. apply with mlflow_image = ""     -> foundation only (creates ACR)
#   2. build+push MLflow image to ACR, run grants.sql, then apply with the digest
###############################################################################

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local state for the dev MVP; prod uses a remote azurerm (Storage) backend.
  # backend "azurerm" { ... }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

module "foundation" {
  source = "./modules/foundation"

  prefix                        = var.prefix
  environment                   = var.environment
  location                      = var.location
  resource_group_name           = var.resource_group_name
  postgres_admin_object_id      = var.postgres_admin_object_id
  postgres_admin_principal_name = var.postgres_admin_principal_name
  deployer_ip                   = var.deployer_ip
  tags                          = var.tags
}

# Deployed only once a pinned MLflow image reference is supplied (second pass).
module "mlflow_app" {
  source = "./modules/mlflow_app"
  count  = var.mlflow_image == "" ? 0 : 1

  name_prefix                  = "${var.prefix}${var.environment}"
  resource_group_name          = module.foundation.resource_group_name
  container_app_environment_id = module.foundation.container_app_environment_id
  acr_login_server             = module.foundation.acr_login_server
  mlflow_image                 = var.mlflow_image
  identity_id                  = module.foundation.identity_ids["id-mlflow"]
  identity_client_id           = module.foundation.identity_client_ids["id-mlflow"]
  postgres_fqdn                = module.foundation.postgres_fqdn
  mlflow_pg_principal          = "id-mlflow"
  artifacts_destination        = "wasbs://mlflow-artifacts@${module.foundation.storage_account_name}.blob.core.windows.net/"
  tags                         = var.tags
}

# Training / evaluation ACA Job (Phase 1, docs/02). Deployed once its image is
# built AND the MLflow App exists (it needs the tracking URI). Same two-pass
# pattern: foundation + MLflow first, then supply train_image.
module "train_job" {
  source = "./modules/train_job"
  count  = var.train_image == "" || var.mlflow_image == "" ? 0 : 1

  name_prefix                  = "${var.prefix}${var.environment}"
  resource_group_name          = module.foundation.resource_group_name
  location                     = var.location
  container_app_environment_id = module.foundation.container_app_environment_id
  acr_login_server             = module.foundation.acr_login_server
  train_image                  = var.train_image
  identity_id                  = module.foundation.identity_ids["id-jobs-train"]
  identity_client_id           = module.foundation.identity_client_ids["id-jobs-train"]
  mlflow_tracking_uri          = module.mlflow_app[0].mlflow_url
  postgres_fqdn                = module.foundation.postgres_fqdn
  results_pg_principal         = "id-jobs-train"
  schedule_cron                = var.train_schedule_cron
  tags                         = var.tags
}

# Batch scoring ACA Job (Phase 2, docs/04). Deployed once its image is built AND
# the MLflow App + train Job exist (it reads model versions produced by training).
# Same two-pass pattern: supply batch_image after the image is built.
module "batch_job" {
  source = "./modules/batch_job"
  count  = var.batch_image == "" || var.mlflow_image == "" ? 0 : 1

  name_prefix                  = "${var.prefix}${var.environment}"
  resource_group_name          = module.foundation.resource_group_name
  location                     = var.location
  container_app_environment_id = module.foundation.container_app_environment_id
  acr_login_server             = module.foundation.acr_login_server
  batch_image                  = var.batch_image
  identity_id                  = module.foundation.identity_ids["id-jobs-batch"]
  identity_client_id           = module.foundation.identity_client_ids["id-jobs-batch"]
  mlflow_tracking_uri          = module.mlflow_app[0].mlflow_url
  postgres_fqdn                = module.foundation.postgres_fqdn
  results_pg_principal         = "id-jobs-batch"
  schedule_cron                = var.batch_schedule_cron
  tags                         = var.tags
}

# Online serving ACA App (Phase 3, docs/05). Optional — skip if the workload is
# batch-only. Deployed once its image is built AND a concrete model version is
# pinned. Two-pass: supply serving_image + serving_model_version.
module "serving_app" {
  source = "./modules/serving_app"
  count  = var.serving_image == "" || var.mlflow_image == "" ? 0 : 1

  name_prefix                  = "${var.prefix}${var.environment}"
  resource_group_name          = module.foundation.resource_group_name
  container_app_environment_id = module.foundation.container_app_environment_id
  acr_login_server             = module.foundation.acr_login_server
  serving_image                = var.serving_image
  identity_id                  = module.foundation.identity_ids["id-serving"]
  identity_client_id           = module.foundation.identity_client_ids["id-serving"]
  mlflow_tracking_uri          = module.mlflow_app[0].mlflow_url
  model_name                   = var.serving_model_name
  model_version                = var.serving_model_version
  tags                         = var.tags
}

# Observability alert rules (Phase 4, docs/06). Always provisioned once the
# foundation exists; action_group_id is optional (empty = no notifications).
module "observability" {
  source = "./modules/observability"

  name_prefix                = "${var.prefix}${var.environment}"
  resource_group_name        = module.foundation.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = module.foundation.log_analytics_workspace_id
  action_group_id            = var.alert_action_group_id
  failure_count_threshold    = var.alert_failure_count_threshold
  tags                       = var.tags
}

# Workflow dashboard ACA App (Phase 4, docs/06). Deployed once its image is
# built; two-pass on dashboard_image.
module "dashboard" {
  source = "./modules/dashboard"
  count  = var.dashboard_image == "" || var.mlflow_image == "" ? 0 : 1

  name_prefix                  = "${var.prefix}${var.environment}"
  resource_group_name          = module.foundation.resource_group_name
  container_app_environment_id = module.foundation.container_app_environment_id
  acr_login_server             = module.foundation.acr_login_server
  dashboard_image              = var.dashboard_image
  identity_id                  = module.foundation.identity_ids["id-dashboard"]
  identity_client_id           = module.foundation.identity_client_ids["id-dashboard"]
  postgres_fqdn                = module.foundation.postgres_fqdn
  results_pg_principal         = "id-dashboard"
  mlflow_url                   = length(module.mlflow_app) > 0 ? module.mlflow_app[0].mlflow_url : ""
  grafana_url                  = module.foundation.grafana_endpoint
  subscription_id              = var.subscription_id
  tags                         = var.tags
}
