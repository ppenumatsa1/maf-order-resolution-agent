targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Prefix used for deterministic naming and defaults')
@minLength(3)
param namePrefix string = 'maffnd'

@description('Foundry project name')
param foundryProjectName string = 'order-resolution'

@description('Hosted agent name used to compose default invocations URL')
param hostedAgentName string = 'order-resolution-hosted'

@description('Optional override for Foundry account name')
param foundryAccountName string = ''

@description('Optional override for Storage account name')
param storageAccountName string = ''

@description('Optional override for Cosmos DB account name')
param cosmosAccountName string = ''

@description('Optional Cosmos DB region override when primary region has capacity issues')
param cosmosLocation string = ''

@description('Optional override for AI Search service name')
param aiSearchName string = ''

@description('AI Search region; defaults to East US to avoid recurring East US 2 capacity exhaustion.')
param aiSearchLocation string = 'eastus'

@description('Optional override for ACR name')
param containerRegistryName string = ''

@description('Name of the callback token setting used by backend event ingress')
param foundryEventCallbackTokenSettingName string = 'FOUNDRY_EVENT_CALLBACK_TOKEN'

@description('Name of the account-level capability host')
param accountCapabilityHostName string = 'caphostacct'

@description('Name of the project-level capability host')
param projectCapabilityHostName string = 'caphostproj'

@description('Virtual network name')
param virtualNetworkName string = ''

@description('VNet address prefix')
param vnetAddressPrefix string = '10.90.0.0/16'

@description('Agent subnet name')
param agentSubnetName string = 'snet-agent-host'

@description('Agent subnet prefix')
param agentSubnetPrefix string = '10.90.1.0/24'

@description('Private endpoint subnet name')
param privateEndpointSubnetName string = 'snet-private-endpoints'

@description('Private endpoint subnet prefix')
param privateEndpointSubnetPrefix string = '10.90.2.0/24'

@description('Create NAT gateway for controlled outbound from the agent subnet.')
param createNatGateway bool = true

@description('Optional override for NAT gateway name')
param natGatewayName string = ''

@description('Optional override for NAT public IP name')
param natPublicIpName string = ''

@description('Enable private runner access resources (runner subnet, Bastion, and VM).')
param createPrivateRunnerAccess bool = false

@description('Assign subscription-scope RBAC to runner UAMI so azd can validate and run deployments non-interactively.')
param assignRunnerSubscriptionRbac bool = true

@description('Also assign User Access Administrator for runner UAMI when templates create role assignments.')
param assignRunnerUserAccessAdministrator bool = false

@description('Runner subnet name')
param runnerSubnetName string = 'snet-runner'

@description('Runner subnet prefix')
param runnerSubnetPrefix string = '10.90.3.0/24'

@description('Azure Bastion subnet name. Must be AzureBastionSubnet.')
param bastionSubnetName string = 'AzureBastionSubnet'

@description('Azure Bastion subnet prefix (minimum /26).')
param bastionSubnetPrefix string = '10.90.4.0/26'

@description('Create Azure Bastion host for browser/SSH tunneling access.')
param createBastionHost bool = true

@description('Create a private VM runner in the runner subnet.')
param createRunnerVm bool = true

@description('Runner VM name')
param runnerVmName string = 'vm-maffnd-runner'

@description('Runner VM size')
param runnerVmSize string = 'Standard_D4s_v5'

@description('Runner VM admin username')
param runnerVmAdminUsername string = 'azureuser'

@description('SSH public key for runner VM admin user. Required when createRunnerVm is true.')
param runnerVmSshPublicKey string = ''

@description('Runner subnet NSG name')
param runnerSubnetNsgName string = 'nsg-maffnd-runner'

@description('Azure Bastion host name')
param bastionHostName string = 'bas-maffnd'

@description('Azure Bastion public IP name')
param bastionPublicIpName string = 'pip-maffnd-bastion'

@description('Private DNS zones used for private endpoint resolution')
param privateDnsZoneNames array = [
  'privatelink.blob.core.windows.net'
  'privatelink.search.windows.net'
  'privatelink.documents.azure.com'
  'privatelink.services.ai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
]

@description('Create private DNS VNet links.')
param createPrivateDnsVnetLinks bool = true

@description('Create private endpoints for dependent services.')
param createPrivateEndpoints bool = true

@description('Assign pre-capability-host RBAC (Storage Blob Data Contributor, Cosmos DB Operator, Search roles).')
param assignPreCaphostRbac bool = false

@description('Assign post-capability-host RBAC (Storage Blob Data Owner conditional and Cosmos SQL role).')
param assignPostCaphostRbac bool = false

@description('Create or update account-level capability host configuration.')
param createAccountCapabilityHost bool = false

@description('Create or update project-level capability host configuration.')
param createProjectCapabilityHost bool = false

@description('Manage project connections through the connections API. Disable on reruns when capability host already owns these connections.')
param manageProjectConnections bool = true

@description('Enable Standard Agent network injection scenario on newly created Foundry account.')
param enableStandardAgentNetworkInjection bool = true

@description('Foundry chat deployment name')
param foundryChatDeploymentName string = 'gpt-4o-mini'

@description('Foundry chat model format')
param foundryChatModelFormat string = 'OpenAI'

@description('Foundry chat model name')
param foundryChatModelName string = 'gpt-4o-mini'

@description('Foundry chat model version')
param foundryChatModelVersion string = '2024-07-18'

@description('Foundry chat deployment SKU name')
param foundryChatDeploymentSkuName string = 'GlobalStandard'

@description('Foundry chat deployment capacity')
param foundryChatDeploymentCapacity int = 1

@description('Foundry embeddings deployment name')
param foundryEmbeddingsDeploymentName string = 'text-embedding-3-small'

@description('Foundry embeddings model format')
param foundryEmbeddingsModelFormat string = 'OpenAI'

@description('Foundry embeddings model name')
param foundryEmbeddingsModelName string = 'text-embedding-3-small'

@description('Foundry embeddings model version')
param foundryEmbeddingsModelVersion string = '1'

@description('Foundry embeddings deployment SKU name')
param foundryEmbeddingsDeploymentSkuName string = 'GlobalStandard'

@description('Foundry embeddings deployment capacity')
param foundryEmbeddingsDeploymentCapacity int = 1

@description('Responsible AI policy name applied to model deployments')
param foundryRaiPolicyName string = 'Microsoft.Default'

var suffix = toLower(uniqueString(resourceGroup().id))
var normalizedPrefix = toLower(replace(namePrefix, '-', ''))
var effectiveFoundryAccountName = empty(foundryAccountName) ? take('${normalizedPrefix}ai${suffix}', 64) : foundryAccountName
var effectiveStorageAccountName = empty(storageAccountName) ? take('${normalizedPrefix}st${suffix}', 24) : storageAccountName
var effectiveCosmosAccountName = empty(cosmosAccountName) ? take('${normalizedPrefix}cosmos${suffix}', 44) : cosmosAccountName
var effectiveAiSearchName = empty(aiSearchName) ? take('${normalizedPrefix}srch${suffix}', 60) : aiSearchName
var effectiveAiSearchLocation = empty(aiSearchLocation) ? 'eastus' : aiSearchLocation
var effectiveContainerRegistryName = empty(containerRegistryName) ? take('${normalizedPrefix}acr${suffix}', 50) : containerRegistryName
var effectiveVirtualNetworkName = empty(virtualNetworkName) ? '${normalizedPrefix}-vnet' : virtualNetworkName
var effectiveNatGatewayName = empty(natGatewayName) ? take('${namePrefix}-nat-${suffix}', 80) : natGatewayName
var effectiveNatPublicIpName = empty(natPublicIpName) ? take('${namePrefix}-nat-pip-${suffix}', 80) : natPublicIpName
var effectiveCosmosConnectionName = '${effectiveCosmosAccountName}-${foundryProjectName}'
var effectiveStorageConnectionName = '${effectiveStorageAccountName}-${foundryProjectName}'
var effectiveAiSearchConnectionName = '${effectiveAiSearchName}-${foundryProjectName}'
var effectiveCosmosLocation = empty(cosmosLocation) ? location : cosmosLocation

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
var resolvedProjectPrincipalId = manageProjectConnections ? projectConnections.outputs.projectPrincipalId : foundryProject.identity.principalId
var resolvedProjectWorkspaceId = manageProjectConnections ? projectConnections.outputs.projectWorkspaceId : ''
var resolvedCosmosConnectionName = manageProjectConnections ? projectConnections.outputs.cosmosConnection : effectiveCosmosConnectionName
var resolvedStorageConnectionName = manageProjectConnections ? projectConnections.outputs.storageConnection : effectiveStorageConnectionName
var resolvedAiSearchConnectionName = manageProjectConnections ? projectConnections.outputs.aiSearchConnection : effectiveAiSearchConnectionName

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: effectiveContainerRegistryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: take('${namePrefix}-mon-${suffix}-law', 63)
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: take('${namePrefix}-mon-${suffix}-appi', 260)
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: effectiveStorageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
  }
}

resource aiSearch 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: effectiveAiSearchName
  location: effectiveAiSearchLocation
  sku: {
    name: 'basic'
  }
  properties: {
    publicNetworkAccess: 'disabled'
  }
}

resource cosmosDB 'Microsoft.DocumentDB/databaseAccounts@2024-12-01-preview' = {
  name: effectiveCosmosAccountName
  location: effectiveCosmosLocation
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: effectiveCosmosLocation
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
  }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: effectiveFoundryAccountName
  location: location
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: effectiveFoundryAccountName
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Deny'
      virtualNetworkRules: [
        {
          id: resourceId('Microsoft.Network/virtualNetworks/subnets', effectiveVirtualNetworkName, agentSubnetName)
          ignoreMissingVnetServiceEndpoint: false
        }
      ]
    }
    publicNetworkAccess: 'Disabled'
    #disable-next-line BCP037
    networkInjections: enableStandardAgentNetworkInjection ? [
      {
        #disable-next-line BCP037
        scenario: 'agent'
        #disable-next-line BCP037
        subnetArmId: resourceId('Microsoft.Network/virtualNetworks/subnets', effectiveVirtualNetworkName, agentSubnetName)
      }
    ] : []
  }
  dependsOn: [
    virtualNetwork
  ]
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
    description: 'MAF order resolution Foundry-hosted project'
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundryAccount
  name: foundryChatDeploymentName
  sku: {
    name: foundryChatDeploymentSkuName
    capacity: foundryChatDeploymentCapacity
  }
  properties: {
    model: {
      format: foundryChatModelFormat
      name: foundryChatModelName
      version: foundryChatModelVersion
    }
    raiPolicyName: foundryRaiPolicyName
  }
}

resource embeddingsDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundryAccount
  name: foundryEmbeddingsDeploymentName
  sku: {
    name: foundryEmbeddingsDeploymentSkuName
    capacity: foundryEmbeddingsDeploymentCapacity
  }
  properties: {
    model: {
      format: foundryEmbeddingsModelFormat
      name: foundryEmbeddingsModelName
      version: foundryEmbeddingsModelVersion
    }
    raiPolicyName: foundryRaiPolicyName
  }
  dependsOn: [
    chatDeployment
  ]
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

resource natPublicIp 'Microsoft.Network/publicIPAddresses@2023-09-01' = if (createNatGateway) {
  name: effectiveNatPublicIpName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2023-09-01' = if (createNatGateway) {
  name: effectiveNatGatewayName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 10
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
}

module virtualNetwork './modules/vnet.bicep' = {
  name: 'foundry-vnet-${suffix}'
  params: {
    enabled: true
    location: location
    vnetName: effectiveVirtualNetworkName
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetName: agentSubnetName
    agentSubnetPrefix: agentSubnetPrefix
    natGatewayResourceId: createNatGateway ? natGateway.id : ''
    privateEndpointSubnetName: privateEndpointSubnetName
    privateEndpointSubnetPrefix: privateEndpointSubnetPrefix
    // Keep runner subnet declared in VNet to avoid destructive subnet pruning on shared reruns.
    createRunnerSubnet: true
    runnerSubnetName: runnerSubnetName
    runnerSubnetPrefix: runnerSubnetPrefix
    runnerSubnetNsgResourceId: ''
    runnerSubnetNatGatewayResourceId: createNatGateway ? natGateway.id : ''
    // Keep AzureBastionSubnet declared in VNet to avoid deletion attempts when Bastion already exists.
    createBastionSubnet: true
    bastionSubnetName: bastionSubnetName
    bastionSubnetPrefix: bastionSubnetPrefix
  }
}

module privateRunnerAccess './modules/private-runner-access.bicep' = if (createPrivateRunnerAccess) {
  name: 'private-runner-access-${suffix}'
  params: {
    enabled: createPrivateRunnerAccess
    location: location
    vnetName: effectiveVirtualNetworkName
    runnerSubnetName: runnerSubnetName
    runnerSubnetPrefix: runnerSubnetPrefix
    createRunnerSubnet: false
    bastionSubnetName: bastionSubnetName
    bastionSubnetPrefix: bastionSubnetPrefix
    createBastionSubnet: false
    runnerNsgName: runnerSubnetNsgName
    createBastion: createBastionHost
    createRunnerVm: createRunnerVm
    runnerVmName: runnerVmName
    runnerVmSize: runnerVmSize
    runnerAdminUsername: runnerVmAdminUsername
    runnerSshPublicKey: runnerVmSshPublicKey
    bastionName: bastionHostName
    bastionPublicIpName: bastionPublicIpName
  }
  dependsOn: [
    virtualNetwork
  ]
}

module runnerSubscriptionRbac './modules/runner-subscription-rbac.bicep' = if (createPrivateRunnerAccess && createRunnerVm && assignRunnerSubscriptionRbac) {
  name: 'runner-subscription-rbac-${suffix}'
  scope: subscription()
  params: {
    principalId: privateRunnerAccess.outputs.runnerUamiPrincipalId
    assignContributor: true
    assignUserAccessAdministrator: assignRunnerUserAccessAdministrator
  }
  dependsOn: [
    privateRunnerAccess
  ]
}

module privateDns './modules/private-dns.bicep' = {
  name: 'private-network-dns'
  params: {
    enabled: true
    virtualNetworkId: virtualNetwork.outputs.id
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
    subnetId: virtualNetwork.outputs.privateEndpointSubnetId
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
    subnetId: virtualNetwork.outputs.privateEndpointSubnetId
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
    subnetId: virtualNetwork.outputs.privateEndpointSubnetId
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
    subnetId: virtualNetwork.outputs.privateEndpointSubnetId
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

module projectConnections './modules/foundry-project-existing-connections.bicep' = if (manageProjectConnections) {
  name: 'project-connections-${suffix}'
  params: {
    accountName: effectiveFoundryAccountName
    projectName: foundryProjectName
    location: location
    aiSearchName: effectiveAiSearchName
    aiSearchSubscriptionId: subscription().subscriptionId
    aiSearchResourceGroupName: resourceGroup().name
    storageAccountName: effectiveStorageAccountName
    storageSubscriptionId: subscription().subscriptionId
    storageResourceGroupName: resourceGroup().name
    cosmosAccountName: effectiveCosmosAccountName
    cosmosSubscriptionId: subscription().subscriptionId
    cosmosResourceGroupName: resourceGroup().name
    cosmosConnectionName: effectiveCosmosConnectionName
    storageConnectionName: effectiveStorageConnectionName
    aiSearchConnectionName: effectiveAiSearchConnectionName
  }
  dependsOn: [
    foundryProject
    aiSearch
    storage
    cosmosDB
  ]
}

module formatProjectWorkspaceId './modules/format-project-workspace-id.bicep' = if (manageProjectConnections) {
  name: 'format-workspace-id-${suffix}'
  params: {
    projectWorkspaceId: resolvedProjectWorkspaceId
  }
}

module storageAccountRoleAssignment './modules/azure-storage-account-role-assignment.bicep' = if (assignPreCaphostRbac) {
  name: 'storage-account-rbac-${suffix}'
  params: {
    storageAccountName: effectiveStorageAccountName
    projectPrincipalId: resolvedProjectPrincipalId
  }
  dependsOn: [
    storagePrivateEndpoint
  ]
}

module cosmosAccountRoleAssignments './modules/cosmosdb-account-role-assignment.bicep' = if (assignPreCaphostRbac) {
  name: 'cosmos-account-rbac-${suffix}'
  params: {
    cosmosDBName: effectiveCosmosAccountName
    projectPrincipalId: resolvedProjectPrincipalId
  }
  dependsOn: [
    cosmosPrivateEndpoint
  ]
}

module aiSearchRoleAssignments './modules/ai-search-role-assignments.bicep' = if (assignPreCaphostRbac) {
  name: 'search-account-rbac-${suffix}'
  params: {
    aiSearchName: effectiveAiSearchName
    projectPrincipalId: resolvedProjectPrincipalId
  }
  dependsOn: [
    searchPrivateEndpoint
  ]
}

module addAccountCapabilityHost './modules/add-account-capability-host.bicep' = if (createAccountCapabilityHost) {
  name: 'account-capability-host-${suffix}'
  params: {
    accountName: effectiveFoundryAccountName
    accountCapabilityHostName: accountCapabilityHostName
    agentSubnetResourceId: virtualNetwork.outputs.agentSubnetId
  }
  dependsOn: [
    foundryPrivateEndpoint
  ]
}

module addProjectCapabilityHost './modules/add-project-capability-host.bicep' = if (createProjectCapabilityHost) {
  name: 'project-capability-host-${suffix}'
  params: {
    accountName: effectiveFoundryAccountName
    projectName: foundryProjectName
    projectCapabilityHostName: projectCapabilityHostName
    cosmosConnectionName: resolvedCosmosConnectionName
    storageConnectionName: resolvedStorageConnectionName
    aiSearchConnectionName: resolvedAiSearchConnectionName
  }
  dependsOn: [
    addAccountCapabilityHost
    storageAccountRoleAssignment
    cosmosAccountRoleAssignments
    aiSearchRoleAssignments
  ]
}

module storageContainersRoleAssignment './modules/blob-storage-container-role-assignments.bicep' = if (assignPostCaphostRbac && createProjectCapabilityHost && manageProjectConnections) {
  name: 'storage-container-rbac-${suffix}'
  params: {
    aiProjectPrincipalId: resolvedProjectPrincipalId
    storageName: effectiveStorageAccountName
    workspaceId: formatProjectWorkspaceId!.outputs.projectWorkspaceIdGuid
  }
  dependsOn: [
    addProjectCapabilityHost
  ]
}

module cosmosContainerRoleAssignments './modules/cosmos-container-role-assignments.bicep' = if (assignPostCaphostRbac && createProjectCapabilityHost && manageProjectConnections) {
  name: 'cosmos-container-rbac-${suffix}'
  params: {
    cosmosAccountName: effectiveCosmosAccountName
    projectWorkspaceId: formatProjectWorkspaceId!.outputs.projectWorkspaceIdGuid
    projectPrincipalId: resolvedProjectPrincipalId
  }
  dependsOn: [
    addProjectCapabilityHost
    storageContainersRoleAssignment
  ]
}

var foundryProjectEndpoint = 'https://${effectiveFoundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
var foundryHostedInvocationsUrl = '${foundryProjectEndpoint}/agents/${hostedAgentName}/endpoint/protocols/invocations?api-version=v1'

output foundryAccountName string = foundryAccount.name
output foundryProjectName string = foundryProject.name
output foundryProjectEndpoint string = foundryProjectEndpoint
output natGatewayId string = createNatGateway ? natGateway.id : ''
output foundryHostedInvocationsUrl string = foundryHostedInvocationsUrl
output foundryEventCallbackTokenSettingName string = foundryEventCallbackTokenSettingName
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString
output accountCapabilityHost string = createAccountCapabilityHost ? addAccountCapabilityHost!.outputs.accountCapabilityHostName : ''
output projectCapabilityHost string = createProjectCapabilityHost ? addProjectCapabilityHost!.outputs.projectCapabilityHostName : ''
output projectPrincipalId string = resolvedProjectPrincipalId
output projectWorkspaceId string = resolvedProjectWorkspaceId
output connectionNames object = {
  cosmos: resolvedCosmosConnectionName
  storage: resolvedStorageConnectionName
  aiSearch: resolvedAiSearchConnectionName
}
output virtualNetwork object = {
  name: virtualNetwork.outputs.name
  id: virtualNetwork.outputs.id
  agentSubnetId: virtualNetwork.outputs.agentSubnetId
  privateEndpointSubnetId: virtualNetwork.outputs.privateEndpointSubnetId
}
output privateEndpointIds object = {
  storage: storagePrivateEndpoint.outputs.id
  aiSearch: searchPrivateEndpoint.outputs.id
  cosmos: cosmosPrivateEndpoint.outputs.id
  foundry: foundryPrivateEndpoint.outputs.id
}
output privateRunnerAccess object = createPrivateRunnerAccess ? {
  enabled: true
  runnerSubnetId: privateRunnerAccess!.outputs.runnerSubnetId
  bastionSubnetId: privateRunnerAccess!.outputs.bastionSubnetId
  runnerVmId: privateRunnerAccess!.outputs.runnerVmId
  runnerVmPrincipalId: privateRunnerAccess!.outputs.runnerVmPrincipalId
  runnerUamiId: privateRunnerAccess!.outputs.runnerUamiId
  runnerUamiPrincipalId: privateRunnerAccess!.outputs.runnerUamiPrincipalId
  runnerUamiClientId: privateRunnerAccess!.outputs.runnerUamiClientId
  bastionHostId: privateRunnerAccess!.outputs.bastionHostId
  bastionPublicIpId: privateRunnerAccess!.outputs.bastionPublicIpId
} : {
  enabled: false
  runnerSubnetId: ''
  bastionSubnetId: ''
  runnerVmId: ''
  runnerVmPrincipalId: ''
  runnerUamiId: ''
  runnerUamiPrincipalId: ''
  runnerUamiClientId: ''
  bastionHostId: ''
  bastionPublicIpId: ''
}
output requiredBackendSettings array = [
  'WORKFLOW_MODE=foundry_hosted'
  'FOUNDRY_HOSTED_INVOCATIONS_URL=${foundryHostedInvocationsUrl}'
  '${foundryEventCallbackTokenSettingName}=<shared-callback-token>'
  'APPLICATIONINSIGHTS_CONNECTION_STRING=${applicationInsights.properties.ConnectionString}'
]
output nextStep string = 'Run azd deploy order-resolution-hosted, then azd ai agent invoke for invocations/responses protocols and verify Foundry + App Insights telemetry.'
