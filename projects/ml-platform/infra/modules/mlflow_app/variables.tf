variable "name_prefix" {
  type        = string
  description = "Prefix for the MLflow app name, e.g. \"mlpdev\"."
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

variable "mlflow_image" {
  type        = string
  description = "Fully-qualified MLflow image reference, pinned by digest (never :latest)."
}

variable "identity_id" {
  type        = string
  description = "Resource ID of the id-mlflow user-assigned identity."
}

variable "identity_client_id" {
  type        = string
  description = "Client ID of id-mlflow, exported as AZURE_CLIENT_ID for DefaultAzureCredential."
}

variable "postgres_fqdn" {
  type = string
}

variable "mlflow_pg_principal" {
  type        = string
  description = "Postgres principal name for the MLflow identity (matches grants.sql), e.g. \"id-mlflow\"."
}

variable "artifacts_destination" {
  type        = string
  description = "MLflow artifact store URI, e.g. wasbs://mlflow-artifacts@<account>.blob.core.windows.net/"
}

variable "tags" {
  type    = map(string)
  default = {}
}
