variable "name_prefix" {
  type        = string
  description = "Base name prefix, e.g. mlpdev."
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "container_app_environment_id" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "batch_image" {
  type        = string
  description = "Pinned batch/scoring image reference (login_server/repo@sha256:...)."
}

variable "identity_id" {
  type        = string
  description = "Resource id of the id-jobs-batch user-assigned identity."
}

variable "identity_client_id" {
  type        = string
  description = "Client id of id-jobs-batch (selected by DefaultAzureCredential)."
}

variable "mlflow_tracking_uri" {
  type        = string
  description = "HTTPS URL of the self-hosted MLflow App."
}

variable "postgres_fqdn" {
  type = string
}

variable "results_pg_principal" {
  type        = string
  default     = "id-jobs-batch"
  description = "Postgres principal name mapped to id-jobs-batch (see grants.sql)."
}

variable "schedule_cron" {
  type        = string
  default     = ""
  description = "UTC cron for the scheduled batch run; empty disables the schedule."
}

variable "data_source" {
  type        = string
  default     = ""
  description = "Default data source URL/path for the scheduled run."
}

variable "model_name" {
  type        = string
  default     = "wine-quality"
  description = "Registered model name to score with (@champion alias by default)."
}

variable "replica_timeout_seconds" {
  type    = number
  default = 3600
}

variable "cpu" {
  type    = number
  default = 1.0
}

variable "memory" {
  type    = string
  default = "2Gi"
}

variable "tags" {
  type    = map(string)
  default = {}
}
