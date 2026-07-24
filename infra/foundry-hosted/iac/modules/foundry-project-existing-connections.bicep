@description('Name of the existing AI Foundry account')
param accountName string

@description('Name of the existing AI Foundry project to update in place')
param projectName string

@description('Location for metadata fields')
param location string

@description('Name of the existing AI Search resource')
param aiSearchName string

@description('Subscription ID containing AI Search')
param aiSearchSubscriptionId string = subscription().subscriptionId

@description('Resource group containing AI Search')
param aiSearchResourceGroupName string = resourceGroup().name

@description('Name of the existing Storage account')
param storageAccountName string

@description('Subscription ID containing Storage account')
param storageSubscriptionId string = subscription().subscriptionId

@description('Resource group containing Storage account')
param storageResourceGroupName string = resourceGroup().name

@description('Name of the existing Cosmos DB account')
param cosmosAccountName string

@description('Subscription ID containing Cosmos DB account')
param cosmosSubscriptionId string = subscription().subscriptionId

@description('Resource group containing Cosmos DB account')
param cosmosResourceGroupName string = resourceGroup().name

@description('Connection name for Cosmos DB on the project')
param cosmosConnectionName string

@description('Connection name for Storage on the project')
param storageConnectionName string

@description('Connection name for AI Search on the project')
param aiSearchConnectionName string

@description('Resource ID of the existing Application Insights resource')
param applicationInsightsResourceId string

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: aiSearchName
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
}

resource cosmosDBAccount 'Microsoft.DocumentDB/databaseAccounts@2024-12-01-preview' existing = {
  name: cosmosAccountName
  scope: resourceGroup(cosmosSubscriptionId, cosmosResourceGroupName)
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
}

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
  scope: resourceGroup()
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName

  resource projectConnectionCosmos 'connections@2025-04-01-preview' = {
    name: cosmosConnectionName
    properties: {
      category: 'CosmosDB'
      target: cosmosDBAccount.properties.documentEndpoint
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: cosmosDBAccount.id
        location: cosmosDBAccount.location
      }
    }
  }

  resource projectConnectionStorage 'connections@2025-04-01-preview' = {
    name: storageConnectionName
    properties: {
      category: 'AzureStorageAccount'
      target: storageAccount.properties.primaryEndpoints.blob
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: storageAccount.id
        location: location
      }
    }
  }

  resource projectConnectionSearch 'connections@2025-04-01-preview' = {
    name: aiSearchConnectionName
    properties: {
      category: 'CognitiveSearch'
      target: 'https://${aiSearchName}.search.windows.net'
      authType: 'AAD'
      metadata: {
        ApiType: 'Azure'
        ResourceId: searchService.id
        location: searchService.location
      }
    }
  }

  resource projectConnectionApplicationInsights 'connections@2025-04-01-preview' = {
    name: 'ApplicationInsights'
    properties: {
      #disable-next-line BCP036
      category: 'AppInsights'
      target: applicationInsightsResourceId
      #disable-next-line BCP036
      authType: 'ProjectManagedIdentity'
      isSharedToAll: false
      metadata: {
        ApiType: 'Azure'
        ResourceId: applicationInsightsResourceId
      }
    }
  }
}

output projectId string = project.id
output projectPrincipalId string = project.identity.principalId
#disable-next-line BCP053
output projectWorkspaceId string = project.properties.internalId
output cosmosConnection string = cosmosConnectionName
output storageConnection string = storageConnectionName
output aiSearchConnection string = aiSearchConnectionName
output applicationInsightsConnection string = project::projectConnectionApplicationInsights.name
output applicationInsightsConnectionId string = project::projectConnectionApplicationInsights.id
