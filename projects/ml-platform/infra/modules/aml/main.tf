###############################################################################
# Azure ML workspace + min-zero GPU cluster (docs/08).
# Provisioned ONLY when the multi-GPU exception is admitted — not part of the
# baseline. The workspace is wired to the same self-hosted MLflow and Blob
# storage as everything else, so distributed-trained versions land in the
# shared registry unchanged.
###############################################################################

resource "azurerm_machine_learning_workspace" "aml" {
  name                    = "${var.name_prefix}-aml"
  resource_group_name     = var.resource_group_name
  location                = var.location
  application_insights_id = var.application_insights_id
  key_vault_id            = var.key_vault_id
  storage_account_id      = var.storage_account_id
  tags                    = var.tags

  identity {
    type = "SystemAssigned"
  }
}

# Min-zero GPU compute cluster — costs nothing idle; scales per job.
resource "azurerm_machine_learning_compute_cluster" "gpu" {
  name                          = "${var.name_prefix}-gpu-cluster"
  location                      = var.location
  machine_learning_workspace_id = azurerm_machine_learning_workspace.aml.id
  vm_priority                   = "Dedicated"
  vm_size                       = var.gpu_vm_size

  scale_settings {
    min_node_count                       = 0
    max_node_count                       = var.max_nodes
    scale_down_nodes_after_idle_duration = "PT5M"
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [var.submit_identity_id]
  }

  tags = var.tags
}
