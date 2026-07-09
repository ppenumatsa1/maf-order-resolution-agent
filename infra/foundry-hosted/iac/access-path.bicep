targetScope = 'resourceGroup'

@description('Deployment location')
param location string = resourceGroup().location

@description('Target virtual network name')
param virtualNetworkName string = 'maffnd-vnet'

@description('Enable private runner access resources')
param createPrivateRunnerAccess bool = true

@description('Runner subnet name')
param runnerSubnetName string = 'snet-runner'

@description('Runner subnet prefix')
param runnerSubnetPrefix string = '10.90.3.0/24'

@description('Azure Bastion subnet name. Must be AzureBastionSubnet.')
param bastionSubnetName string = 'AzureBastionSubnet'

@description('Azure Bastion subnet prefix (minimum /26).')
param bastionSubnetPrefix string = '10.90.4.0/26'

@description('Create Azure Bastion host')
param createBastionHost bool = true

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

@description('Runner VM admin username')
param runnerVmAdminUsername string = 'azureuser'

@description('SSH public key for runner VM admin user. Required when createRunnerVm is true.')
param runnerVmSshPublicKey string = ''

@description('Runner subnet NSG name')
param runnerSubnetNsgName string = 'nsg-maffnd-runner'

@description('Azure Bastion host name')
param bastionHostName string = 'bas-maffnd'

@description('Azure Bastion public IP name')
param bastionPublicIpName string = 'pip-maffnd-bastion'

module privateRunnerAccess './modules/private-runner-access.bicep' = if (createPrivateRunnerAccess) {
  name: 'private-runner-access'
  params: {
    enabled: createPrivateRunnerAccess
    location: location
    vnetName: virtualNetworkName
    runnerSubnetName: runnerSubnetName
    runnerSubnetPrefix: runnerSubnetPrefix
    bastionSubnetName: bastionSubnetName
    bastionSubnetPrefix: bastionSubnetPrefix
    runnerNsgName: runnerSubnetNsgName
    createBastion: createBastionHost
    createRunnerVm: createRunnerVm
    createRunnerUami: createRunnerUami
    runnerUamiName: runnerUamiName
    keepSystemAssignedIdentity: keepSystemAssignedIdentity
    runnerVmName: runnerVmName
    runnerVmSize: runnerVmSize
    runnerAdminUsername: runnerVmAdminUsername
    runnerSshPublicKey: runnerVmSshPublicKey
    bastionName: bastionHostName
    bastionPublicIpName: bastionPublicIpName
  }
}

output privateRunnerAccess object = createPrivateRunnerAccess ? {
  enabled: true
  runnerSubnetId: privateRunnerAccess!.outputs.runnerSubnetId
  bastionSubnetId: privateRunnerAccess!.outputs.bastionSubnetId
  runnerVmId: privateRunnerAccess!.outputs.runnerVmId
  runnerVmPrincipalId: privateRunnerAccess!.outputs.runnerVmPrincipalId
  runnerUamiId: privateRunnerAccess!.outputs.runnerUamiId
  runnerUamiPrincipalId: privateRunnerAccess!.outputs.runnerUamiPrincipalId
  runnerUamiClientId: privateRunnerAccess!.outputs.runnerUamiClientId
  bastionHostId: privateRunnerAccess!.outputs.bastionHostId
  bastionPublicIpId: privateRunnerAccess!.outputs.bastionPublicIpId
  runnerVmSkippedReason: privateRunnerAccess!.outputs.runnerVmSkippedReason
} : {
  enabled: false
  runnerSubnetId: ''
  bastionSubnetId: ''
  runnerVmId: ''
  runnerVmPrincipalId: ''
  runnerUamiId: ''
  runnerUamiPrincipalId: ''
  runnerUamiClientId: ''
  bastionHostId: ''
  bastionPublicIpId: ''
  runnerVmSkippedReason: ''
}
