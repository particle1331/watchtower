###############################################################################
# Observability alert rules. Two application conditions emitted by
# the batch code and captured from ACA stdout/stderr in Log Analytics:
#   1. Permanent-failure children exceed the small-team threshold.
#   2. A batch circuit breaker trips.
#
# Job execution failures and missed schedules stay visible in ACA execution
# history and the results dashboard. They become alerts only after live log
# schemas and a per-workflow expected schedule have been validated.
# The action group is wired in via var.action_group_id; leave empty to create
# the rules without notifications (dry-run / test mode).
###############################################################################

# --- Rule 1: Permanent failures over threshold ------------------------------

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "permanent_failures" {
  name                = "${var.name_prefix}-alert-permanent-failures"
  resource_group_name = var.resource_group_name
  location            = var.location

  evaluation_frequency = "PT15M"
  window_duration      = "PT1H"
  scopes               = [var.log_analytics_workspace_id]
  severity             = 2
  description          = "Permanent FAILURE children exceed threshold in the last hour."

  criteria {
    query = <<-QUERY
      ContainerAppConsoleLogs_CL
      | where ContainerGroupName_s has "job-batch"
      | where Log_s has "permanently failed"
      | summarize failures = count() by bin(TimeGenerated, 15m)
      | where failures > ${var.failure_count_threshold}
    QUERY

    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  dynamic "action" {
    for_each = var.action_group_id == "" ? [] : [var.action_group_id]
    content {
      action_groups = [action.value]
    }
  }

  tags = var.tags
}

# --- Rule 2: Batch stalled (circuit breaker) --------------------------------

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "batch_stalled" {
  name                = "${var.name_prefix}-alert-batch-stalled"
  resource_group_name = var.resource_group_name
  location            = var.location

  evaluation_frequency = "PT15M"
  window_duration      = "PT1H"
  scopes               = [var.log_analytics_workspace_id]
  severity             = 1
  description          = "Batch circuit breaker tripped — no progress detected; parent marked FAILURE."

  criteria {
    query = <<-QUERY
      ContainerAppConsoleLogs_CL
      | where ContainerGroupName_s has "job-batch"
      | where Log_s has "circuit breaking"
      | summarize count() by bin(TimeGenerated, 15m)
    QUERY

    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  dynamic "action" {
    for_each = var.action_group_id == "" ? [] : [var.action_group_id]
    content {
      action_groups = [action.value]
    }
  }

  tags = var.tags
}
