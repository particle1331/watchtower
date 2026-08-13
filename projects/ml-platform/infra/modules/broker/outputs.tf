output "redis_hostname" {
  value       = azurerm_redis_cache.broker.hostname
  description = "Redis hostname; reference in KEDA scale rule."
}

output "redis_ssl_port" {
  value = azurerm_redis_cache.broker.ssl_port
}

output "redis_url_secret_name" {
  value       = azurerm_key_vault_secret.redis_url.name
  description = "Key Vault secret name holding the Redis connection string."
}
