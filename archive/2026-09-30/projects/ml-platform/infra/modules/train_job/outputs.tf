output "train_job_name" {
  value       = azurerm_container_app_job.train.name
  description = "ACA Job name; start ad-hoc runs with `az containerapp job start`."
}

output "job_name" {
  value       = azurerm_container_app_job.train.name
  description = "ACA Job name for either the training or evaluation instance."
}

output "train_job_id" {
  value = azurerm_container_app_job.train.id
}
