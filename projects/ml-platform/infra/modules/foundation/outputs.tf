output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "location" {
  value = azurerm_resource_group.this.location
}

output "acr_login_server" {
  value = azurerm_container_registry.acr.login_server
}

output "acr_name" {
  value = azurerm_container_registry.acr.name
}

output "container_app_environment_id" {
  value = azurerm_container_app_environment.cae.id
}

output "storage_account_name" {
  value = azurerm_storage_account.sa.name
}

output "storage_blob_endpoint" {
  value = azurerm_storage_account.sa.primary_blob_endpoint
}

output "key_vault_name" {
  value = azurerm_key_vault.kv.name
}

output "key_vault_id" {
  value = azurerm_key_vault.kv.id
}

output "key_vault_url" {
  value       = azurerm_key_vault.kv.vault_uri
  description = "Key Vault URI used by workloads to resolve runtime secrets."
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.pg.fqdn
}

output "postgres_server_name" {
  value = azurerm_postgresql_flexible_server.pg.name
}

output "grafana_endpoint" {
  value = azurerm_dashboard_grafana.grafana.endpoint
}

output "log_analytics_workspace_id" {
  value       = azurerm_log_analytics_workspace.law.id
  description = "Log Analytics workspace ID; used by the observability module for alert rules."
}

output "log_analytics_workspace_resource_id" {
  value       = azurerm_log_analytics_workspace.law.id
  description = "Alias; same as log_analytics_workspace_id."
}

# Identity IDs (for binding to Job/App definitions) and client IDs (for the
# AZURE_CLIENT_ID env that DefaultAzureCredential uses to pick the right MI).
output "identity_ids" {
  value = { for k, v in azurerm_user_assigned_identity.workload : k => v.id }
}

output "identity_client_ids" {
  value = { for k, v in azurerm_user_assigned_identity.workload : k => v.client_id }
}

output "identity_principal_ids" {
  value = { for k, v in azurerm_user_assigned_identity.workload : k => v.principal_id }
}
