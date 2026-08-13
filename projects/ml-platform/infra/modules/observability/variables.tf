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

variable "log_analytics_workspace_id" {
  type        = string
  description = "Log Analytics workspace resource ID; alert rules are scoped to this workspace."
}

variable "action_group_id" {
  type        = string
  default     = ""
  description = "Azure Monitor action group resource ID for notifications. Empty = rules created without notifications (dry-run)."
}

variable "failure_count_threshold" {
  type        = number
  default     = 5
  description = "Number of permanent FAILURE children per 15-minute window before the alert fires."
}

variable "tags" {
  type    = map(string)
  default = {}
}
