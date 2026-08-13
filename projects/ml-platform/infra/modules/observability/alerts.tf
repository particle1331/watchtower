###############################################################################
# Observability alert rules (docs/06). Four conditions that page a small team:
#   1. Job execution failed.
#   2. Scheduled run missed (no execution in expected window).
#   3. Permanent-failure children exceed per-workflow threshold.
#   4. Batch stalled (circuit breaker tripped).
#
# These are Log Analytics scheduled-query alert rules backed by the ACA job
# execution logs and (for rules 3 & 4) the results DB via Diagnostic Settings.
# The action group is wired in via var.action_group_id; leave empty to create
# the rules without notifications (dry-run / test mode).
###############################################################################

# --- Rule 1: Job execution failed -------------------------------------------

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "job_failed" {
  name                = "${var.name_prefix}-alert-job-failed"
  resource_group_name = var.resource_group_name
  location            = var.location

  evaluation_frequency = "PT5M"
  window_duration      = "PT10M"
  scopes               = [var.log_analytics_workspace_id]
  severity             = 1
  description          = "An ACA Job execution ended with a non-zero exit code."

  criteria {
    query = <<-QUERY
      ContainerAppConsoleLogs_CL
      | where ContainerGroupName_s has "job"
      | where Log_s has "exit code"
      | summarize count() by ContainerGroupName_s, bin(TimeGenerated, 5m)
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

# --- Rule 2: Scheduled run missed -------------------------------------------

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "run_missed" {
  name                = "${var.name_prefix}-alert-run-missed"
  resource_group_name = var.resource_group_name
  location            = var.location

  evaluation_frequency = "PT1H"
  window_duration      = "PT2H"
  scopes               = [var.log_analytics_workspace_id]
  severity             = 2
  description          = "No ACA Job execution started in the expected window (missed cron trigger)."

  criteria {
    query = <<-QUERY
      ContainerAppConsoleLogs_CL
      | where ContainerGroupName_s has "job"
      | where TimeGenerated > ago(2h)
      | summarize executions = count() by bin(TimeGenerated, 1h)
      | where executions == 0
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

# --- Rule 3: Permanent failures over threshold ------------------------------
# Requires results DB rows to be forwarded to Log Analytics via custom logs or
# an application-level emit. Placeholder query; tune per workflow.

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
      AppTraces
      | where Message has "permanently failed"
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

# --- Rule 4: Batch stalled (circuit breaker) --------------------------------

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
      AppTraces
      | where Message has "circuit-breaker"
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
