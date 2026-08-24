output "resource_group_name" {
  value = module.foundation.resource_group_name
}

output "acr_login_server" {
  value = module.foundation.acr_login_server
}

output "acr_name" {
  value = module.foundation.acr_name
}

output "storage_account_name" {
  value = module.foundation.storage_account_name
}

output "key_vault_name" {
  value = module.foundation.key_vault_name
}

output "key_vault_url" {
  value = module.foundation.key_vault_url
}

output "postgres_fqdn" {
  value = module.foundation.postgres_fqdn
}

output "postgres_server_name" {
  value = module.foundation.postgres_server_name
}

output "identity_client_ids" {
  value = module.foundation.identity_client_ids
}

output "identity_principal_ids" {
  value       = module.foundation.identity_principal_ids
  description = "Managed-identity objectIds, injected into grants.sql to map Postgres principals."
}

output "mlflow_url" {
  value       = length(module.mlflow_app) > 0 ? module.mlflow_app[0].mlflow_url : ""
  description = "Empty until the second (MLflow) apply pass runs."
}

output "train_job_name" {
  value       = length(module.train_job) > 0 ? module.train_job[0].train_job_name : ""
  description = "Empty until the training image is built and applied."
}

output "eval_job_name" {
  value       = length(module.eval_job) > 0 ? module.eval_job[0].job_name : ""
  description = "Empty until the train/eval image is built and applied."
}

output "batch_job_name" {
  value       = length(module.batch_job) > 0 ? module.batch_job[0].batch_job_name : ""
  description = "Empty until the batch image is built and applied."
}

output "serving_url" {
  value       = length(module.serving_app) > 0 ? module.serving_app[0].serving_url : ""
  description = "Empty until the serving image and model version are set."
}

output "dashboard_url" {
  value       = length(module.dashboard) > 0 ? module.dashboard[0].dashboard_url : ""
  description = "Empty until the dashboard image is built and applied."
}

output "dashboard_auth_client_id" {
  value       = var.dashboard_auth_client_id
  description = "Audience/client ID used for authenticated dashboard API calls."
}

output "dashboard_auth_callback_url" {
  value       = length(module.dashboard) > 0 ? module.dashboard[0].auth_callback_url : ""
  description = "Web redirect URI required by the dashboard Entra app registration."
}

output "llm_register_job_name" {
  value       = length(module.llm_register_job) > 0 ? module.llm_register_job[0].job_name : ""
  description = "Manual ACA Job for registering the shared LLM pyfunc entrypoint."
}

output "llm_evaluate_job_name" {
  value       = length(module.llm_evaluate_job) > 0 ? module.llm_evaluate_job[0].job_name : ""
  description = "Manual ACA Job for evaluating the shared LLM pyfunc entrypoint."
}
