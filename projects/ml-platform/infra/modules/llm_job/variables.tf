variable "name_prefix" {
  type = string
}

variable "job_suffix" {
  type        = string
  description = "Stable suffix such as llm-register or llm-evaluate."
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

variable "image" {
  type        = string
  description = "Digest-pinned train image containing register_llm.py and ml_platform.llm.evaluator."
}

variable "identity_id" {
  type = string
}

variable "identity_client_id" {
  type = string
}

variable "mlflow_tracking_uri" {
  type = string
}

variable "postgres_fqdn" {
  type = string
}

variable "results_pg_principal" {
  type    = string
  default = "id-jobs-train"
}

variable "key_vault_url" {
  type = string
}

variable "model_api_key_secret" {
  type        = string
  default     = "model-api-key"
  description = "Key Vault secret name resolved by the shared pyfunc model at evaluation time."
}

variable "command" {
  type = list(string)
}

variable "eval_dataset" {
  type    = string
  default = ""
}

variable "model_name" {
  type    = string
  default = "llm-app"
}

variable "model_version" {
  type    = string
  default = "1"
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
