targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Public Foundry project name')
param foundryProjectName string = 'order-resolution-public-managed-dev'

@description('Hosted agent name used to compose the Responses endpoint')
param hostedAgentName string = 'order-resolution-hosted'

@description('Public Foundry account name')
param foundryAccountName string = 'maffndaibfscpfhjr7sp4'

@description('Public Azure Container Registry name')
param containerRegistryName string = 'maffndacrbfscpfhjr7sp4'

@description('Application Insights component name')
param applicationInsightsName string = 'maffnd-mon-bfscpfhjr7sp4-appi'

@description('Linked Log Analytics workspace name')
param logAnalyticsWorkspaceName string = 'maffnd-mon-bfscpfhjr7sp4-law'

@description('Dedicated Storage account name for Foundry evaluation artifacts')
param evaluationStorageAccountName string = 'maffndeval${uniqueString(subscription().id, resourceGroup().id, foundryProjectName)}'

@description('Optional principal ID permitted to query Foundry traces')
param traceReaderPrincipalId string = ''

@description('Foundry chat deployment name')
param foundryChatDeploymentName string = 'gpt-4o-mini'

@description('Foundry embeddings deployment name')
param foundryEmbeddingsDeploymentName string = 'text-embedding-3-small'

@description('Dedicated Foundry evaluator deployment name')
param foundryEvaluationDeploymentName string = 'gpt-4o-mini-evaluation'

@minValue(1)
@description('Dedicated evaluator deployment capacity in thousands of tokens per minute')
param foundryEvaluationDeploymentCapacity int = 10

@description('Create the public PostgreSQL Flexible Server used by the workflow')
param createPostgresServer bool = true

@description('Public PostgreSQL server name')
param postgresServerName string = 'maffndpgbfscpfhjr7sp4cu'

@description('PostgreSQL administrator username')
param postgresAdminUsername string = 'pgadmin'

@description('PostgreSQL administrator password')
@secure()
param postgresAdminPassword string = ''

@description('Workflow database name')
param postgresDatabaseName string = 'maf_workflow'

@description('PostgreSQL server location')
param postgresLocation string = 'centralus'

var foundryProjectEndpoint = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
var foundryHostedResponsesUrl = '${foundryProjectEndpoint}/agents/${hostedAgentName}/endpoint/protocols/openai/responses?api-version=v1'

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource logAnalyticsReaderRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '73c42c96-874c-492b-b04d-ab87d138a893'
  scope: resourceGroup()
}

resource traceReaderApplicationInsightsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(traceReaderPrincipalId)) {
  name: guid(applicationInsights.id, traceReaderPrincipalId, logAnalyticsReaderRole.id)
  scope: applicationInsights
  properties: {
    roleDefinitionId: logAnalyticsReaderRole.id
    principalId: traceReaderPrincipalId
    principalType: 'User'
  }
}

resource traceReaderLogAnalyticsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(traceReaderPrincipalId)) {
  name: guid(logAnalyticsWorkspace.id, traceReaderPrincipalId, logAnalyticsReaderRole.id)
  scope: logAnalyticsWorkspace
  properties: {
    roleDefinitionId: logAnalyticsReaderRole.id
    principalId: traceReaderPrincipalId
    principalType: 'User'
  }
}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = if (createPostgresServer) {
  name: postgresServerName
  location: postgresLocation
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: postgresAdminUsername
    administratorLoginPassword: postgresAdminPassword
    version: '17'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource postgresAzureServicesFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = if (createPostgresServer) {
  name: 'allow-azure-services'
  parent: postgresServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource postgresWorkflowDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = if (createPostgresServer) {
  name: postgresDatabaseName
  parent: postgresServer
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

resource foundryEvaluationDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: foundryAccount
  name: foundryEvaluationDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: foundryEvaluationDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    raiPolicyName: 'Microsoft.Default'
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundryAccount
  name: foundryProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: foundryProjectName
    description: 'MAF order resolution public managed-state hosted project'
  }
}

resource projectFoundryUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, foundryProject.id, 'project-foundry-user')
  scope: foundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource projectScopedFoundryUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryProject.id, 'project-foundry-user')
  scope: foundryProject
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource projectTraceReaderApplicationInsightsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(applicationInsights.id, foundryProject.id, logAnalyticsReaderRole.id)
  scope: applicationInsights
  properties: {
    roleDefinitionId: logAnalyticsReaderRole.id
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource projectTraceReaderLogAnalyticsRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(logAnalyticsWorkspace.id, foundryProject.id, logAnalyticsReaderRole.id)
  scope: logAnalyticsWorkspace
  properties: {
    roleDefinitionId: logAnalyticsReaderRole.id
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource evaluationStorageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: evaluationStorageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource evaluationStorageBlobDataOwnerRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  scope: resourceGroup()
}

resource foundryAccountEvaluationStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(evaluationStorageAccount.id, foundryAccount.id, evaluationStorageBlobDataOwnerRole.id)
  scope: evaluationStorageAccount
  properties: {
    roleDefinitionId: evaluationStorageBlobDataOwnerRole.id
    principalId: foundryAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource foundryProjectEvaluationStorageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(evaluationStorageAccount.id, foundryProject.id, evaluationStorageBlobDataOwnerRole.id)
  scope: evaluationStorageAccount
  properties: {
    roleDefinitionId: evaluationStorageBlobDataOwnerRole.id
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource evaluationStorageAccountConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: foundryAccount
  name: 'evaluation-artifacts'
  properties: {
    category: 'AzureStorageAccount'
    target: evaluationStorageAccount.properties.primaryEndpoints.blob
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: evaluationStorageAccount.id
      location: evaluationStorageAccount.location
      purpose: 'foundry-evaluation-artifacts'
    }
  }
}

output foundryAccountName string = foundryAccount.name
output foundryProjectName string = foundryProject.name
output foundryProjectEndpoint string = foundryProjectEndpoint
output FOUNDRY_PROJECTS_ENDPOINT string = foundryProjectEndpoint
output FOUNDRY_PROJECT_ENDPOINT string = foundryProjectEndpoint
output FOUNDRY_PROJECT_ID string = foundryProject.id
output AZURE_AI_PROJECT_ENDPOINT string = foundryProjectEndpoint
output AZURE_AI_PROJECT_ID string = foundryProject.id
output foundryHostedResponsesUrl string = foundryHostedResponsesUrl
output FOUNDRY_MODEL_DEPLOYMENT_NAME string = foundryChatDeploymentName
output FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME string = foundryEmbeddingsDeploymentName
output FOUNDRY_EVAL_MODEL string = foundryEvaluationDeployment.name
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString
output APPLICATIONINSIGHTS_CONNECTION_STRING string = applicationInsights.properties.ConnectionString
output APPINSIGHTS_RESOURCE_ID string = applicationInsights.id
output FOUNDRY_EVALUATION_STORAGE_ACCOUNT_NAME string = evaluationStorageAccount.name
output postgresFullyQualifiedDomainName string = createPostgresServer ? postgresServer!.properties.fullyQualifiedDomainName : ''
output postgresDatabaseName string = postgresDatabaseName
output projectPrincipalId string = foundryProject.identity.principalId
output requiredBackendSettings array = [
  'FOUNDRY_PROJECTS_ENDPOINT=${foundryProjectEndpoint}'
  'APPLICATIONINSIGHTS_CONNECTION_STRING=${applicationInsights.properties.ConnectionString}'
]
output nextStep string = 'Run the local public release script, then verify hosted Responses conversations and Application Insights telemetry.'
