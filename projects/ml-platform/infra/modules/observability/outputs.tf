output "alert_job_failed_id" {
  value = azurerm_monitor_scheduled_query_rules_alert_v2.job_failed.id
}

output "alert_run_missed_id" {
  value = azurerm_monitor_scheduled_query_rules_alert_v2.run_missed.id
}

output "alert_permanent_failures_id" {
  value = azurerm_monitor_scheduled_query_rules_alert_v2.permanent_failures.id
}

output "alert_batch_stalled_id" {
  value = azurerm_monitor_scheduled_query_rules_alert_v2.batch_stalled.id
}
