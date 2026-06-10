targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Prefix used for shared resources')
param namePrefix string = 'maffd'

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
output nextStep string = 'Add Foundry project/agent resources and bind runtime identity.'
