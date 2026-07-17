# Foundry-Hosted Deployment (Public Dev + Private Baseline)

This stack provisions and deploys a Foundry-hosted agent path using `azd` + Bicep from `infra/foundry-hosted`.

Primary target region for this path is **eastus2**.

## Deployment lanes

Use two separate environments instead of toggling one account between modes.

1. `foundry-public-dev` (rapid iteration): public network mode and direct developer-machine deployment.
2. `foundry-private-env` (baseline/private): private networking, private endpoints, and private-runner execution path.

Current status snapshot (2026-07-15):

- Public lane: Conversations/Traces restored and confirmed for `order-resolution-hosted`.
- Private lane: deploy continues to activate, but smoke/probe can intermittently fail with upstream `HTTP 500 server_error`; ongoing diagnostics focus on hosted runtime behavior after activation.

## What this stack includes

- `azure.yaml` service host: `azure.ai.agent` (`order-resolution-hosted`)
- `azure.yaml` deploy source path: `./agent` (generated from `backend/` by sync helper)
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
- `iac/parameters.public-dev.json`  
  Public development profile (`networkMode=public`) that disables private DNS/endpoints, runner access, NAT, and network injection.

`iac/main.bicep` uses `networkMode` (`public|private`) to switch networking posture while keeping the hosted runtime path unchanged.

## Public dev local workflow

Set runtime values through azd environment and Foundry connection inputs:

- `RUNTIME_DATABASE_URL=postgresql://...@...postgres.database.azure.com:5432/<db>?sslmode=require`
- optional model config: `FOUNDRY_PROJECTS_ENDPOINT=...`, `FOUNDRY_MODEL_DEPLOYMENT_NAME=...`

Then run:

```bash
make foundry-postgres-readiness
AZURE_SUBSCRIPTION_ID="<subscription-id>" \
AZURE_RESOURCE_GROUP="rg-maf-ora-foundry-public-dev" \
FOUNDRY_AZD_ENV_NAME="foundry-public-dev" \
RUNTIME_DATABASE_URL="<postgres-url>" \
make foundry-deploy-public
```

The deploy helper configures AZD env values for public mode, provisions infra (including the runtime `CustomKeys` connection), syncs `backend/` into `infra/foundry-hosted/agent`, and deploys `order-resolution-hosted` without runtime dotenv mirroring.

Provisioning now reads `iac/main.parameters.json`, which maps AZD environment keys (for example `NETWORK_MODE`) into Bicep parameters. The helper script `scripts/foundry/ensure_foundry_azd_defaults.sh` backfills missing keys so ad-hoc `make foundry-provision` and CI runs stay deterministic.

## CI/CD workflows

- `.github/workflows/foundry-provision.yml`
- `.github/workflows/foundry-deploy.yml`
- `.github/workflows/foundry-orchestrator.yml`

The private-runner workflow path supports:

1. `azd provision`
2. `azd deploy order-resolution-hosted`
3. smoke invoke
4. hosted E2E regression (optional)

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

## Runner readiness check

Verify GitHub sees an online runner for the required label:

```bash
REPO=ppenumatsa1/maf-order-resolution-agent \
RUNNER_LABEL=foundry-private \
./scripts/github/verify_foundry_runner_ready.sh
```

## Existing VM runbook

Run this on the retained private runner VM (`vm-maffnd-runner`) via SSH/Bastion:

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

## PostgreSQL readiness helper (public dev)

`scripts/foundry/check_public_postgres_readiness.sh` validates that a candidate Azure PostgreSQL Flexible Server can be reused for public dev:

- server state is `Ready`
- public network access is enabled
- Azure-services firewall rule (`0.0.0.0`) is present
- optional `DATABASE_URL` check enforces `sslmode=require` and host match

Example:

```bash
SUBSCRIPTION_ID="<subscription-id>" \
RESOURCE_GROUP="rg-maf-ora-foundry" \
SERVER_NAME="maffndpg7930" \
DATABASE_URL="$DATABASE_URL" \
./scripts/foundry/check_public_postgres_readiness.sh
```

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

Delivery ownership, required gate mapping, and evidence handoff expectations are documented in `docs/design/engineering-operating-model.md`.
