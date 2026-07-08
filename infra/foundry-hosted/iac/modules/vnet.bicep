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

@description('Optional NAT gateway resource ID attached to the agent subnet')
param natGatewayResourceId string = ''

@description('Subnet name for private endpoints')
param privateEndpointSubnetName string = 'pe-subnet'

@description('Address prefix for the private endpoint subnet')
param privateEndpointSubnetPrefix string = '192.168.1.0/24'

@description('Whether to include runner subnet in the VNet subnet collection')
param createRunnerSubnet bool = false

@description('Runner subnet name')
param runnerSubnetName string = 'snet-runner'

@description('Runner subnet prefix')
param runnerSubnetPrefix string = '192.168.2.0/24'

@description('Optional NSG resource ID for runner subnet')
param runnerSubnetNsgResourceId string = ''

@description('Whether to include Azure Bastion subnet in the VNet subnet collection')
param createBastionSubnet bool = false

@description('Azure Bastion subnet name')
param bastionSubnetName string = 'AzureBastionSubnet'

@description('Azure Bastion subnet prefix')
param bastionSubnetPrefix string = '192.168.3.0/26'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = if (enabled) {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: concat(
      [
        {
          name: agentSubnetName
          properties: {
            addressPrefix: agentSubnetPrefix
            natGateway: empty(natGatewayResourceId) ? null : {
              id: natGatewayResourceId
            }
            delegations: [
              {
                name: 'Microsoft.App/environments'
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
      ],
      createRunnerSubnet ? [
        {
          name: runnerSubnetName
          properties: {
            addressPrefix: runnerSubnetPrefix
            networkSecurityGroup: empty(runnerSubnetNsgResourceId) ? null : {
              id: runnerSubnetNsgResourceId
            }
          }
        }
      ] : [],
      createBastionSubnet ? [
        {
          name: bastionSubnetName
          properties: {
            addressPrefix: bastionSubnetPrefix
          }
        }
      ] : []
    )
  }
}

output id string = resourceId('Microsoft.Network/virtualNetworks', vnetName)
output name string = vnetName
output agentSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, agentSubnetName)
output privateEndpointSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, privateEndpointSubnetName)
