@description('Name of the existing AI Foundry account')
param accountName string

@description('Name of the account-level capability host')
param accountCapabilityHostName string = '${accountName}@aml_aiagentservice'

@description('ARM resource ID of the delegated agent subnet')
param agentSubnetResourceId string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: accountName
}

resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
  name: accountCapabilityHostName
  parent: account
  properties: {
    #disable-next-line BCP037
    capabilityHostKind: 'Agents'
    #disable-next-line BCP037
    customerSubnet: agentSubnetResourceId
  }
}

output accountCapabilityHostName string = accountCapabilityHost.name
