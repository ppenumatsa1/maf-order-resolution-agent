targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Prefix used for shared resources')
param namePrefix string = 'maffd'

@description('Foundry hosted invocations endpoint URL wired into backend runtime (optional during scaffold).')
param foundryHostedInvocationsUrl string = ''

@description('Name of the callback token setting used by backend event ingress.')
param foundryEventCallbackTokenSettingName string = 'FOUNDRY_EVENT_CALLBACK_TOKEN'

var suffix = toLower(uniqueString(resourceGroup().id))
var storageAccountName = take(replace('${namePrefix}st${suffix}', '-', ''), 24)
var appConfigName = take('${namePrefix}-appcs-${suffix}', 50)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
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
}

output storageAccountId string = storage.id
output appConfigurationId string = appConfig.id
output foundryHostedInvocationsUrl string = foundryHostedInvocationsUrl
output foundryEventCallbackTokenSettingName string = foundryEventCallbackTokenSettingName
output requiredBackendSettings array = [
  'WORKFLOW_MODE=foundry_hosted'
  'FOUNDRY_HOSTED_INVOCATIONS_URL=<hosted-agent-invocations-endpoint>'
  '${foundryEventCallbackTokenSettingName}=<shared-callback-token>'
]
output nextStep string = 'Bind hosted agent deployment endpoint and callback token, then run azd ai agent show/invoke validation.'
