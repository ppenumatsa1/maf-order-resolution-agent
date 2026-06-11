targetScope = 'subscription'

@description('AZD environment name.')
param environmentName string

@description('Deployment location.')
param location string

@description('Prefix used for Azure resource names.')
param namePrefix string = 'mafapp'

@description('Azure Database for PostgreSQL administrator login. Use a non-reserved value.')
param postgresAdministratorLogin string = 'pgadminuser'

@secure()
@description('Azure Database for PostgreSQL administrator password. Set with: azd env set POSTGRES_ADMIN_PASSWORD <value>')
param postgresAdministratorPassword string

@description('Application database name.')
param postgresDatabaseName string = 'maf_workflow'

@secure()
@description('Optional MCP API key. Leave empty when MCP is not configured.')
param mcpApiKey string = ''

@secure()
@description('Optional MCP bearer token. Leave empty when MCP is not configured.')
param mcpBearerToken string = ''

@description('Optional MCP server URL.')
param mcpServerUrl string = ''

@description('Azure AI Foundry project name.')
param foundryProjectName string = 'order-resolution'

@description('Azure AI Foundry chat model deployment name exposed to the backend.')
param foundryChatDeploymentName string = 'gpt-4o-mini'

@description('Azure AI Foundry chat model format.')
param foundryChatModelFormat string = 'OpenAI'

@description('Azure AI Foundry chat model name.')
param foundryChatModelName string = 'gpt-4o-mini'

@description('Azure AI Foundry chat model version. Override when the target region requires a different version.')
param foundryChatModelVersion string = '2024-07-18'

@description('Azure AI Foundry chat deployment SKU name. Keep low-cost defaults and override per-region/quota as needed.')
param foundryChatDeploymentSkuName string = 'GlobalStandard'

@description('Azure AI Foundry chat deployment capacity.')
param foundryChatDeploymentCapacity int = 1

@description('Azure AI Foundry embeddings deployment name exposed to the backend.')
param foundryEmbeddingsDeploymentName string = 'text-embedding-3-small'

@description('Azure AI Foundry embeddings model format.')
param foundryEmbeddingsModelFormat string = 'OpenAI'

@description('Azure AI Foundry embeddings model name.')
param foundryEmbeddingsModelName string = 'text-embedding-3-small'

@description('Azure AI Foundry embeddings model version. Override when the target region requires a different version.')
param foundryEmbeddingsModelVersion string = '1'

@description('Azure AI Foundry embeddings deployment SKU name. Keep low-cost defaults and override per-region/quota as needed.')
param foundryEmbeddingsDeploymentSkuName string = 'GlobalStandard'

@description('Azure AI Foundry embeddings deployment capacity.')
param foundryEmbeddingsDeploymentCapacity int = 1

@description('Responsible AI policy name applied to model deployments.')
param foundryRaiPolicyName string = 'Microsoft.Default'

var resourceSuffix = take(uniqueString(subscription().id, environmentName, location), 6)
var normalizedPrefix = toLower(replace(namePrefix, '-', ''))
var resourceGroupName = 'rg-${environmentName}'
var commonTags = {
  'azd-env-name': environmentName
  app: 'maf-order-resolution-agent'
  workload: 'order-resolution'
}

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: commonTags
}

module monitoring './modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    name: '${namePrefix}-mon-${resourceSuffix}'
    location: location
    tags: commonTags
  }
}

module containerRegistry './modules/container-registry.bicep' = {
  name: 'containerRegistry'
  scope: rg
  params: {
    name: take('${normalizedPrefix}acr${resourceSuffix}', 50)
    location: location
    tags: commonTags
  }
}

module keyVault './modules/key-vault.bicep' = {
  name: 'keyVault'
  scope: rg
  params: {
    name: take('kv${normalizedPrefix}${resourceSuffix}', 24)
    location: location
    tags: commonTags
  }
}


module foundry './modules/foundry.bicep' = {
  name: 'foundry'
  scope: rg
  params: {
    accountName: take('${normalizedPrefix}ai${resourceSuffix}', 64)
    projectName: foundryProjectName
    location: location
    tags: commonTags
    customSubDomainName: take('${normalizedPrefix}ai${resourceSuffix}', 64)
    chatDeploymentName: foundryChatDeploymentName
    chatModelFormat: foundryChatModelFormat
    chatModelName: foundryChatModelName
    chatModelVersion: foundryChatModelVersion
    chatDeploymentSkuName: foundryChatDeploymentSkuName
    chatDeploymentCapacity: foundryChatDeploymentCapacity
    embeddingsDeploymentName: foundryEmbeddingsDeploymentName
    embeddingsModelFormat: foundryEmbeddingsModelFormat
    embeddingsModelName: foundryEmbeddingsModelName
    embeddingsModelVersion: foundryEmbeddingsModelVersion
    embeddingsDeploymentSkuName: foundryEmbeddingsDeploymentSkuName
    embeddingsDeploymentCapacity: foundryEmbeddingsDeploymentCapacity
    raiPolicyName: foundryRaiPolicyName
  }
}

module postgres './modules/postgres-flexible-server.bicep' = {
  name: 'postgres'
  scope: rg
  params: {
    name: take('${namePrefix}-pg-${resourceSuffix}', 63)
    location: location
    tags: commonTags
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    databaseName: postgresDatabaseName
  }
}

var databaseUrl = 'postgresql://${postgresAdministratorLogin}:${postgresAdministratorPassword}@${postgres.outputs.fullyQualifiedDomainName}:5432/${postgresDatabaseName}?sslmode=require'

module containerAppsEnvironment './modules/container-app-environment.bicep' = {
  name: 'containerAppsEnvironment'
  scope: rg
  params: {
    name: '${namePrefix}-cae-${resourceSuffix}'
    location: location
    tags: commonTags
    logAnalyticsCustomerId: monitoring.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: monitoring.outputs.logAnalyticsSharedKey
  }
}

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var backendSecrets = concat(
  [
    {
      name: 'database-url'
      value: databaseUrl
    }
  ],
  empty(mcpApiKey) ? [] : [
    {
      name: 'mcp-api-key'
      value: mcpApiKey
    }
  ],
  empty(mcpBearerToken) ? [] : [
    {
      name: 'mcp-bearer-token'
      value: mcpBearerToken
    }
  ]
)
var backendEnv = concat(
  [
    {
      name: 'APP_ENV'
      value: 'azure-apphosted'
    }
    {
      name: 'WORKFLOW_MODE'
      value: 'maf_sdk'
    }
    {
      name: 'STORE_PROVIDER'
      value: 'postgres'
    }
    {
      name: 'RAG_PROVIDER'
      value: 'pgvector'
    }
    {
      name: 'MEMORY_PROVIDER'
      value: 'postgres'
    }
    {
      name: 'DATABASE_URL'
      secretRef: 'database-url'
    }
    {
      name: 'OTEL_SERVICE_NAME'
      value: 'maf-order-resolution-backend'
    }
    {
      name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
      value: monitoring.outputs.applicationInsightsConnectionString
    }
    {
      name: 'FOUNDRY_PROJECTS_ENDPOINT'
      value: foundry.outputs.projectEndpoint
    }
    {
      name: 'FOUNDRY_MODEL_DEPLOYMENT_NAME'
      value: foundry.outputs.chatDeploymentName
    }
    {
      name: 'FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME'
      value: foundry.outputs.embeddingsDeploymentName
    }
  ],
  empty(mcpServerUrl) ? [] : [
    {
      name: 'MCP_SERVER_URL'
      value: mcpServerUrl
    }
  ],
  empty(mcpApiKey) ? [] : [
    {
      name: 'MCP_API_KEY'
      secretRef: 'mcp-api-key'
    }
  ],
  empty(mcpBearerToken) ? [] : [
    {
      name: 'MCP_BEARER_TOKEN'
      secretRef: 'mcp-bearer-token'
    }
  ]
)

module backend './modules/container-app.bicep' = {
  name: 'backendContainerApp'
  scope: rg
  params: {
    name: '${namePrefix}-backend-${resourceSuffix}'
    location: location
    tags: commonTags
    serviceName: 'backend'
    managedEnvironmentId: containerAppsEnvironment.outputs.id
    image: placeholderImage
    targetPort: 8000
    cpu: '0.5'
    memory: '1Gi'
    minReplicas: 1
    maxReplicas: 2
    env: backendEnv
    registries: [
      {
        server: containerRegistry.outputs.loginServer
        identity: 'system'
      }
    ]
    secrets: {
      items: backendSecrets
    }
  }
}

var frontendEnv = [
  {
    name: 'API_BASE'
    value: backend.outputs.url
  }
]

module frontend './modules/container-app.bicep' = {
  name: 'frontendContainerApp'
  scope: rg
  params: {
    name: '${namePrefix}-frontend-${resourceSuffix}'
    location: location
    tags: commonTags
    serviceName: 'frontend'
    managedEnvironmentId: containerAppsEnvironment.outputs.id
    image: placeholderImage
    targetPort: 5173
    cpu: '0.25'
    memory: '0.5Gi'
    minReplicas: 1
    maxReplicas: 2
    env: frontendEnv
    registries: [
      {
        server: containerRegistry.outputs.loginServer
        identity: 'system'
      }
    ]
    secrets: {
      items: []
    }
  }
}

module backendAcrPull './modules/acr-pull-role.bicep' = {
  name: 'backendAcrPull'
  scope: rg
  params: {
    acrName: containerRegistry.outputs.name
    principalId: backend.outputs.systemAssignedMIPrincipalId
  }
}

module frontendAcrPull './modules/acr-pull-role.bicep' = {
  name: 'frontendAcrPull'
  scope: rg
  params: {
    acrName: containerRegistry.outputs.name
    principalId: frontend.outputs.systemAssignedMIPrincipalId
  }
}


module backendFoundryOpenAiUser './modules/foundry-openai-user-role.bicep' = {
  name: 'backendFoundryOpenAiUser'
  scope: rg
  params: {
    foundryAccountName: foundry.outputs.accountName
    principalId: backend.outputs.systemAssignedMIPrincipalId
  }
}

module backendFoundryProjectUser './modules/foundry-project-user-role.bicep' = {
  name: 'backendFoundryProjectUser'
  scope: rg
  params: {
    foundryAccountName: foundry.outputs.accountName
    foundryProjectName: foundry.outputs.projectName
    principalId: backend.outputs.systemAssignedMIPrincipalId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_KEY_VAULT_NAME string = keyVault.outputs.name
output FOUNDRY_ACCOUNT_NAME string = foundry.outputs.accountName
output FOUNDRY_ACCOUNT_ENDPOINT string = foundry.outputs.accountEndpoint
output FOUNDRY_PROJECT_NAME string = foundry.outputs.projectName
output FOUNDRY_PROJECTS_ENDPOINT string = foundry.outputs.projectEndpoint
output FOUNDRY_MODEL_DEPLOYMENT_NAME string = foundry.outputs.chatDeploymentName
output FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME string = foundry.outputs.embeddingsDeploymentName
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = monitoring.outputs.logAnalyticsWorkspaceId
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString
output API_URL string = backend.outputs.url
output WEB_URL string = frontend.outputs.url
