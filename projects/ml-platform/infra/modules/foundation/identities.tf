###############################################################################
# Per-workload managed identities + least-privilege role assignments (docs/01).
#
# Every workload gets its OWN user-assigned identity with the minimum roles it
# needs. No workload shares an identity; none gets broad Contributor. Two
# workloads need permissions with no suitable built-in role (the dashboard's
# scoped Job-start, and CI's ACA definition-update), so we define narrow custom
# roles for exactly those actions.
#
# NOTE: writing role assignments needs Owner or User Access Administrator on the
# scope. Contributor cannot. See docs/01 — Open decisions (grant requested,
# RG-scoped, by objectId).
###############################################################################

locals {
  identities = [
    "id-jobs-train", # training/eval Jobs
    "id-jobs-batch", # batch inference Jobs
    "id-serving",    # serving App
    "id-mlflow",     # self-hosted MLflow App
    "id-dashboard",  # catalog + launcher dashboard App
    "id-ci",         # GitHub Actions (federated OIDC in real CI)
  ]
}

resource "azurerm_user_assigned_identity" "workload" {
  for_each            = toset(local.identities)
  name                = "${local.base}-${each.value}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  tags                = var.tags
}

#------------------------------------------------------------------------------
# ACR pull for every identity that runs a container; ACR push for CI only.
#------------------------------------------------------------------------------
resource "azurerm_role_assignment" "acr_pull" {
  for_each             = toset(["id-jobs-train", "id-jobs-batch", "id-serving", "id-mlflow", "id-dashboard"])
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.workload[each.value].principal_id
}

resource "azurerm_role_assignment" "acr_push_ci" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.workload["id-ci"].principal_id
}

#------------------------------------------------------------------------------
# Blob data access. Train/batch/mlflow read+write; serving reads only.
# (MVP scopes at the storage-account level; prod can scope per container.)
#------------------------------------------------------------------------------
resource "azurerm_role_assignment" "blob_contributor" {
  for_each             = toset(["id-jobs-train", "id-jobs-batch", "id-mlflow"])
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.workload[each.value].principal_id
}

resource "azurerm_role_assignment" "blob_reader" {
  scope                = azurerm_storage_account.sa.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.workload["id-serving"].principal_id
}

#------------------------------------------------------------------------------
# Key Vault secret read for workloads that resolve connection strings at runtime.
#------------------------------------------------------------------------------
resource "azurerm_role_assignment" "kv_secrets_user" {
  for_each             = toset(["id-jobs-train", "id-jobs-batch", "id-serving", "id-mlflow"])
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload[each.value].principal_id
}

#------------------------------------------------------------------------------
# Dashboard reads the results DB via Postgres (grants.sql) and Log Analytics.
#------------------------------------------------------------------------------
resource "azurerm_role_assignment" "dashboard_law_reader" {
  scope                = azurerm_log_analytics_workspace.law.id
  role_definition_name = "Log Analytics Reader"
  principal_id         = azurerm_user_assigned_identity.workload["id-dashboard"].principal_id
}

#------------------------------------------------------------------------------
# Custom role: start ACA Job executions. Assigned to the dashboard, scoped to
# the resource group. Every manual start is audited via results.triggered_by.
#------------------------------------------------------------------------------
resource "azurerm_role_definition" "job_starter" {
  name        = "${local.base}-aca-job-starter"
  scope       = azurerm_resource_group.this.id
  description = "Start ACA Job executions (manual trigger) — nothing else."

  permissions {
    actions = [
      "Microsoft.App/jobs/read",
      "Microsoft.App/jobs/start/action",
      "Microsoft.App/jobs/executions/read",
    ]
    not_actions = []
  }

  assignable_scopes = [azurerm_resource_group.this.id]
}

resource "azurerm_role_assignment" "dashboard_job_starter" {
  scope              = azurerm_resource_group.this.id
  role_definition_id = azurerm_role_definition.job_starter.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.workload["id-dashboard"].principal_id
}

#------------------------------------------------------------------------------
# Custom role: update ACA Job/App definitions (image digest, env, schedule).
# Assigned to CI. No runtime data access — CI never reads Blob or the DBs.
#------------------------------------------------------------------------------
resource "azurerm_role_definition" "aca_deployer" {
  name        = "${local.base}-aca-deployer"
  scope       = azurerm_resource_group.this.id
  description = "Create/update ACA Job and App definitions — no data-plane access."

  permissions {
    actions = [
      "Microsoft.App/jobs/read",
      "Microsoft.App/jobs/write",
      "Microsoft.App/containerApps/read",
      "Microsoft.App/containerApps/write",
      "Microsoft.App/managedEnvironments/read",
    ]
    not_actions = []
  }

  assignable_scopes = [azurerm_resource_group.this.id]
}

resource "azurerm_role_assignment" "ci_aca_deployer" {
  scope              = azurerm_resource_group.this.id
  role_definition_id = azurerm_role_definition.aca_deployer.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.workload["id-ci"].principal_id
}
