@description('Deployment location')
param location string

@description('Enable virtual network resource creation')
param enabled bool = true

@description('Virtual network name')
param vnetName string

@description('Address space for the virtual network')
param vnetAddressPrefix string = '192.168.0.0/16'

@description('Subnet name for Foundry agent network injection')
param agentSubnetName string = 'agent-subnet'

@description('Address prefix for the Foundry agent subnet')
param agentSubnetPrefix string = '192.168.0.0/24'

@description('Subnet name for private endpoints')
param privateEndpointSubnetName string = 'pe-subnet'

@description('Address prefix for the private endpoint subnet')
param privateEndpointSubnetPrefix string = '192.168.1.0/24'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = if (enabled) {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: agentSubnetName
        properties: {
          addressPrefix: agentSubnetPrefix
          delegations: [
            {
              name: 'delegation-agent-environment'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: privateEndpointSubnetName
        properties: {
          addressPrefix: privateEndpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

output id string = resourceId('Microsoft.Network/virtualNetworks', vnetName)
output name string = vnetName
output agentSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, agentSubnetName)
output privateEndpointSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, privateEndpointSubnetName)
