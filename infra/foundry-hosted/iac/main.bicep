targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Prefix used for shared resources')
@minLength(3)
param namePrefix string = 'maffd'

@description('Foundry hosted invocations endpoint URL wired into backend runtime (optional during scaffold).')
param foundryHostedInvocationsUrl string = ''

@description('Name of the callback token setting used by backend event ingress.')
param foundryEventCallbackTokenSettingName string = 'FOUNDRY_EVENT_CALLBACK_TOKEN'

@description('Enable private networking resources (VNet, DNS, and private endpoints).')
param enablePrivateNetworking bool = false

@description('Optional virtual network name. When empty, a deterministic name is generated.')
param vnetName string = ''

@description('Address space for the private networking VNet.')
param vnetAddressPrefix string = '192.168.0.0/16'

@description('Subnet name for Foundry agent network injection.')
param agentSubnetName string = 'agent-subnet'

@description('Address prefix for the Foundry agent subnet.')
param agentSubnetPrefix string = '192.168.0.0/24'

@description('Subnet name for private endpoints.')
param privateEndpointSubnetName string = 'pe-subnet'

@description('Address prefix for the private endpoint subnet.')
param privateEndpointSubnetPrefix string = '192.168.1.0/24'

@description('Private DNS zones created and linked when private networking is enabled.')
#disable-next-line no-hardcoded-env-urls
param privateDnsZoneNames array = [
  'privatelink.blob.core.windows.net'
  'privatelink.azconfig.io'
  'privatelink.services.ai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
]

@description('Optional existing Foundry account resource ID for private endpoint creation.')
param existingFoundryAccountResourceId string = ''

var suffix = toLower(uniqueString(resourceGroup().id))
var safeNamePrefix = take('${toLower(replace(namePrefix, '-', ''))}maf', 8)
var storageAccountName = take('${safeNamePrefix}st${suffix}', 24)
var appConfigName = take('${namePrefix}-appcs-${suffix}', 50)
var effectiveVnetName = empty(vnetName) ? '${namePrefix}-vnet-${suffix}' : vnetName

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    publicNetworkAccess: enablePrivateNetworking ? 'Disabled' : 'Enabled'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource appConfig 'Microsoft.AppConfiguration/configurationStores@2024-06-01-preview' = {
  name: appConfigName
  location: location
  sku: {
    name: 'standard'
  }
  properties: {
    publicNetworkAccess: enablePrivateNetworking ? 'Disabled' : 'Enabled'
  }
}

module vnet './modules/vnet.bicep' = {
  name: 'private-network-vnet'
  params: {
    enabled: enablePrivateNetworking
    location: location
    vnetName: effectiveVnetName
    vnetAddressPrefix: vnetAddressPrefix
    agentSubnetName: agentSubnetName
    agentSubnetPrefix: agentSubnetPrefix
    privateEndpointSubnetName: privateEndpointSubnetName
    privateEndpointSubnetPrefix: privateEndpointSubnetPrefix
  }
}

module privateDns './modules/private-dns.bicep' = {
  name: 'private-network-dns'
  params: {
    enabled: enablePrivateNetworking
    virtualNetworkId: vnet.outputs.id
    zoneNames: privateDnsZoneNames
  }
}

#disable-next-line no-hardcoded-env-urls
var storageZoneName = 'privatelink.blob.core.windows.net'
var appConfigZoneName = 'privatelink.azconfig.io'
var foundryZoneNames = [
  'privatelink.services.ai.azure.com'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
]
var storageZoneIndex = indexOf(privateDnsZoneNames, storageZoneName)
var appConfigZoneIndex = indexOf(privateDnsZoneNames, appConfigZoneName)
var foundryServicesZoneIndex = indexOf(privateDnsZoneNames, foundryZoneNames[0])
var foundryCognitiveZoneIndex = indexOf(privateDnsZoneNames, foundryZoneNames[1])
var foundryOpenAiZoneIndex = indexOf(privateDnsZoneNames, foundryZoneNames[2])

module storagePrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-storage'
  params: {
    enabled: enablePrivateNetworking
    location: location
    name: '${namePrefix}-storage-pe-${suffix}'
    subnetId: vnet.outputs.privateEndpointSubnetId
    targetResourceId: storage.id
    groupIds: [
      'blob'
    ]
    privateDnsZoneIds: [
      privateDns.outputs.zoneIds[storageZoneIndex]
    ]
  }
}

module appConfigPrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-appconfig'
  params: {
    enabled: enablePrivateNetworking
    location: location
    name: '${namePrefix}-appconfig-pe-${suffix}'
    subnetId: vnet.outputs.privateEndpointSubnetId
    targetResourceId: appConfig.id
    groupIds: [
      'configurationStores'
    ]
    privateDnsZoneIds: [
      privateDns.outputs.zoneIds[appConfigZoneIndex]
    ]
  }
}

module foundryPrivateEndpoint './modules/private-endpoint.bicep' = {
  name: 'private-endpoint-foundry-account'
  params: {
    enabled: enablePrivateNetworking && !empty(existingFoundryAccountResourceId)
    location: location
    name: '${namePrefix}-foundry-pe-${suffix}'
    subnetId: vnet.outputs.privateEndpointSubnetId
    targetResourceId: existingFoundryAccountResourceId
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

output storageAccountId string = storage.id
output appConfigurationId string = appConfig.id
output foundryHostedInvocationsUrl string = foundryHostedInvocationsUrl
output foundryEventCallbackTokenSettingName string = foundryEventCallbackTokenSettingName
output privateNetworkingEnabled bool = enablePrivateNetworking
output vnetId string = enablePrivateNetworking ? vnet.outputs.id : ''
output privateEndpointSubnetId string = enablePrivateNetworking ? vnet.outputs.privateEndpointSubnetId : ''
output foundryPrivateEndpointId string = (enablePrivateNetworking && !empty(existingFoundryAccountResourceId)) ? foundryPrivateEndpoint.outputs.id : ''
output requiredBackendSettings array = [
  'WORKFLOW_MODE=foundry_hosted'
  'FOUNDRY_HOSTED_INVOCATIONS_URL=<hosted-agent-invocations-endpoint>'
  '${foundryEventCallbackTokenSettingName}=<shared-callback-token>'
]
output nextStep string = enablePrivateNetworking ? 'Validate private endpoint approvals and DNS resolution, then bind hosted agent endpoint/callback token and run azd ai agent show/invoke validation.' : 'Bind hosted agent deployment endpoint and callback token, then run azd ai agent show/invoke validation.'
