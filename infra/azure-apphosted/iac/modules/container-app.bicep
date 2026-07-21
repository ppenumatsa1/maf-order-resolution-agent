targetScope = 'resourceGroup'

param name string
param location string = resourceGroup().location
param tags object = {}
param serviceName string
param managedEnvironmentId string
param image string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param targetPort int
param cpu string = '0.5'
param memory string = '1Gi'
param minReplicas int = 1
param maxReplicas int = 2
param env array = []
param registries array = []
param userAssignedIdentityId string
param command array = []

@secure()
param secrets object

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: union(tags, {
    'azd-service-name': serviceName
  })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: registries
      secrets: secrets.items
    }
    template: {
      containers: [
        {
          name: serviceName
          image: image
          command: command
          env: env
          resources: {
            cpu: json(cpu)
            memory: memory
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output id string = containerApp.id
output name string = containerApp.name
output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
