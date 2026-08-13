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

variable "grafana_url" {
  type        = string
  description = "Azure Managed Grafana endpoint URL (for deep-links)."
}

variable "subscription_id" {
  type        = string
  description = "Azure subscription ID; needed by the dashboard to call the ACA Jobs execution API."
}

variable "tags" {
  type    = map(string)
  default = {}
}
