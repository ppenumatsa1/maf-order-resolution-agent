# Foundry-Hosted Deployment (Private VNet Baseline)

This stack provisions and deploys a Foundry-hosted agent path using `azd` + Bicep from `infra/foundry-hosted`.

Primary target region for this path is **eastus2**.

## Deployment lane

This branch keeps one hosted deployment lane:

1. `foundry-private-env` (baseline/private): private networking, private endpoints, and private-runner execution path.

## What this stack includes

- `azure.yaml` service hosts: internal `backend`, external `frontend`, and
  `azure.ai.agent` (`order-resolution-hosted`)
- `azure.yaml` deploy source path: `./agent` (generated from `backend/` by sync helper)
- Bicep orchestration in `iac/main.bicep` for:
  - Foundry account/project + model deployments
  - VNet + dedicated Container Apps subnet + agent subnet + private endpoint subnet
  - private DNS zones and private endpoints
  - NAT gateway
  - optional private runner access (runner subnet, Bastion, VM, UAMI, subscription RBAC)
  - Storage, Search, Cosmos, ACR, Log Analytics, App Insights, and PostgreSQL private endpoint/DNS
  - capability-host and connection modules

## Parameter profiles

- `iac/parameters.standard-ni.json`  
  First-provision standard profile (eastus2) with DNS links, project connections, and capability-host sequencing enabled.
- `iac/parameters.standard-ni.rerun.json`  
  Rerun/repair profile for existing environments (capability-host/connections disabled, runner VM creation disabled).
- `iac/parameters.dev.json`  
  Dev profile aligned to eastus2 defaults.
`iac/main.bicep` uses `networkMode=private` for this branch posture.

Provisioning now reads `iac/main.parameters.json`, which maps AZD environment keys (for example `NETWORK_MODE`) into Bicep parameters. The helper script `scripts/foundry/ensure_foundry_azd_defaults.sh` backfills missing keys so ad-hoc `make foundry-provision` and CI runs stay deterministic.

## Private release flow

PR validation is credential-free through
`.github/workflows/foundry-private-validation.yml`. Authenticated infrastructure
and application deployment is available only by manually dispatching
`foundry-provision.yml` or `foundry-deploy.yml`; both are protected by the
`foundry-private-env` GitHub environment and run only on
`self-hosted,foundry-private-v2` with Azure OIDC. They use the runner's retained
selected AZD environment, so do not recreate that environment or place its
database credentials in GitHub workflow configuration.
Before the first dispatch, configure the environment-scoped nonsecret OIDC and
target variables with `scripts/github/bootstrap_foundry_github_config.sh` and
enable the required GitHub environment protection rules.

The release target executes this fixed sequence:

1. local validation and private release preflight;
2. non-mutating provisioning preview, then infrastructure provisioning;
3. backend then frontend ACA deployment;
4. optional hosted-agent refresh (`FOUNDRY_REFRESH_HOSTED_AGENT=true`);
5. ACA readiness plus hosted-agent workflow proof of PostgreSQL connectivity;
6. PostgreSQL public-network lockdown and removal of the Azure-services firewall rule;
7. hosted E2E, Foundry evaluation, and correlated telemetry evidence.

```bash
make foundry-provision-preview  # no Azure resource changes
FOUNDRY_REFRESH_HOSTED_AGENT=true make foundry-release
```

The frontend is the only external ingress and proxies browser `/api` traffic to
the internal backend ACA. Lockdown consumes
`backend/.foundry/results/private-connectivity-proof.json`, produced by
`make foundry-connectivity-proof`; it cannot be authorized with a manually set
environment flag. The proof must report the same canonical FQDN as
`POSTGRES_SERVER_NAME`/`RUNTIME_DATABASE_URL`; by default it expires after one
hour. Lockdown additionally verifies that the approved `postgresqlServer`
private endpoint, private-DNS A record, and VNet link all target that server.

The latest recorded target is
`maffndpgv20722.postgres.database.azure.com`. This is an operational record,
not a template default: `make foundry-preflight` and the selected AZD
environment are authoritative if the canonical server changes.

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

- `RUNNER_LABEL` (active target: `foundry-private-v2`)
- `RUNNER_VERSION` (default: `2.328.0`)

The private runner is the only GitHub Actions host permitted to run the manual
provision/deployment lane and remains an in-VNet operator host for the local
release flow. Dispatch provision before application deployment; use the local
release flow for the full proof and PostgreSQL lockdown sequence.

## Runner readiness check

Verify GitHub sees an online runner for the required label:

```bash
REPO=ppenumatsa1/maf-order-resolution-agent \
RUNNER_LABEL=foundry-private-v2 \
./scripts/github/verify_foundry_runner_ready.sh
```

## Existing VM runbook

Run this on the active private runner VM via SSH/Bastion:

```bash
cd /path/to/repo
export GH_RUNNER_PAT=<github_pat_with_repo_workflow_scope>
export REPO=ppenumatsa1/maf-order-resolution-agent
export RUNNER_LABEL=foundry-private-v2

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
  - Ensure the active runner is configured with
    `self-hosted,foundry-private-v2`.
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

Delivery ownership, required gate mapping, and evidence handoff expectations are documented in `docs/design/engineering-operating-model.md`.
