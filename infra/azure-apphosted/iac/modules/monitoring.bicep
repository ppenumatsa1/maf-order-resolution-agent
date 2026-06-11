targetScope = 'resourceGroup'

param name string
param location string = resourceGroup().location
param tags object = {}

var workspaceName = take('${name}-law', 63)
var appInsightsName = take('${name}-appi', 260)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

output logAnalyticsWorkspaceId string = logAnalytics.id
output logAnalyticsCustomerId string = logAnalytics.properties.customerId
@secure()
output logAnalyticsSharedKey string = logAnalytics.listKeys().primarySharedKey
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString
