###############################################################################
# Foundation module — the entire Phase 0 footprint.
#
# Everything every later phase depends on: registry, container-apps environment
# + Log Analytics, a two-database Postgres flexible server, a storage account
# with per-concern containers, Key Vault, and Log Analytics. Per-workload managed
# identities and their role assignments live in identities.tf.
#
# Baseline networking is PUBLIC endpoints protected by identity (managed-identity
# auth to Postgres/Blob/Key Vault, ACR pull via identity). Private endpoints are
# a deferred production-hardening step.
###############################################################################

resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# Random suffix for globally-unique names (storage account, ACR, Key Vault).
resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  base = "${var.prefix}${var.environment}"
}

#------------------------------------------------------------------------------
# Container registry — immutable images, referenced by digest, never `latest`.
# Admin user disabled: pulls happen via managed identity only.
#------------------------------------------------------------------------------
resource "azurerm_container_registry" "acr" {
  name                = "${local.base}acr${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "Standard"
  admin_enabled       = false
  tags                = var.tags
}

#------------------------------------------------------------------------------
# Log Analytics + Container Apps environment. One environment hosts every Job
# and App; Log Analytics is attached for infra telemetry and alerting.
#------------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "law" {
  name                = "${local.base}-law"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_container_app_environment" "cae" {
  name                       = "${local.base}-cae"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id
  tags                       = var.tags
}

#------------------------------------------------------------------------------
# Storage — MLflow artifacts, batch outputs, immutable manifests, datasets.
# Blob versioning + soft delete give immutable artifact identity. Hierarchical
# namespace stays off (we use Blob, not ADLS Gen2). Access is via managed
# identity (shared_access_key usage disabled).
#------------------------------------------------------------------------------
resource "azurerm_storage_account" "sa" {
  name                            = "${local.base}st${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  tags                            = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_container" "containers" {
  for_each              = toset(["mlflow-artifacts", "batch-outputs", "manifests", "datasets"])
  name                  = each.value
  storage_account_id    = azurerm_storage_account.sa.id
  container_access_type = "private"
}

#------------------------------------------------------------------------------
# Key Vault — connection strings and any unavoidable secrets, read at runtime
# via managed identity (RBAC authorization; no access policies, no secrets in
# images or Git).
#------------------------------------------------------------------------------
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "kv" {
  name                       = "${local.base}kv${random_string.suffix.result}"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = var.tags
}

#------------------------------------------------------------------------------
# Postgres flexible server — one small server, two logical databases
# (`mlflow` + `results`). Entra-only auth (no password auth): each workload
# connects with its own managed identity. Per-database privileges are applied
# post-provision by infra/grants.sql, the one deliberate exception to pure
# declarative IaC.
#------------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "pg" {
  name                          = "${local.base}-pg-${random_string.suffix.result}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  version                       = "16"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  zone                          = "1"
  public_network_access_enabled = true

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = data.azurerm_client_config.current.tenant_id
  }
}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "admin" {
  server_name         = azurerm_postgresql_flexible_server.pg.name
  resource_group_name = azurerm_resource_group.this.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = var.postgres_admin_object_id
  principal_name      = var.postgres_admin_principal_name
  principal_type      = "User"
}

resource "azurerm_postgresql_flexible_server_database" "mlflow" {
  name      = "mlflow"
  server_id = azurerm_postgresql_flexible_server.pg.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_database" "results" {
  name      = "results"
  server_id = azurerm_postgresql_flexible_server.pg.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# MVP: allow access from Azure services (ACA workloads) and the deploying host
# that runs grants.sql. Prod hardening replaces this with private networking.
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "deployer" {
  count            = var.deployer_ip == "" ? 0 : 1
  name             = "allow-deployer"
  server_id        = azurerm_postgresql_flexible_server.pg.id
  start_ip_address = var.deployer_ip
  end_ip_address   = var.deployer_ip
}
