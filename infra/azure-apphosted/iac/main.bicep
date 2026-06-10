targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Prefix used for deployed resources')
param namePrefix string = 'mafapp'

var suffix = toLower(uniqueString(resourceGroup().id))
var logAnalyticsWorkspaceName = take('${namePrefix}law${suffix}', 63)
var managedEnvironmentName = take('${namePrefix}cae${suffix}', 60)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: managedEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: listKeys(logAnalytics.id, logAnalytics.apiVersion).primarySharedKey
      }
    }
  }
}

output logAnalyticsWorkspaceId string = logAnalytics.id
output managedEnvironmentId string = managedEnvironment.id
