output "serving_url" {
  value       = "https://${azurerm_container_app.serving.ingress[0].fqdn}"
  description = "Public HTTPS endpoint of the serving App."
}

output "serving_app_name" {
  value       = azurerm_container_app.serving.name
  description = "ACA App name; update the App definition to roll a new version or rollback."
}
