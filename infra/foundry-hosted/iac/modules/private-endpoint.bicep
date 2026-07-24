@description('Deployment location')
param location string

@description('Enable private endpoint creation')
param enabled bool = true

@description('Private endpoint resource name')
param name string

@description('Subnet resource ID where private endpoint will be created')
param subnetId string

@description('Target resource ID for private endpoint')
param targetResourceId string

@description('Private link group IDs for the target resource')
param groupIds array

@description('Private DNS zone resource IDs to bind through zone group')
param privateDnsZoneIds array = []

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = if (enabled) {
  name: name
  location: location
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pls-${name}'
        properties: {
          privateLinkServiceId: targetResourceId
          groupIds: groupIds
        }
      }
    ]
  }
}

resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-09-01' = if (enabled && !empty(privateDnsZoneIds)) {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (zoneId, i) in privateDnsZoneIds: {
      name: 'dns-${i}'
      properties: {
        privateDnsZoneId: zoneId
      }
    }]
  }
}

output id string = enabled ? resourceId('Microsoft.Network/privateEndpoints', name) : ''
output name string = enabled ? privateEndpoint.name : ''
