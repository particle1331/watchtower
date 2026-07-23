// ML Platform — Azure infrastructure for learning demo.
//
// Deploy:
//   az group create -n ml-platform-demo -l southeastasia
//   az deployment group create -g ml-platform-demo -f infra/main.bicep
//
// Optional GPU training compute (deploy separately after quota approval):
//   az deployment group create -g ml-platform-demo -f infra/gpu-training.bicep
//
// Tear down:
//   az group delete -n ml-platform-demo --yes --no-wait
//
// Cost: ~$0.50/hour running. Tear down between sessions.
//
// See: learning/mlops/09-azure-iac.ipynb

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Unique suffix for globally-unique resource names (e.g. your initials).')
@minLength(3)
@maxLength(6)
param suffix string

// ── Tags: track cost per demo session ──────────────────────────────────────
param demoTag string = toLower('demo-${suffix}')

// ── MLflow ─────────────────────────────────────────────────────────────────
@description('MLflow tracking URI path (e.g. mlflow).')
param mlflowUriPath string = 'mlflow'

// ── PostgreSQL ─────────────────────────────────────────────────────────────
@description('PostgreSQL admin login. Defaults to Key Vault secret if left empty.')
@secure()
param pgAdminLogin string = 'mlflowadmin'

@description('PostgreSQL admin password. Auto-generated if empty.')
@secure()
param pgAdminPassword string = newGuid()

@description('PostgreSQL database name for MLflow metadata.')
param pgDatabaseName string = 'mlflow'

@description('PostgreSQL SKU — B1ms is burstable, ~$17/month running 24/7.')
param pgSkuName string = 'B_Standard_B1ms'
param pgSkuTier string = 'Burstable'
param pgStorageGB int = 32

// ── Containers ─────────────────────────────────────────────────────────────
@description('Container Apps environment name.')
param containerEnvName string = 'ml-platform-env'

@description('MLflow container app name.')
param mlflowAppName string = 'mlflow'

@description('Redis container app name.')
param redisAppName string = 'redis'

// ── Storage (Blob) ────────────────────────────────────────────────────────
@description('Storage account name — lowercase alphanumeric only.')
param storageName string = replace('mlplatform${suffix}', '-', '')

@description('Blob container for MLflow artifacts.')
param mlflowContainerName string = 'mlflow-artifacts'

// ── Key Vault ──────────────────────────────────────────────────────────────
@description('Key Vault name — lowercase alphanumeric only.')
param keyVaultName string = 'ml-platform-kv-${suffix}'

// ── Container Registry ─────────────────────────────────────────────────────
@description('ACR name — lowercase alphanumeric only.')
param acrName string = replace('mlplatform${suffix}', '-', '')

// ── Azure OpenAI ───────────────────────────────────────────────────────────
@description('Azure OpenAI account name.')
param openAiName string = 'ml-platform-aoai-${suffix}'

// ── Azure Functions ────────────────────────────────────────────────────────
@description('Functions app name — globally unique.')
param functionAppName string = 'ml-platform-fn-${suffix}'

// ── Azure Machine Learning ─────────────────────────────────────────────────
@description('Azure ML workspace name.')
param amlWorkspaceName string = 'ml-platform-aml-${suffix}'

@description('CPU training compute cluster name.')
param amlCpuComputeName string = 'cpu-cluster'

@description('CPU training VM size.')
param amlCpuVmSize string = 'Standard_DS3_v2'

@description('Minimum nodes for CPU training cluster (0 = scale to zero).')
param amlCpuMinNodes int = 0

@description('Maximum nodes for CPU training cluster.')
param amlCpuMaxNodes int = 2

// ═══════════════════════════════════════════════════════════════════════════
// Resources
// ═══════════════════════════════════════════════════════════════════════════

// ── Log Analytics workspace (shared by all services) ──────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'ml-platform-logs-${suffix}'
  location: location
  tags: { demo: demoTag }
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── Application Insights ───────────────────────────────────────────────────
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'ml-platform-ai-${suffix}'
  location: location
  kind: 'web'
  tags: { demo: demoTag }
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// ── Key Vault ──────────────────────────────────────────────────────────────
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: { demo: demoTag }
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A'; name: 'standard' }
    enableSoftDelete: true
    enableRbacAuthorization: true
  }
}

// ── PostgreSQL Flexible Server ─────────────────────────────────────────────
resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'ml-platform-pg-${suffix}'
  location: location
  tags: { demo: demoTag }
  sku: { name: pgSkuName; tier: pgSkuTier }
  properties: {
    administratorLogin: pgAdminLogin
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: pgStorageGB }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
    version: '16'
  }

  resource database 'databases' = {
    name: pgDatabaseName
  }
}

// ── Storage Account + Blob Container ───────────────────────────────────────
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: { demo: demoTag }
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }

  resource blobService 'blobServices' = {
    name: 'default'

    resource mlflowContainer 'containers' = {
      name: mlflowContainerName
      properties: {
        publicAccess: 'None'
      }
    }
  }
}

// ── Container Registry ─────────────────────────────────────────────────────
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: { demo: demoTag }
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true
  }
}

// ── Azure Machine Learning workspace ───────────────────────────────────────
resource amlWorkspace 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: amlWorkspaceName
  location: location
  tags: { demo: demoTag }
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    friendlyName: amlWorkspaceName
    storageAccount: storageAccount.id
    keyVault: keyVault.id
    applicationInsights: appInsights.id
    containerRegistry: containerRegistry.id
    hbiWorkspace: false
  }
}

// ── Azure ML CPU compute cluster (scale-to-zero) ───────────────────────────
resource amlCpuCompute 'Microsoft.MachineLearningServices/workspaces/computes@2024-04-01' = {
  parent: amlWorkspace
  name: amlCpuComputeName
  location: location
  tags: { demo: demoTag }
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: amlCpuVmSize
      vmPriority: 'Dedicated'
      scaleSettings: {
        minNodeCount: amlCpuMinNodes
        maxNodeCount: amlCpuMaxNodes
      }
      remoteLoginPortPublicAccess: 'Disabled'
    }
  }
}

// ── Container Apps Environment ────────────────────────────────────────────
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerEnvName
  location: location
  tags: { demo: demoTag }
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── MLflow Container App ────────────────────────────────────────────────────
resource mlflowApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: mlflowAppName
  location: location
  tags: { demo: demoTag }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 5000
        transport: 'http'
      }
      secrets: [
        {
          name: 'pg-connection-string'
          value: 'postgresql://${pgAdminLogin}:${pgAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${pgDatabaseName}'
        }
      ]
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mlflow'
          image: 'ghcr.io/mlflow/mlflow:v3.5.0'
          env: [
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'MLFLOW_S3_ENDPOINT_URL'
              value: 'https://${storageAccount.name}.blob.core.windows.net'
            }
          ]
          command: [
            'mlflow'
            'server'
            '--backend-store-uri'
            'postgresql://${pgAdminLogin}:${pgAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${pgDatabaseName}'
            '--default-artifact-root'
            'wasbs://${mlflowContainerName}@${storageAccount.name}.blob.core.windows.net/artifacts'
            '--host'
            '0.0.0.0'
            '--port'
            '5000'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ── Redis Container App ─────────────────────────────────────────────────────
resource redisApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: redisAppName
  location: location
  tags: { demo: demoTag }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: false
        targetPort: 6379
        transport: 'tcp'
      }
    }
    template: {
      containers: [
        {
          name: 'redis'
          image: 'redis:7-alpine'
          command: [
            'redis-server'
            '--appendonly'
            'no'
            '--maxmemory'
            '256mb'
            '--maxmemory-policy'
            'noeviction'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Liveness'
              tcpSocket: { port: 6379 }
              initialDelaySeconds: 10
              periodSeconds: 15
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ── Azure Functions App (consumption) ───────────────────────────────────────
resource functionsHostingPlan 'Microsoft.Web/serverFarms@2023-12-01' = {
  name: 'ml-platform-fn-plan-${suffix}'
  location: location
  tags: { demo: demoTag }
  kind: 'functionapp'
  sku: { name: 'Y1'; tier: 'Dynamic' }
}

resource functionStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: replace('mlplatformfn${suffix}', '-', '')
  location: location
  tags: { demo: demoTag }
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: functionAppName
  location: location
  tags: { demo: demoTag }
  kind: 'functionapp'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: functionsHostingPlan.id
    siteConfig: {
      appSettings: [
        { name: 'AzureWebJobsStorage'; value: 'DefaultEndpointsProtocol=https;AccountName=${functionStorage.name};AccountKey=${functionStorage.listKeys().keys[0].value};EndpointSuffix=core.windows.net' }
        { name: 'FUNCTIONS_EXTENSION_VERSION'; value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME'; value: 'python' }
        { name: 'APPINSIGHTS_INSTRUMENTATIONKEY'; value: appInsights.properties.InstrumentationKey }
        { name: 'MLFLOW_TRACKING_URI'; value: 'https://${mlflowApp.properties.configuration.ingress.fqdn}' }
        { name: 'KEY_VAULT_NAME'; value: keyVault.name }
      ]
      cors: {
        allowedOrigins: ['*']
      }
      ftpsState: 'Disabled'
      http20Enabled: true
      minTlsVersion: '1.2'
    }
    httpsOnly: true
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────
output mlflowUrl string = 'https://${mlflowApp.properties.configuration.ingress.fqdn}'
output redisInternalFqdn string = redisApp.properties.configuration.ingress.fqdn
output postgresFqdn string = postgresServer.properties.fullyQualifiedDomainName
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output keyVaultUri string = keyVault.properties.vaultUri
output acrLoginServer string = containerRegistry.properties.loginServer
output amlWorkspaceName string = amlWorkspace.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output appInsightsKey string = appInsights.properties.InstrumentationKey
