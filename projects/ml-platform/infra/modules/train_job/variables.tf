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

variable "train_image" {
  type        = string
  description = "Pinned train/eval image reference (login_server/repo@sha256:...)."
}

variable "identity_id" {
  type        = string
  description = "Resource id of the id-jobs-train user-assigned identity."
}

variable "identity_client_id" {
  type        = string
  description = "Client id of id-jobs-train (selected by DefaultAzureCredential)."
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
  default     = "id-jobs-train"
  description = "Postgres principal name mapped to id-jobs-train (see grants.sql)."
}

variable "schedule_cron" {
  type        = string
  default     = ""
  description = "UTC cron for the nightly retrain; empty disables the schedule."
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
