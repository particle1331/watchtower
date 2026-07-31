output "batch_job_name" {
  value       = azurerm_container_app_job.batch.name
  description = "ACA Job name; start ad-hoc runs with `az containerapp job start`."
}

output "batch_job_id" {
  value = azurerm_container_app_job.batch.id
}
