@description('Name of the existing AI Foundry account')
param accountName string

@description('Name of the existing AI Foundry project to update in place')
param projectName string

@description('Location for metadata fields')
param location string

@description('Connection name for hosted runtime secret values')
param runtimeConnectionName string = 'orderresolutionruntimesecrets'

@description('Hosted runtime DATABASE_URL value to store under database_url')
@secure()
param runtimeDatabaseUrl string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName

  resource runtimeSecretConnection 'connections@2025-04-01-preview' = {
    name: runtimeConnectionName
    properties: {
      category: 'CustomKeys'
      authType: 'CustomKeys'
      target: 'https://runtime-secrets.local'
      credentials: {
        keys: {
          database_url: runtimeDatabaseUrl
        }
      }
      metadata: {
        ApiType: 'KeyValue'
        location: location
      }
    }
  }
}

output runtimeConnection string = runtimeConnectionName
