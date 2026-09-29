###############################################################################
# Optional managed Redis broker + KEDA scale rule.
# Adopted ONLY when the results-DB continuation model can no longer keep up
# with fan-out. Do not provision this in the baseline.
###############################################################################

# Managed Azure Cache for Redis — no Redis server to operate.
resource "azurerm_redis_cache" "broker" {
  name                = "${var.name_prefix}-broker"
  resource_group_name = var.resource_group_name
  location            = var.location
  capacity            = var.redis_capacity
  family              = var.redis_family
  sku_name            = var.redis_sku

  enable_non_ssl_port = false
  minimum_tls_version = "1.2"

  redis_configuration {}

  tags = var.tags
}

# Store the Redis connection string in Key Vault so workers fetch it via
# managed identity at runtime — no secrets in environment variables.
resource "azurerm_key_vault_secret" "redis_url" {
  name         = "redis-url"
  value        = "rediss://:${azurerm_redis_cache.broker.primary_access_key}@${azurerm_redis_cache.broker.hostname}:${azurerm_redis_cache.broker.ssl_port}/0"
  key_vault_id = var.key_vault_id

  lifecycle {
    ignore_changes = [value]  # rotated externally; do not overwrite on re-apply
  }
}

# KEDA ScaledJob: scale up ACA batch workers on Redis list length.
# The ScaledJob definition is added to the batch_job ACA Job via a separate
# azurerm_container_app_job resource; KEDA integration is not yet supported
# directly in the azurerm provider — documented here as a placeholder until
# the provider exposes it, at which point it replaces the manual az CLI step
# in deploy.ps1.
#
# Manual equivalent (run after apply):
#   az containerapp job update \
#     --name <batch-job-name> \
#     --resource-group <rg> \
#     --min-executions 0 --max-executions 10 \
#     --scale-rule-name redis-queue \
#     --scale-rule-type redis \
#     --scale-rule-metadata "listName=celery address=<redis-host>:6380 ssl=true" \
#     --scale-rule-auth "connection=redis-connection-string"
