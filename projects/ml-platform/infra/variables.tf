variable "subscription_id" {
  type        = string
  description = "Target Azure subscription ID."
}

variable "prefix" {
  type        = string
  default     = "mlp"
  description = "Short lowercase prefix for resource names."
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Environment name."
}

variable "location" {
  type        = string
  default     = "eastus2"
  description = "Azure region."
}

variable "resource_group_name" {
  type        = string
  description = "Resource group to create and hold every resource."
}

variable "postgres_admin_object_id" {
  type        = string
  description = "Entra objectId set as the Postgres AAD administrator (the deploying principal)."
}

variable "postgres_admin_principal_name" {
  type        = string
  description = "UPN of the Postgres AAD administrator."
}

variable "deployer_ip" {
  type        = string
  default     = ""
  description = "Public IP allowed through the Postgres firewall to run grants.sql."
}

variable "mlflow_image" {
  type        = string
  default     = ""
  description = "Pinned MLflow image (by digest). Empty on the first (foundation-only) apply."
}

variable "train_image" {
  type        = string
  default     = ""
  description = "Pinned train/eval image (by digest). Empty until the training image is built."
}

variable "llm_image" {
  type        = string
  default     = ""
  description = "Pinned train image used by the shared LLM register/evaluate ACA Jobs. Empty disables those Jobs."
}

variable "llm_eval_dataset" {
  type        = string
  default     = ""
  description = "Path or URL for the LLM evaluator's JSONL dataset. Empty disables the evaluation Job."
}

variable "llm_model_name" {
  type        = string
  default     = "llm-app"
  description = "Registered LLM model name supplied to the shared evaluator entrypoint."
}

variable "llm_model_version" {
  type        = string
  default     = "1"
  description = "LLM model version supplied to the shared evaluator entrypoint."
}

variable "train_schedule_cron" {
  type        = string
  default     = ""
  description = "UTC cron for the nightly retrain Job; empty disables the schedule."
}

variable "eval_data_source" {
  type        = string
  default     = "https://raw.githubusercontent.com/mlflow/mlflow/master/tests/datasets/winequality-white.csv"
  description = "Default held-out CSV source for the classical evaluation Job."
}

variable "eval_model_name" {
  type        = string
  default     = "wine-quality"
  description = "Default registered model evaluated by the ACA evaluation Job."
}

variable "eval_model_version" {
  type        = string
  default     = "1"
  description = "Fallback evaluation version when no execution override is supplied."
}

variable "eval_max_rmse" {
  type        = number
  default     = 0.8
  description = "Default maximum RMSE accepted by evaluation."
}

variable "batch_image" {
  type        = string
  default     = ""
  description = "Pinned batch/scoring image (by digest). Empty until the batch image is built."
}

variable "batch_schedule_cron" {
  type        = string
  default     = ""
  description = "UTC cron for the scheduled batch scoring Job; empty disables the schedule."
}

variable "serving_image" {
  type        = string
  default     = ""
  description = "Pinned serving image (by digest). Empty until the serving image is built."
}

variable "serving_model_name" {
  type        = string
  default     = "wine-quality"
  description = "Registered model name to serve."
}

variable "serving_model_version" {
  type        = string
  default     = ""
  description = "Exact model version to pin in the serving App definition."
}

variable "dashboard_image" {
  type        = string
  default     = ""
  description = "Pinned dashboard image (by digest). Empty until the dashboard image is built."
}

variable "dashboard_auth_client_id" {
  type        = string
  default     = ""
  description = "Entra app-registration client ID for dashboard Easy Auth."
}

variable "dashboard_auth_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Entra app-registration client secret for dashboard Easy Auth."
}

variable "dashboard_operator_group_id" {
  type        = string
  default     = ""
  description = "Entra group object ID allowed to trigger dashboard workflows."
}

variable "alert_action_group_id" {
  type        = string
  default     = ""
  description = "Azure Monitor action group resource ID for alert notifications. Empty = no notifications."
}

variable "alert_failure_count_threshold" {
  type        = number
  default     = 5
  description = "Permanent FAILURE children per window before the threshold alert fires."
}

variable "tags" {
  type = map(string)
  default = {
    project = "ml-platform"
    tier    = "mvp"
  }
  description = "Tags applied to every resource."
}
