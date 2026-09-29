output "mlflow_url" {
  value       = "https://${azurerm_container_app.mlflow.ingress[0].fqdn}"
  description = "Public HTTPS endpoint of the self-hosted MLflow tracking/registry server."
}
