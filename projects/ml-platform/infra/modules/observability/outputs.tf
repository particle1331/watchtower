output "alert_permanent_failures_id" {
  value = azurerm_monitor_scheduled_query_rules_alert_v2.permanent_failures.id
}

output "alert_batch_stalled_id" {
  value = azurerm_monitor_scheduled_query_rules_alert_v2.batch_stalled.id
}
