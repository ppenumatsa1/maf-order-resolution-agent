# Foundry-Hosted Private-Only (Sample-15 Aligned)

This stack is now a direct private-only BYO resource wiring for Foundry-hosted execution.

- No public-mode toggle.
- No dual setup paths.
- Existing Foundry account/project, Search, Storage, Cosmos, and VNet/subnets are required.
- Capability hosts and project connections follow the sample-15 ordering model.

## Layout

- `iac/main.bicep`: private-only orchestration entrypoint.
- `iac/modules/foundry-project-existing-connections.bicep`: updates existing project connections for Cosmos, Storage, and Search.
- `iac/modules/add-account-capability-host.bicep`: account-level capability host (`Agents`) with `customerSubnet`.
- `iac/modules/add-project-capability-host.bicep`: project capability host (`Agents`) with thread/storage/vector connection bindings.
- `iac/modules/azure-storage-account-role-assignment.bicep`: Storage Blob Data Contributor role before project caphost.
- `iac/modules/cosmosdb-account-role-assignment.bicep`: Cosmos DB Operator role before project caphost.
- `iac/modules/ai-search-role-assignments.bicep`: Search role assignments before project caphost.
- `iac/modules/blob-storage-container-role-assignments.bicep`: Storage Blob Data Owner conditional role after project caphost.
- `iac/modules/cosmos-container-role-assignments.bicep`: Cosmos SQL role assignment after project caphost.
- `iac/modules/format-project-workspace-id.bicep`: extracts workspace GUID for role scoping.
- `iac/modules/private-dns.bicep`: private DNS zones and VNet links.
- `iac/modules/private-endpoint.bicep`: private endpoints (storage/search/cosmos/foundry account).
- `iac/parameters.dev.json`: dev template for required BYO inputs.

## Deployment Inputs

Mandatory BYO parameters in `iac/parameters.dev.json`:

- `foundryAccountName`
- `foundryProjectName`
- `aiSearchName`
- `storageAccountName`
- `cosmosAccountName`
- `virtualNetworkResourceId`
- `agentSubnetResourceId`
- `privateEndpointSubnetResourceId`
- `foundryHostedInvocationsUrl`

Optional overrides:

- `cosmosConnectionName`
- `storageConnectionName`
- `aiSearchConnectionName`
- `accountCapabilityHostName`
- `projectCapabilityHostName`

Cross-RG/subscription inputs default to current context and can be overridden with:

- `aiSearchSubscriptionId`, `aiSearchResourceGroupName`
- `storageSubscriptionId`, `storageResourceGroupName`
- `cosmosSubscriptionId`, `cosmosResourceGroupName`

## Private DNS Zones

Default private DNS zone list:

- `privatelink.blob.core.windows.net`
- `privatelink.search.windows.net`
- `privatelink.documents.azure.com`
- `privatelink.services.ai.azure.com`
- `privatelink.cognitiveservices.azure.com`
- `privatelink.openai.azure.com`

## Ordering Model

1. Private DNS and private endpoints are created for Storage, Search, Cosmos, and Foundry account.
2. Existing project connections are created/updated.
3. Pre-caphost RBAC is assigned:
   - Storage Blob Data Contributor
   - Cosmos DB Operator
   - Search roles
4. Account capability host is created.
5. Project capability host is created.
6. Post-caphost RBAC is assigned:
   - Storage Blob Data Owner (conditioned to workspace-scoped containers)
   - Cosmos SQL role assignment

## Build And Validate

Compile all templates:

```bash
az bicep build --file infra/foundry-hosted/iac/main.bicep
az bicep build --file infra/foundry-hosted/iac/modules/foundry-project-existing-connections.bicep
az bicep build --file infra/foundry-hosted/iac/modules/add-account-capability-host.bicep
az bicep build --file infra/foundry-hosted/iac/modules/add-project-capability-host.bicep
az bicep build --file infra/foundry-hosted/iac/modules/azure-storage-account-role-assignment.bicep
az bicep build --file infra/foundry-hosted/iac/modules/cosmosdb-account-role-assignment.bicep
az bicep build --file infra/foundry-hosted/iac/modules/ai-search-role-assignments.bicep
az bicep build --file infra/foundry-hosted/iac/modules/blob-storage-container-role-assignments.bicep
az bicep build --file infra/foundry-hosted/iac/modules/cosmos-container-role-assignments.bicep
az bicep build --file infra/foundry-hosted/iac/modules/format-project-workspace-id.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-dns.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-endpoint.bicep
```

Run what-if:

```bash
az deployment group what-if \
  --resource-group <rg-name> \
  --template-file infra/foundry-hosted/iac/main.bicep \
  --parameters @infra/foundry-hosted/iac/parameters.dev.json
```

## Required Backend Settings

- `WORKFLOW_MODE=foundry_hosted`
- `FOUNDRY_HOSTED_INVOCATIONS_URL=<hosted-agent-invocations-endpoint>`
- `FOUNDRY_EVENT_CALLBACK_TOKEN=<shared-callback-token>`

## Notes

- This path assumes Foundry-only operation for this stack.
- Approve private endpoint connections and verify DNS resolution before runtime validation.
- Existing repo validation gates remain unchanged (`make test`, `make eval-backend`, `make test-e2e`, `./scripts/skills/design-review-skill.sh`).
