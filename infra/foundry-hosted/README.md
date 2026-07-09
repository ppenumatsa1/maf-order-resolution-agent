# Foundry-Hosted Private VNet Deployment

This stack provisions and deploys a Foundry-hosted agent path using `azd` + Bicep from `infra/foundry-hosted`.

Primary target region for this path is **eastus2**.

## What this stack includes

- `azure.yaml` service host: `azure.ai.agent` (`order-resolution-hosted`)
- Bicep orchestration in `iac/main.bicep` for:
  - Foundry account/project + model deployments
  - VNet + agent subnet + private endpoint subnet
  - private DNS zones and private endpoints
  - NAT gateway
  - optional private runner access (runner subnet, Bastion, VM, UAMI, subscription RBAC)
  - Storage, Search, Cosmos, ACR, Log Analytics, App Insights
  - capability-host and connection modules

## Parameter profiles

- `iac/parameters.standard-ni.json`  
  First-provision standard profile (eastus2) with DNS links, project connections, and capability-host sequencing enabled.
- `iac/parameters.standard-ni.rerun.json`  
  Rerun/repair profile for existing environments (capability-host/connections disabled, runner VM creation disabled).
- `iac/parameters.dev.json`  
  Dev profile aligned to eastus2 defaults.

## CI/CD workflows

- `.github/workflows/foundry-provision.yml`
- `.github/workflows/foundry-deploy.yml`
- `.github/workflows/foundry-orchestrator.yml`

The private-runner workflow path supports:

1. `azd provision`
2. `azd deploy order-resolution-hosted`
3. smoke invoke
4. hosted E2E regression
5. App Insights telemetry gate (thread-correlated)

## Authentication mode

Workflow auth mode is controlled by repo variable `FOUNDRY_DEPLOY_AUTH_MODE`.

- `service-principal` (default): requires environment secret `AZURE_CLIENT_SECRET`
- `managed-identity`: uses VM UAMI login

Bootstrap GitHub variables/secrets with:

```bash
./scripts/github/bootstrap_foundry_github_config.sh
```

## Private runner bootstrap

Prepare and register/start the private self-hosted runner on the VM with:

```bash
./scripts/github/bootstrap_vm_runner_host.sh
./scripts/github/register_vm_runner.sh
```

Required environment variables include:

- `GH_RUNNER_PAT`
- `REPO` (owner/repo)

Optional defaults:

- `RUNNER_LABEL` (default: `foundry-private`)
- `RUNNER_VERSION` (default: `2.328.0`)

## Runner readiness check (before orchestrator dispatch)

Verify GitHub sees an online runner for the required label:

```bash
REPO=ppenumatsa1/maf-order-resolution-agent \
RUNNER_LABEL=foundry-private \
./scripts/github/verify_foundry_runner_ready.sh
```

The orchestrator workflow now runs this check as a preflight job.

## Existing VM runbook

Run this on each private runner VM (`vm-maffnd-runner`, `vm-maffnd-runner-iac`) via SSH/Bastion:

```bash
cd /path/to/repo
export GH_RUNNER_PAT=<github_pat_with_repo_workflow_scope>
export REPO=ppenumatsa1/maf-order-resolution-agent
export RUNNER_LABEL=foundry-private

./scripts/github/bootstrap_vm_runner_host.sh
./scripts/github/register_vm_runner.sh
```

Then verify from your operator host:

```bash
gh api repos/ppenumatsa1/maf-order-resolution-agent/actions/runners \
  --jq '.runners[] | {name,status,busy,labels:[.labels[].name]}'
```

## Troubleshooting

- VM is running but workflow job is queued:
  - Runner service may be stopped or runner may be offline in GitHub.
  - Run `sudo ./svc.sh status && sudo ./svc.sh start` in runner directory.
- Azure RunCommand reports `Conflict ... execution is in progress`:
  - Use direct SSH/Bastion for bootstrap/register actions.
- Runner label mismatch:
  - Ensure runner is configured with `self-hosted,foundry-private`.
- Missing tools on runner host:
  - Re-run `./scripts/github/bootstrap_vm_runner_host.sh`.

## Local validation

```bash
az bicep build --file infra/foundry-hosted/iac/main.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-runner-access.bicep
az bicep build --file infra/foundry-hosted/iac/modules/vnet.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-dns.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-endpoint.bicep
```

Repository deterministic gates remain:

- `make test`
- `make eval-backend`
- `make test-e2e`
- `./scripts/skills/design-review-skill.sh`
