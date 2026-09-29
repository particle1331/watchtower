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

variable "key_vault_id" {
  type        = string
  description = "Key Vault to store the Redis connection string as a secret."
}

variable "redis_capacity" {
  type        = number
  default     = 1
  description = "Redis cache capacity (1 = C1 for Standard/Premium)."
}

variable "redis_family" {
  type        = string
  default     = "C"
  description = "Redis family: C (Basic/Standard) or P (Premium)."
}

variable "redis_sku" {
  type        = string
  default     = "Standard"
  description = "Redis SKU: Basic, Standard, or Premium."
}

variable "tags" {
  type    = map(string)
  default = {}
}
