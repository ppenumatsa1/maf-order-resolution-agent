@description('Virtual network resource ID to link private DNS zones to')
param virtualNetworkId string

@description('Enable private DNS zone and link creation')
param enabled bool = true

@description('Zone names to create for private endpoint resolution')
param zoneNames array

@description('Create VNet links for private DNS zones. Set false when links already exist.')
param createVnetLinks bool = true

resource privateZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zoneName in zoneNames: if (enabled) {
  name: zoneName
  location: 'global'
}]

resource zoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zoneName, i) in zoneNames: if (enabled && createVnetLinks) {
  name: 'link-${replace(zoneName, '.', '-')}'
  parent: privateZones[i]
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetworkId
    }
  }
}]

output zoneIds array = [for zoneName in zoneNames: resourceId('Microsoft.Network/privateDnsZones', zoneName)]
output zoneNames array = zoneNames
