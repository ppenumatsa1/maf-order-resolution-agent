@description('Name of the storage account')
param storageName string

@description('Principal ID of the AI project')
param aiProjectPrincipalId string

@description('Workspace GUID used to scope container role conditions')
param workspaceId string

resource storage 'Microsoft.Storage/storageAccounts@2022-05-01' existing = {
  name: storageName
  scope: resourceGroup()
}

resource storageBlobDataOwner 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  scope: resourceGroup()
}

var conditionStr = '((!(ActionMatches{\'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/read\'}) AND !(ActionMatches{\'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/filter/action\'}) AND !(ActionMatches{\'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags/write\'})) OR (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringStartsWithIgnoreCase \'${workspaceId}\' AND @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringLikeIgnoreCase \'*-azureml-agent\'))'

resource storageBlobDataOwnerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, aiProjectPrincipalId, storageBlobDataOwner.id, workspaceId)
  properties: {
    principalId: aiProjectPrincipalId
    roleDefinitionId: storageBlobDataOwner.id
    principalType: 'ServicePrincipal'
    conditionVersion: '2.0'
    condition: conditionStr
  }
}
