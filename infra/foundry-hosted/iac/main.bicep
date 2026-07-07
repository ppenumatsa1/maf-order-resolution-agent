targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Prefix used for deterministic naming and defaults')
@minLength(3)
param namePrefix string = 'maffd'

@description('Foundry hosted invocations endpoint URL wired into backend runtime')
param foundryHostedInvocationsUrl string

@description('Name of the callback token setting used by backend event ingress')
param foundryEventCallbackTokenSettingName string = 'FOUNDRY_EVENT_CALLBACK_TOKEN'

@description('Name of the existing AI Foundry account')
param foundryAccountName string

@description('Name of the existing AI Foundry project')
param foundryProjectName string

@description('Name of the existing AI Search service')
param aiSearchName string

@description('Name of the existing Storage account')
param storageAccountName string

@description('Name of the existing Cosmos DB account')
param cosmosAccountName string

@description('Optional override for Cosmos connection name inside the project')
param cosmosConnectionName string = ''

@description('Optional override for Storage connection name inside the project')
param storageConnectionName string = ''

@description('Optional override for AI Search connection name inside the project')
param aiSearchConnectionName string = ''

@description('Name of the account-level capability host')
param accountCapabilityHostName string = '${foundryAccountName}-aml-aiagentservice'

@description('Name of the project-level capability host')
param projectCapabilityHostName string = 'caphostproj'

@description('Resource ID of the existing virtual network used for private DNS links')
param virtualNetworkResourceId string

@description('Resource ID of the delegated agent subnet for account capability host customerSubnet')
param agentSubnetResourceId string

@description('Resource ID of the private-endpoint subnet')
param privateEndpointSubnetResourceId string

@description('Private DNS zones used for private endpoint resolution')
param privateDnsZoneNames array

@description('Create private DNS VNet links. Set false when the VNet is already linked to these zones.')
param createPrivateDnsVnetLinks bool = false

@description('Create private endpoints for dependent services. Set false when BYO private endpoints already exist.')
param createPrivateEndpoints bool = false

@description('Assign pre-capability-host RBAC (Storage Blob Data Contributor, Cosmos DB Operator, Search roles).')
param assignPreCaphostRbac bool = true

@description('Assign post-capability-host RBAC (Storage Blob Data Owner conditional and Cosmos SQL role).')
param assignPostCaphostRbac bool = true

@description('Create or update account-level capability host configuration.')
param createAccountCapabilityHost bool = true

@description('Create or update project-level capability host configuration.')
param createProjectCapabilityHost bool = true

@description('Subscription ID containing AI Search (defaults to current)')
param aiSearchSubscriptionId string = subscription().subscriptionId

@description('Resource group containing AI Search (defaults to current)')
param aiSearchResourceGroupName string = resourceGroup().name

@description('Subscription ID containing Storage account (defaults to current)')
param storageSubscriptionId string = subscription().subscriptionId

@description('Resource group containing Storage account (defaults to current)')
param storageResourceGroupName string = resourceGroup().name

@description('Subscription ID containing Cosmos DB account (defaults to current)')
param cosmosSubscriptionId string = subscription().subscriptionId

@description('Resource group containing Cosmos DB account (defaults to current)')
param cosmosResourceGroupName string = resourceGroup().name

var suffix = toLower(uniqueString(resourceGroup().id))
var effectiveCosmosConnectionName = empty(cosmosConnectionName) ? '${cosmosAccountName}-${foundryProjectName}' : cosmosConnectionName
var effectiveStorageConnectionName = empty(storageConnectionName) ? '${storageAccountName}-${foundryProjectName}' : storageConnectionName
var effectiveAiSearchConnectionName = empty(aiSearchConnectionName) ? '${aiSearchName}-${foundryProjectName}' : aiSearchConnectionName

#disable-next-line no-hardcoded-env-urls
var blobZoneName = 'privatelink.blob.core.windows.net'
#disable-next-line no-hardcoded-env-urls
var searchZoneName = 'privatelink.search.windows.net'
#disable-next-line no-hardcoded-env-urls
var cosmosZoneName = 'privatelink.documents.azure.com'
#disable-next-line no-hardcoded-env-urls
var foundryServicesZoneName = 'privatelink.services.ai.azure.com'
#disable-next-line no-hardcoded-env-urls
var foundryCognitiveZoneName = 'privatelink.cognitiveservices.azure.com'
#disable-next-line no-hardcoded-env-urls
var foundryOpenAiZoneName = 'privatelink.openai.azure.com'

var blobZoneIndex = indexOf(privateDnsZoneNames, blobZoneName)
var searchZoneIndex = indexOf(privateDnsZoneNames, searchZoneName)
var cosmosZoneIndex = indexOf(privateDnsZoneNames, cosmosZoneName)
var foundryServicesZoneIndex = indexOf(privateDnsZoneNames, foundryServicesZoneName)
var foundryCognitiveZoneIndex = indexOf(privateDnsZoneNames, foundryCognitiveZoneName)
var foundryOpenAiZoneIndex = indexOf(privateDnsZoneNames, foundryOpenAiZoneName)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
}

resource aiSearch 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: aiSearchName
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
}

resource cosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-12-01-preview' existing = {
  name: cosmosAccountName
  scope: resourceGroup(cosmosSubscriptionId, cosmosResourceGroupName)
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: foundryAccountName
}

module privateDns './modules/private-dns.bicep' = {
  name: 'private-network-dns'
  params: {
    enabled: true
    virtualNetworkId: virtualNetworkResourceId
    zoneNames: privateDnsZoneNames
    createVnetLinks: createPrivateDnsVnetLinks
  }
}

module storagePrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-storage'
  params: {
    enabled: createPrivateEndpoints
    location: location
    name: '${namePrefix}-storage-pe-${suffix}'
    subnetId: privateEndpointSubnetResourceId
    targetResourceId: storage.id
    groupIds: [
      'blob'
    ]
    privateDnsZoneIds: [
      privateDns.outputs.zoneIds[blobZoneIndex]
    ]
  }
}

module searchPrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-search'
  params: {
    enabled: createPrivateEndpoints
    location: location
    name: '${namePrefix}-search-pe-${suffix}'
    subnetId: privateEndpointSubnetResourceId
    targetResourceId: aiSearch.id
    groupIds: [
      'searchService'
    ]
    privateDnsZoneIds: [
      privateDns.outputs.zoneIds[searchZoneIndex]
    ]
  }
}

module cosmosPrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-cosmos'
  params: {
    enabled: createPrivateEndpoints
    location: location
    name: '${namePrefix}-cosmos-pe-${suffix}'
    subnetId: privateEndpointSubnetResourceId
    targetResourceId: cosmosDB.id
    groupIds: [
      'Sql'
    ]
    privateDnsZoneIds: [
      privateDns.outputs.zoneIds[cosmosZoneIndex]
    ]
  }
}

module foundryPrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-foundry-account'
  params: {
    enabled: createPrivateEndpoints
    location: location
    name: '${namePrefix}-foundry-pe-${suffix}'
    subnetId: privateEndpointSubnetResourceId
    targetResourceId: foundryAccount.id
    groupIds: [
      'account'
    ]
    privateDnsZoneIds: [
      privateDns.outputs.zoneIds[foundryServicesZoneIndex]
      privateDns.outputs.zoneIds[foundryCognitiveZoneIndex]
      privateDns.outputs.zoneIds[foundryOpenAiZoneIndex]
    ]
  }
}

module projectConnections './modules/foundry-project-existing-connections.bicep' = {
  name: 'project-connections-${suffix}'
  params: {
    accountName: foundryAccountName
    projectName: foundryProjectName
    location: location
    aiSearchName: aiSearchName
    aiSearchSubscriptionId: aiSearchSubscriptionId
    aiSearchResourceGroupName: aiSearchResourceGroupName
    storageAccountName: storageAccountName
    storageSubscriptionId: storageSubscriptionId
    storageResourceGroupName: storageResourceGroupName
    cosmosAccountName: cosmosAccountName
    cosmosSubscriptionId: cosmosSubscriptionId
    cosmosResourceGroupName: cosmosResourceGroupName
    cosmosConnectionName: effectiveCosmosConnectionName
    storageConnectionName: effectiveStorageConnectionName
    aiSearchConnectionName: effectiveAiSearchConnectionName
  }
}

module formatProjectWorkspaceId './modules/format-project-workspace-id.bicep' = {
  name: 'format-workspace-id-${suffix}'
  params: {
    projectWorkspaceId: projectConnections.outputs.projectWorkspaceId
  }
}

module storageAccountRoleAssignment './modules/azure-storage-account-role-assignment.bicep' = if (assignPreCaphostRbac) {
  name: 'storage-account-rbac-${suffix}'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    storageAccountName: storageAccountName
    projectPrincipalId: projectConnections.outputs.projectPrincipalId
  }
  dependsOn: [
    storagePrivateEndpoint
  ]
}

module cosmosAccountRoleAssignments './modules/cosmosdb-account-role-assignment.bicep' = if (assignPreCaphostRbac) {
  name: 'cosmos-account-rbac-${suffix}'
  scope: resourceGroup(cosmosSubscriptionId, cosmosResourceGroupName)
  params: {
    cosmosDBName: cosmosAccountName
    projectPrincipalId: projectConnections.outputs.projectPrincipalId
  }
  dependsOn: [
    cosmosPrivateEndpoint
  ]
}

module aiSearchRoleAssignments './modules/ai-search-role-assignments.bicep' = if (assignPreCaphostRbac) {
  name: 'search-account-rbac-${suffix}'
  scope: resourceGroup(aiSearchSubscriptionId, aiSearchResourceGroupName)
  params: {
    aiSearchName: aiSearchName
    projectPrincipalId: projectConnections.outputs.projectPrincipalId
  }
  dependsOn: [
    searchPrivateEndpoint
  ]
}

module addAccountCapabilityHost './modules/add-account-capability-host.bicep' = if (createAccountCapabilityHost) {
  name: 'account-capability-host-${suffix}'
  params: {
    accountName: foundryAccountName
    accountCapabilityHostName: accountCapabilityHostName
    agentSubnetResourceId: agentSubnetResourceId
  }
  dependsOn: [
    foundryPrivateEndpoint
  ]
}

module addProjectCapabilityHost './modules/add-project-capability-host.bicep' = if (createProjectCapabilityHost) {
  name: 'project-capability-host-${suffix}'
  params: {
    accountName: foundryAccountName
    projectName: foundryProjectName
    projectCapabilityHostName: projectCapabilityHostName
    cosmosConnectionName: projectConnections.outputs.cosmosConnection
    storageConnectionName: projectConnections.outputs.storageConnection
    aiSearchConnectionName: projectConnections.outputs.aiSearchConnection
  }
  dependsOn: [
    addAccountCapabilityHost
    storageAccountRoleAssignment
    cosmosAccountRoleAssignments
    aiSearchRoleAssignments
  ]
}

module storageContainersRoleAssignment './modules/blob-storage-container-role-assignments.bicep' = if (assignPostCaphostRbac && createProjectCapabilityHost) {
  name: 'storage-container-rbac-${suffix}'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    aiProjectPrincipalId: projectConnections.outputs.projectPrincipalId
    storageName: storageAccountName
    workspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
  }
  dependsOn: [
    addProjectCapabilityHost
  ]
}

module cosmosContainerRoleAssignments './modules/cosmos-container-role-assignments.bicep' = if (assignPostCaphostRbac && createProjectCapabilityHost) {
  name: 'cosmos-container-rbac-${suffix}'
  scope: resourceGroup(cosmosSubscriptionId, cosmosResourceGroupName)
  params: {
    cosmosAccountName: cosmosAccountName
    projectWorkspaceId: formatProjectWorkspaceId.outputs.projectWorkspaceIdGuid
    projectPrincipalId: projectConnections.outputs.projectPrincipalId
  }
  dependsOn: [
    addProjectCapabilityHost
    storageContainersRoleAssignment
  ]
}

output foundryHostedInvocationsUrl string = foundryHostedInvocationsUrl
output foundryEventCallbackTokenSettingName string = foundryEventCallbackTokenSettingName
output accountCapabilityHost string = createAccountCapabilityHost ? addAccountCapabilityHost.outputs.accountCapabilityHostName : ''
output projectCapabilityHost string = createProjectCapabilityHost ? addProjectCapabilityHost.outputs.projectCapabilityHostName : ''
output projectPrincipalId string = projectConnections.outputs.projectPrincipalId
output projectWorkspaceId string = projectConnections.outputs.projectWorkspaceId
output connectionNames object = {
  cosmos: projectConnections.outputs.cosmosConnection
  storage: projectConnections.outputs.storageConnection
  aiSearch: projectConnections.outputs.aiSearchConnection
}
output privateEndpointIds object = {
  storage: storagePrivateEndpoint.outputs.id
  aiSearch: searchPrivateEndpoint.outputs.id
  cosmos: cosmosPrivateEndpoint.outputs.id
  foundry: foundryPrivateEndpoint.outputs.id
}
output requiredBackendSettings array = [
  'WORKFLOW_MODE=foundry_hosted'
  'FOUNDRY_HOSTED_INVOCATIONS_URL=<hosted-agent-invocations-endpoint>'
  '${foundryEventCallbackTokenSettingName}=<shared-callback-token>'
]
output nextStep string = 'Approve all private endpoints, validate private DNS resolution, and run hosted-agent invoke validation.'
