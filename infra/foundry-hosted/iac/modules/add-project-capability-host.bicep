param accountName string
param projectName string
param projectCapabilityHostName string = 'caphostproj'
param cosmosConnectionName string
param storageConnectionName string
param aiSearchConnectionName string

var threadConnections = [
  cosmosConnectionName
]
var storageConnections = [
  storageConnectionName
]
var vectorStoreConnections = [
  aiSearchConnectionName
]

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  name: projectName
  parent: account
}

resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  name: projectCapabilityHostName
  parent: project
  properties: {
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
    vectorStoreConnections: vectorStoreConnections
    storageConnections: storageConnections
    threadStorageConnections: threadConnections
  }
}

output projectCapabilityHostName string = projectCapabilityHost.name
