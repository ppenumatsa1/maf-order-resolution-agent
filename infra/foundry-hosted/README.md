# Foundry-Hosted Self-Contained Deployment

This folder is a dedicated azd project for hosted-agent deployment where `azd up` provisions and deploys the full Foundry stack.

## What `azd up` creates

- Azure AI Foundry account and project
- Chat + embeddings model deployments
- Dedicated VNET and subnets:
  - agent subnet for capability host
  - private endpoint subnet
  - optional runner subnet for private deployment execution
  - optional `AzureBastionSubnet` for Bastion access
- Private DNS zones and VNET links
- Private endpoints for:
  - Foundry account
  - Storage
  - Cosmos DB
  - AI Search
- Storage account, Cosmos DB account, AI Search service
- Container Registry (ACR)
- Application Insights + Log Analytics
- Project connections (Storage/Cosmos/Search/AppInsights)
- Capability hosts and RBAC wiring (unless toggled off)
- Optional private execution path:
  - Bastion host + public IP
  - private Linux runner VM (no public IP)

## Entry points

- AZD config: [azure.yaml](azure.yaml)
- Infra template: [iac/main.bicep](iac/main.bicep)
- Access-path-only template: [iac/access-path.bicep](iac/access-path.bicep)
- Default parameters: [iac/parameters.dev.json](iac/parameters.dev.json)

## Repo-managed runtime env

Source-of-truth runtime variables are in-repo:

- [runtime/.env](runtime/.env) (Foundry deploy source)
- [runtime/.env.example](runtime/.env.example) (template)

Derived files (do not edit directly):

- [agent/runtime/.env](agent/runtime/.env)
- [../../backend/foundry/runtime/.env](../../backend/foundry/runtime/.env)

Both derived files are regenerated from `runtime/.env` by `make foundry-sync-env`.

Required for App Insights telemetry:

- `APPLICATIONINSIGHTS_CONNECTION_STRING`

Sync `runtime/.env` values into the active azd environment before deploy:

```bash
make foundry-sync-env
```

## Runbook

From repo root:

```bash
make foundry-up
```

Or from this folder:

```bash
azd up --no-prompt
```

Provision and deploy separately:

```bash
make foundry-sync-env
azd provision --no-prompt
azd deploy order-resolution-hosted --no-prompt
```

Show outputs/environment:

```bash
azd env get-values
azd ai agent show order-resolution-hosted --output json
```

Invoke end-to-end:

```bash
azd ai agent invoke order-resolution-hosted '{"message":"health check"}' --protocol invocations --no-prompt
azd ai agent invoke order-resolution-hosted '{"input":"health check"}' --protocol responses --no-prompt
```

## Telemetry checks

- Foundry console:
  - Agent traces and conversation runs
  - Protocol invoke history
- App Insights:
  - ensure `APPLICATIONINSIGHTS_CONNECTION_STRING` is set in `runtime/.env` and synced via `make foundry-sync-env`
  - verify trace ingestion from hosted runtime

Quick smoke from repo root:

```bash
make foundry-smoke
```

## Important toggles

See [iac/parameters.dev.json](iac/parameters.dev.json):

- `createPrivateDnsVnetLinks`
- `createPrivateEndpoints`
- `createAccountCapabilityHost`
- `createProjectCapabilityHost`
- `assignPreCaphostRbac`
- `assignPostCaphostRbac`
- `createPrivateRunnerAccess`
- `createBastionHost`
- `createRunnerVm`
- `runnerVmSshPublicKey` (must be set to create runner VM)

Example with explicit SSH key override:

```bash
azd env set RUNNER_VM_SSH_PUBLIC_KEY "$(cat ~/.ssh/id_rsa.pub)"
azd provision --no-prompt -- --parameters runnerVmSshPublicKey="$RUNNER_VM_SSH_PUBLIC_KEY"
```

Access-path-only deployment (does not provision the full Foundry stack):

```bash
az deployment group create \
  --resource-group rg-maf-ora-ni-eus-07080910 \
  --template-file iac/access-path.bicep \
  --parameters @iac/access-path.parameters.json \
  --parameters runnerVmSshPublicKey="$(cat ~/.ssh/id_rsa.pub)"
```

## VM UAMI workflow (private deployment path)

The access-path template now creates and attaches a User-Assigned Managed Identity (UAMI) to the runner VM.

After `make foundry-access-path`, note these outputs:

- `runnerUamiClientId`
- `runnerUamiPrincipalId`

Use the UAMI from inside the VM:

```bash
az login --identity --client-id <runnerUamiClientId>
az account set -s <subscriptionId>
```

Recommended RBAC for the UAMI:

- `Contributor` on `rg-maf-ora-ni-eus-07080910`
- `Foundry Project Manager` on Foundry account scope
- `Foundry User` on Foundry account scope

Example role assignment commands:

```bash
az role assignment create --assignee-object-id <runnerUamiPrincipalId> --assignee-principal-type ServicePrincipal --role Contributor --scope /subscriptions/<sub>/resourceGroups/rg-maf-ora-ni-eus-07080910
az role assignment create --assignee-object-id <runnerUamiPrincipalId> --assignee-principal-type ServicePrincipal --role eadc314b-1a2d-4efa-be10-5d325db5065e --scope /subscriptions/<sub>/resourceGroups/rg-maf-ora-ni-eus-07080910/providers/Microsoft.CognitiveServices/accounts/<foundryAccount>
az role assignment create --assignee-object-id <runnerUamiPrincipalId> --assignee-principal-type ServicePrincipal --role 53ca6127-db72-4b80-b1b0-d745d6d5456d --scope /subscriptions/<sub>/resourceGroups/rg-maf-ora-ni-eus-07080910/providers/Microsoft.CognitiveServices/accounts/<foundryAccount>
```

Validation from VM (UAMI token, private endpoint path):

```bash
az rest --method get \
  --uri "https://<foundryAccount>.services.ai.azure.com/api/projects/<project>/agents?api-version=v1" \
  --resource https://ai.azure.com
```

If `azd deploy` reports a subscription/user resolution error while using managed identity, use `azd` with delegated Azure CLI auth (`auth.useAzCliAuth=true`) and a principal that resolves subscriptions correctly in your environment, or deploy with a service principal/OIDC in CI.

If your subscription has strict subnet policy or existing account constraints, disable capability host toggles temporarily and re-enable once subnet policy is aligned.
