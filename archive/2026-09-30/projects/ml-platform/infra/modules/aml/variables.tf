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

variable "storage_account_id" {
  type        = string
  description = "Storage account resource ID shared with the rest of the platform."
}

variable "key_vault_id" {
  type        = string
  description = "Key Vault resource ID; AML uses it to resolve secrets at job submit time."
}

variable "application_insights_id" {
  type        = string
  description = "App Insights resource ID for AML diagnostics."
}

variable "submit_identity_id" {
  type        = string
  description = "Resource ID of the user-assigned identity allowed to submit jobs to this workspace."
}

variable "gpu_vm_size" {
  type        = string
  default     = "Standard_NC4as_T4_v3"
  description = "GPU VM SKU for the cluster; set at admission time."
}

variable "max_nodes" {
  type        = number
  default     = 4
  description = "Maximum cluster nodes; set at admission time per workload need."
}

variable "tags" {
  type    = map(string)
  default = {}
}
