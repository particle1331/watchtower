output "dashboard_url" {
  value       = "https://${azurerm_container_app.dashboard.ingress[0].fqdn}"
  description = "Public HTTPS endpoint of the workflow dashboard App."
}

output "dashboard_app_name" {
  value       = azurerm_container_app.dashboard.name
  description = "ACA App name."
}

output "auth_callback_url" {
  value       = "https://${azurerm_container_app.dashboard.ingress[0].fqdn}/.auth/login/aad/callback"
  description = "Add this Web redirect URI to the dashboard Entra app registration."
}
