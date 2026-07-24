targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Public Foundry project name')
param foundryProjectName string = 'order-resolution-public-managed-dev2'

@description('Hosted agent name used to compose the Responses endpoint')
param hostedAgentName string = 'order-resolution-hosted'

@description('Public Foundry account name')
param foundryAccountName string = 'maffndaibfscpfhjr7sp4'

@description('Public Azure Container Registry name')
param containerRegistryName string = 'maffndacrbfscpfhjr7sp4'

@description('Public Container Apps environment name')
param containerAppsEnvironmentName string = 'ora-public-dev2-aca'

@description('Public internal backend Container App name')
param backendContainerAppName string = 'ora-public-dev2-backend'

@description('Public external frontend Container App name')
param frontendContainerAppName string = 'ora-public-dev2-frontend'

@description('Backend bootstrap or azd-published container image')
param backendImageName string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Frontend bootstrap or azd-published container image')
param frontendImageName string = 'mcr.microsoft.com/k8se/quickstart:latest'

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

@secure()
@description('TLS-enabled PostgreSQL connection string supplied to the backend Container App')
param runtimeDatabaseUrl string = ''

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

resource acrPullRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  scope: resourceGroup()
}

resource acrPushRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '8311e382-0749-4cb8-b61a-304f252e45ec'
  scope: resourceGroup()
}

resource azureAIUserRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
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

resource foundryAccountAcrPushRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, foundryAccount.id, acrPushRole.id)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPushRole.id
    principalId: foundryAccount.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource foundryProjectAcrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, foundryProject.id, acrPullRole.id)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRole.id
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

resource projectApplicationInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: foundryProject
  name: 'ApplicationInsights'
  properties: {
    category: 'AppInsights'
    target: applicationInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
    }
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

resource runtimeStorageConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: foundryAccount
  name: 'runtime-storage'
  properties: {
    category: 'AzureStorageAccount'
    target: evaluationStorageAccount.properties.primaryEndpoints.blob
    authType: 'AAD'
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ResourceId: evaluationStorageAccount.id
      location: evaluationStorageAccount.location
      purpose: 'foundry-runtime-artifacts'
    }
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource containerAppsRegistryPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${containerAppsEnvironmentName}-acr-pull'
  location: location
}

resource containerAppsRegistryPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, containerAppsRegistryPullIdentity.id, acrPullRole.id)
  scope: containerRegistry
  properties: {
    roleDefinitionId: acrPullRole.id
    principalId: containerAppsRegistryPullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource backendContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendContainerAppName
  location: location
  tags: {
    'azd-service-name': 'backend'
  }
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${containerAppsRegistryPullIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: containerAppsRegistryPullIdentity.id
        }
      ]
      secrets: [
        {
          name: 'database-url'
          value: runtimeDatabaseUrl
        }
        {
          name: 'application-insights-connection-string'
          value: applicationInsights.properties.ConnectionString
        }
      ]
      ingress: {
        external: false
        allowInsecure: false
        targetPort: 8000
        transport: 'http'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImageName
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'APP_ENV'
              value: 'aca-public'
            }
            {
              name: 'STORE_PROVIDER'
              value: 'postgres'
            }
            {
              name: 'RUNTIME_TARGET'
              value: 'responses_wrapper'
            }
            {
              name: 'FOUNDRY_RESPONSES_ENDPOINT'
              value: foundryHostedResponsesUrl
            }
            {
              name: 'AZURE_TOKEN_CREDENTIALS'
              value: 'prod'
            }
            {
              name: 'FOUNDRY_PROJECTS_ENDPOINT'
              value: foundryProjectEndpoint
            }
            {
              name: 'FOUNDRY_MODEL_DEPLOYMENT_NAME'
              value: foundryChatDeploymentName
            }
            {
              name: 'FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME'
              value: foundryEmbeddingsDeploymentName
            }
            {
              name: 'ENABLE_TELEMETRY'
              value: 'true'
            }
            {
              name: 'ENABLE_INSTRUMENTATION'
              value: 'true'
            }
            {
              name: 'OTEL_SERVICE_NAME'
              value: 'maf-order-resolution-aca-backend'
            }
            {
              name: 'OTEL_SERVICE_NAMESPACE'
              value: 'maf-order-resolution'
            }
            {
              name: 'OTEL_RECORD_CONTENT'
              value: 'false'
            }
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'application-insights-connection-string'
            }
            {
              name: 'APPINSIGHTS_CONNECTION_STRING'
              secretRef: 'application-insights-connection-string'
            }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        // The public bootstrap image does not implement the application health contract.
        // HTTP ingress activates the real revision after `azd deploy` replaces it.
        minReplicas: 0
        maxReplicas: 2
      }
    }
  }
  dependsOn: [
    containerAppsRegistryPullRoleAssignment
  ]
}

resource frontendContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendContainerAppName
  location: location
  tags: {
    'azd-service-name': 'frontend'
  }
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${containerAppsRegistryPullIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: containerAppsRegistryPullIdentity.id
        }
      ]
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 5173
        transport: 'http'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImageName
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'API_BASE'
              value: ''
            }
            {
              name: 'NGINX_API_UPSTREAM'
              value: 'https://${backendContainerApp.properties.configuration.ingress.fqdn}'
            }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health'
                port: 5173
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 24
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 5173
              }
              initialDelaySeconds: 15
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 5173
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        // The public bootstrap image does not implement the application health contract.
        // HTTP ingress activates the real revision after `azd deploy` replaces it.
        minReplicas: 0
        maxReplicas: 2
      }
    }
  }
  dependsOn: [
    containerAppsRegistryPullRoleAssignment
  ]
}

resource backendContainerAppAzureAIUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryProject.id, backendContainerApp.id, azureAIUserRole.id)
  scope: foundryProject
  properties: {
    roleDefinitionId: azureAIUserRole.id
    principalId: backendContainerApp.identity.principalId
    principalType: 'ServicePrincipal'
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
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.properties.loginServer
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString
output APPLICATIONINSIGHTS_CONNECTION_STRING string = applicationInsights.properties.ConnectionString
output APPINSIGHTS_CONNECTION_STRING string = applicationInsights.properties.ConnectionString
output APPINSIGHTS_RESOURCE_ID string = applicationInsights.id
output FOUNDRY_EVALUATION_STORAGE_ACCOUNT_NAME string = evaluationStorageAccount.name
output postgresFullyQualifiedDomainName string = createPostgresServer ? postgresServer!.properties.fullyQualifiedDomainName : ''
output postgresDatabaseName string = postgresDatabaseName
output projectPrincipalId string = foundryProject.identity.principalId
output AZURE_CONTAINER_ENVIRONMENT_NAME string = containerAppsEnvironment.name
output SERVICE_BACKEND_NAME string = backendContainerApp.name
output SERVICE_BACKEND_IMAGE_NAME string = backendImageName
output SERVICE_BACKEND_URI string = 'https://${backendContainerApp.properties.configuration.ingress.fqdn}'
output SERVICE_BACKEND_ENDPOINTS array = [
  'https://${backendContainerApp.properties.configuration.ingress.fqdn}'
]
output SERVICE_BACKEND_IDENTITY_PRINCIPAL_ID string = backendContainerApp.identity.principalId
output SERVICE_FRONTEND_NAME string = frontendContainerApp.name
output SERVICE_FRONTEND_IMAGE_NAME string = frontendImageName
output SERVICE_FRONTEND_URI string = 'https://${frontendContainerApp.properties.configuration.ingress.fqdn}'
output SERVICE_FRONTEND_ENDPOINTS array = [
  'https://${frontendContainerApp.properties.configuration.ingress.fqdn}'
]
output SERVICE_FRONTEND_IDENTITY_PRINCIPAL_ID string = frontendContainerApp.identity.principalId
output API_BASE_URL string = 'https://${backendContainerApp.properties.configuration.ingress.fqdn}'
output WEB_URL string = 'https://${frontendContainerApp.properties.configuration.ingress.fqdn}'
output requiredBackendSettings array = [
  'FOUNDRY_PROJECTS_ENDPOINT=${foundryProjectEndpoint}'
  'APPLICATIONINSIGHTS_CONNECTION_STRING=${applicationInsights.properties.ConnectionString}'
]
output nextStep string = 'Run the local public release script, then verify hosted Responses conversations and Application Insights telemetry.'
