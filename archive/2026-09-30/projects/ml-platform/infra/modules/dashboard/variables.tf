variable "name_prefix" {
  type        = string
  description = "Base name prefix, e.g. mlpdev."
}

variable "resource_group_name" {
  type = string
}

variable "container_app_environment_id" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "dashboard_image" {
  type        = string
  description = "Pinned dashboard image reference (login_server/repo@sha256:...)."
}

variable "identity_id" {
  type        = string
  description = "Resource ID of the id-dashboard user-assigned identity."
}

variable "identity_client_id" {
  type        = string
  description = "Client ID of id-dashboard (selected by DefaultAzureCredential)."
}

variable "postgres_fqdn" {
  type = string
}

variable "results_pg_principal" {
  type        = string
  default     = "id-dashboard"
  description = "Postgres principal name for the dashboard identity (see grants.sql)."
}

variable "mlflow_url" {
  type        = string
  description = "Public URL of the self-hosted MLflow App (for deep-links)."
}

variable "auth_tenant_id" {
  type        = string
  description = "Entra tenant ID used as the Easy Auth OpenID issuer."
}

variable "auth_client_id" {
  type        = string
  description = "Client ID of the Entra app registration used by Easy Auth."
}

variable "auth_client_secret" {
  type        = string
  sensitive   = true
  description = "Client secret for the dashboard Entra app registration."
}

variable "operator_group_id" {
  type        = string
  description = "Entra group object ID allowed to trigger workflows."
}

variable "train_job_name" {
  type        = string
  description = "Deployed ACA training Job resource name."
}

variable "eval_job_name" {
  type        = string
  description = "Deployed ACA evaluation Job resource name."
}

variable "batch_job_name" {
  type        = string
  description = "Deployed ACA batch Job resource name."
}

variable "subscription_id" {
  type        = string
  description = "Azure subscription ID; needed by the dashboard to call the ACA Jobs execution API."
}

variable "tags" {
  type    = map(string)
  default = {}
}
