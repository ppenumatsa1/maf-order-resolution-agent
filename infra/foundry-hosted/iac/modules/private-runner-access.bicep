@description('Enable private runner access resources')
param enabled bool = false

@description('Deployment location')
param location string

@description('Virtual network name where runner/bastion subnets are created')
param vnetName string

@description('Runner subnet name')
param runnerSubnetName string = 'snet-runner'

@description('Runner subnet prefix')
param runnerSubnetPrefix string = '10.90.3.0/24'

@description('Create the runner subnet in this module. Disable when subnet is managed by another module.')
param createRunnerSubnet bool = true

@description('Azure Bastion subnet name. Must be AzureBastionSubnet.')
param bastionSubnetName string = 'AzureBastionSubnet'

@description('Azure Bastion subnet prefix (minimum /26).')
param bastionSubnetPrefix string = '10.90.4.0/26'

@description('Create the Bastion subnet in this module. Disable when subnet is managed by another module.')
param createBastionSubnet bool = true

@description('Runner NSG name')
param runnerNsgName string = 'nsg-maffnd-runner'

@description('Create Azure Bastion host')
param createBastion bool = true

@description('Create private VM runner')
param createRunnerVm bool = true

@description('Create and attach a user-assigned managed identity to the runner VM.')
param createRunnerUami bool = true

@description('Runner user-assigned managed identity name')
param runnerUamiName string = 'uami-maffnd-runner'

@description('Keep system-assigned identity on VM in addition to UAMI.')
param keepSystemAssignedIdentity bool = false

@description('Runner VM name')
param runnerVmName string = 'vm-maffnd-runner'

@description('Runner VM size')
param runnerVmSize string = 'Standard_D4s_v5'

@description('Runner admin username')
param runnerAdminUsername string = 'azureuser'

@description('SSH public key for runner VM admin user. Required when createRunnerVm is true.')
param runnerSshPublicKey string = ''

@description('Azure Bastion host name')
param bastionName string = 'bas-maffnd'

@description('Azure Bastion public IP name')
param bastionPublicIpName string = 'pip-maffnd-bastion'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' existing = {
  name: vnetName
}

resource runnerNsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = if (enabled) {
  name: runnerNsgName
  location: location
  properties: {
    securityRules: []
  }
}

resource runnerSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = if (enabled && createRunnerSubnet) {
  parent: vnet
  name: runnerSubnetName
  properties: {
    addressPrefix: runnerSubnetPrefix
    privateEndpointNetworkPolicies: 'Disabled'
    networkSecurityGroup: {
      id: runnerNsg.id
    }
  }
}

resource runnerSubnetExisting 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' existing = if (enabled && !createRunnerSubnet) {
  parent: vnet
  name: runnerSubnetName
}

resource bastionSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = if (enabled && createBastion && createBastionSubnet) {
  parent: vnet
  name: bastionSubnetName
  properties: {
    addressPrefix: bastionSubnetPrefix
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

resource bastionSubnetExisting 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' existing = if (enabled && createBastion && !createBastionSubnet) {
  parent: vnet
  name: bastionSubnetName
}

var runnerSubnetId = createRunnerSubnet ? runnerSubnet.id : runnerSubnetExisting.id
var bastionSubnetId = createBastionSubnet ? bastionSubnet.id : bastionSubnetExisting.id

var createRunnerVmEffective = enabled && createRunnerVm && !empty(runnerSshPublicKey)

resource runnerUami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (enabled && createRunnerVm && createRunnerUami) {
  name: runnerUamiName
  location: location
}

resource runnerNic 'Microsoft.Network/networkInterfaces@2023-09-01' = if (createRunnerVmEffective) {
  name: '${runnerVmName}-nic'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: runnerSubnetId
          }
        }
      }
    ]
  }
}

resource runnerVm 'Microsoft.Compute/virtualMachines@2023-09-01' = if (createRunnerVmEffective) {
  name: runnerVmName
  location: location
  identity: {
    type: createRunnerUami ? (keepSystemAssignedIdentity ? 'SystemAssigned, UserAssigned' : 'UserAssigned') : 'SystemAssigned'
    userAssignedIdentities: createRunnerUami ? {
      '${runnerUami.id}': {}
    } : null
  }
  properties: {
    hardwareProfile: {
      vmSize: runnerVmSize
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Standard_LRS'
        }
      }
    }
    osProfile: {
      computerName: runnerVmName
      adminUsername: runnerAdminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${runnerAdminUsername}/.ssh/authorized_keys'
              keyData: runnerSshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: runnerNic.id
          properties: {
            primary: true
          }
        }
      ]
    }
  }
}

resource bastionPublicIp 'Microsoft.Network/publicIPAddresses@2023-09-01' = if (enabled && createBastion) {
  name: bastionPublicIpName
  location: location
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource bastionHost 'Microsoft.Network/bastionHosts@2023-09-01' = if (enabled && createBastion) {
  name: bastionName
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'bastion-ipcfg'
        properties: {
          subnet: {
            id: bastionSubnetId
          }
          publicIPAddress: {
            id: bastionPublicIp.id
          }
        }
      }
    ]
  }
}

output runnerSubnetId string = enabled ? runnerSubnetId : ''
output bastionSubnetId string = (enabled && createBastion) ? bastionSubnetId : ''
output runnerVmId string = createRunnerVmEffective ? runnerVm.id : ''
output runnerVmPrincipalId string = (createRunnerVmEffective && (!createRunnerUami || keepSystemAssignedIdentity)) ? runnerVm!.identity.principalId : ''
output runnerUamiId string = (enabled && createRunnerVm && createRunnerUami) ? runnerUami.id : ''
output runnerUamiPrincipalId string = (enabled && createRunnerVm && createRunnerUami) ? runnerUami!.properties.principalId : ''
output runnerUamiClientId string = (enabled && createRunnerVm && createRunnerUami) ? runnerUami!.properties.clientId : ''
output bastionHostId string = (enabled && createBastion) ? bastionHost.id : ''
output bastionPublicIpId string = (enabled && createBastion) ? bastionPublicIp.id : ''
output runnerVmSkippedReason string = (enabled && createRunnerVm && empty(runnerSshPublicKey)) ? 'runnerVmSshPublicKey is empty; VM creation skipped' : ''
