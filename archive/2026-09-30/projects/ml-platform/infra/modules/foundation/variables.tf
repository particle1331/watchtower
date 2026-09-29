variable "prefix" {
  type        = string
  description = "Short lowercase prefix for resource names, e.g. \"mlp\"."
}

variable "environment" {
  type        = string
  description = "Environment name, e.g. \"dev\"."
}

variable "location" {
  type        = string
  description = "Azure region, e.g. \"eastus2\"."
}

variable "resource_group_name" {
  type        = string
  description = "Name of the resource group to create and place all resources in."
}

variable "postgres_admin_object_id" {
  type        = string
  description = "Entra objectId set as the Postgres AAD administrator (the deploying principal). Used by grants.sql to create per-workload principals."
}

variable "postgres_admin_principal_name" {
  type        = string
  description = "UPN/display name of the Postgres AAD administrator principal."
}

variable "deployer_ip" {
  type        = string
  default     = ""
  description = "Public IP allowed through the Postgres firewall so the deploy host can run grants.sql. Empty disables the rule."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags applied to every resource."
}
