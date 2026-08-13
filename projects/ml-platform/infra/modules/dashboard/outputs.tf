output "dashboard_url" {
  value       = "https://${azurerm_container_app.dashboard.ingress[0].fqdn}"
  description = "Public HTTPS endpoint of the workflow dashboard App."
}

output "dashboard_app_name" {
  value       = azurerm_container_app.dashboard.name
  description = "ACA App name."
}
