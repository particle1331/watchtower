// ML Platform — optional GPU training compute.
//
// Deploy after the main platform is up and GPU quota is approved:
//   az deployment group create -g ml-platform-demo -f infra/gpu-training.bicep \
//     --parameters suffix=<same-suffix-as-main>
//
// Tear down to stop GPU billing:
//   az ml compute delete --name <gpu-cluster-name> --workspace-name <aml-workspace> -g ml-platform-demo -y
//
// This is intentionally separate from main.bicep because GPU quota is region-specific,
// approval-heavy, and an order of magnitude more expensive than CPU compute. Keeping it
// separate lets the core platform deploy without waiting for GPU quota and lets the team
// delete the GPU cluster without touching MLflow, Redis, or batch inference.

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Unique suffix matching the main platform deployment.')
@minLength(3)
@maxLength(6)
param suffix string

@description('Azure ML workspace name. Defaults to the name created by main.bicep.')
param amlWorkspaceName string = 'ml-platform-aml-${suffix}'

@description('GPU training compute cluster name.')
param amlGpuComputeName string = 'gpu-cluster'

@description('GPU training VM size. Verify quota in the target region before deploying.')
param amlGpuVmSize string = 'Standard_NC24ads_A100_v4'

@description('Minimum nodes for GPU training cluster (0 = scale to zero).')
param amlGpuMinNodes int = 0

@description('Maximum nodes for GPU training cluster.')
param amlGpuMaxNodes int = 1

@description('VM priority. LowPriority uses Azure spot capacity and is cheaper but preemptible.')
@allowed(['Dedicated', 'LowPriority'])
param amlGpuVmPriority string = 'Dedicated'

// ── Tags: track cost per demo session ──────────────────────────────────────
param demoTag string = toLower('demo-${suffix}')

// ── Existing Azure ML workspace created by main.bicep ──────────────────────
resource amlWorkspace 'Microsoft.MachineLearningServices/workspaces@2024-04-01' existing = {
  name: amlWorkspaceName
}

// ── GPU compute cluster for fine-tuning / multi-GPU training POCs ──────────
resource amlGpuCompute 'Microsoft.MachineLearningServices/workspaces/computes@2024-04-01' = {
  parent: amlWorkspace
  name: amlGpuComputeName
  location: location
  tags: { demo: demoTag }
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: amlGpuVmSize
      vmPriority: amlGpuVmPriority
      scaleSettings: {
        minNodeCount: amlGpuMinNodes
        maxNodeCount: amlGpuMaxNodes
      }
      remoteLoginPortPublicAccess: 'Disabled'
    }
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────
output amlGpuComputeName string = amlGpuCompute.name
output amlGpuVmSize string = amlGpuVmSize
