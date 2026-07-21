targetScope = 'resourceGroup'

param name string
param location string = resourceGroup().location
param tags object = {}
param databaseName string = 'maf_workflow'
@description('Optional public IPv4 address of the AZD runner that performs the Entra grant bootstrap.')
param bootstrapAllowedIp string = ''

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: subscription().tenantId
    }
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }

  resource allowBootstrapRunner 'firewallRules@2023-06-01-preview' = if (!empty(bootstrapAllowedIp)) {
    name: 'allow-bootstrap-runner'
    properties: {
      startIpAddress: bootstrapAllowedIp
      endIpAddress: bootstrapAllowedIp
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-06-01-preview' = {
  parent: server
  name: 'allow-azure-services'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }


}

output id string = server.id
output name string = server.name
output fullyQualifiedDomainName string = server.properties.fullyQualifiedDomainName
