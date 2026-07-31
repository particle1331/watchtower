output "train_job_name" {
  value       = azurerm_container_app_job.train.name
  description = "ACA Job name; start ad-hoc runs with `az containerapp job start`."
}

output "train_job_id" {
  value = azurerm_container_app_job.train.id
}
