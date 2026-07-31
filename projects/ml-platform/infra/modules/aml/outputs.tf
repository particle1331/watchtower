output "workspace_name" {
  value       = azurerm_machine_learning_workspace.aml.name
  description = "AML workspace name; use as --workspace-name in az ml job create."
}

output "workspace_id" {
  value = azurerm_machine_learning_workspace.aml.id
}

output "cluster_name" {
  value       = azurerm_machine_learning_compute_cluster.gpu.name
  description = "Compute cluster name; reference in job.yml as azureml:<cluster-name>."
}
