targetScope = 'subscription'

@description('Principal object ID to grant subscription deployment permissions')
param principalId string

@description('Assign Contributor at subscription scope')
param assignContributor bool = true

@description('Assign User Access Administrator at subscription scope')
param assignUserAccessAdministrator bool = false

resource contributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = if (assignContributor) {
  scope: subscription()
  name: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
}

resource userAccessAdministratorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = if (assignUserAccessAdministrator) {
  scope: subscription()
  name: '18d7d88d-d35e-4fb5-a5c3-7773c20a72d9'
}

resource contributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignContributor) {
  scope: subscription()
  name: guid(subscription().id, principalId, contributorRole.id, 'runner-subscription-contributor')
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: contributorRole.id
  }
}

resource userAccessAdministratorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignUserAccessAdministrator) {
  scope: subscription()
  name: guid(subscription().id, principalId, userAccessAdministratorRole.id, 'runner-subscription-uaa')
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: userAccessAdministratorRole.id
  }
}
