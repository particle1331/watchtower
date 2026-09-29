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

variable "serving_image" {
  type        = string
  description = "Pinned serving image reference (login_server/repo@sha256:...)."
}

variable "identity_id" {
  type        = string
  description = "Resource ID of the id-serving user-assigned identity."
}

variable "identity_client_id" {
  type        = string
  description = "Client ID of id-serving (selected by DefaultAzureCredential)."
}

variable "mlflow_tracking_uri" {
  type        = string
  description = "HTTPS URL of the self-hosted MLflow App."
}

variable "model_name" {
  type        = string
  description = "Registered model name to serve."
}

variable "model_version" {
  type        = string
  description = "Exact model version to pin in the App definition (never a floating alias)."
}

variable "min_replicas" {
  type        = number
  default     = 1
  description = "Minimum replicas; set >0 to keep the model warm."
}

variable "max_replicas" {
  type    = number
  default = 3
}

variable "cpu" {
  type    = number
  default = 0.5
}

variable "memory" {
  type    = string
  default = "1Gi"
}

variable "tags" {
  type    = map(string)
  default = {}
}
