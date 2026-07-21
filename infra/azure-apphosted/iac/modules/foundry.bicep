targetScope = 'resourceGroup'

param accountName string
param projectName string
param location string = resourceGroup().location
param tags object = {}
param customSubDomainName string
param publicNetworkAccess string = 'Enabled'
param disableLocalAuth bool = true
param chatDeploymentName string
param chatModelFormat string = 'OpenAI'
param chatModelName string = 'gpt-4.1-mini'
param chatModelVersion string = '2025-04-14'
param chatDeploymentSkuName string = 'GlobalStandard'
param chatDeploymentCapacity int = 1
param embeddingsDeploymentName string
param embeddingsModelFormat string = 'OpenAI'
param embeddingsModelName string = 'text-embedding-3-small'
param embeddingsModelVersion string = '1'
param embeddingsDeploymentSkuName string = 'GlobalStandard'
param embeddingsDeploymentCapacity int = 1
param evaluatorDeploymentName string = 'gpt-4.1-mini-evaluator'
param evaluatorModelFormat string = 'OpenAI'
param evaluatorModelName string = 'gpt-4.1-mini'
param evaluatorModelVersion string = '2025-04-14'
param evaluatorDeploymentSkuName string = 'GlobalStandard'
param evaluatorDeploymentCapacity int = 1
param raiPolicyName string = 'Microsoft.Default'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: customSubDomainName
    disableLocalAuth: disableLocalAuth
    publicNetworkAccess: publicNetworkAccess
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'MAF order resolution app-hosted project'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: chatDeploymentName
  tags: tags
  sku: {
    name: chatDeploymentSkuName
    capacity: chatDeploymentCapacity
  }
  properties: {
    model: {
      format: chatModelFormat
      name: chatModelName
      version: chatModelVersion
    }
    raiPolicyName: raiPolicyName
  }
}

resource embeddingsDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: embeddingsDeploymentName
  tags: tags
  sku: {
    name: embeddingsDeploymentSkuName
    capacity: embeddingsDeploymentCapacity
  }

  properties: {
    model: {
      format: embeddingsModelFormat
      name: embeddingsModelName
      version: embeddingsModelVersion
    }
    raiPolicyName: raiPolicyName
  }
  dependsOn: [
    chatDeployment
  ]
}

resource projectFoundryUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, project.id, 'project-foundry-user')
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '53ca6127-db72-4b80-b1b0-d745d6d5456d'
    )
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource evaluatorDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: evaluatorDeploymentName
  tags: tags
  sku: {
    name: evaluatorDeploymentSkuName
    capacity: evaluatorDeploymentCapacity
  }
  properties: {
    model: {
      format: evaluatorModelFormat
      name: evaluatorModelName
      version: evaluatorModelVersion
    }
    raiPolicyName: raiPolicyName
  }
  dependsOn: [
    embeddingsDeployment
  ]
}

var accountEndpoint = account.properties.endpoint
var projectEndpoint = 'https://${customSubDomainName}.services.ai.azure.com/api/projects/${project.name}'

output accountId string = account.id
output accountName string = account.name
output accountEndpoint string = accountEndpoint
output projectId string = project.id
output projectName string = project.name
output projectEndpoint string = projectEndpoint
output chatDeploymentName string = chatDeployment.name
output embeddingsDeploymentName string = embeddingsDeployment.name
output evaluatorDeploymentName string = evaluatorDeployment.name
