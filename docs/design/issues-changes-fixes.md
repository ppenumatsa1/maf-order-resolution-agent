# Issues, Changes, and Fixes (Foundry Private VM Path)

Date: 2026-07-07
Scope: Foundry hosted-agent deployment from private network path in `rg-maf-ora-ni-eus-07080910`.

## Latest verification update (2026-07-08, RBAC recurrence guard)

## Latest execution update (2026-07-08, GitHub private-runner automation)

Completed:

- Added reusable GitHub Actions workflows for private-network Foundry operations:
  - `.github/workflows/foundry-provision.yml`
  - `.github/workflows/foundry-deploy.yml`
  - `.github/workflows/foundry-orchestrator.yml`
- Workflows reuse existing Make/azd targets (no duplicate deployment logic):
  - `make foundry-sync-env`
  - `make foundry-provision`
  - `make foundry-deploy`
  - `make foundry-smoke`
- Added bootstrap script to configure repository/environment variables and secrets via PAT + `gh`:
  - `scripts/github/bootstrap_foundry_github_config.sh`

Outcome:

- Private deployment path is now automatable from a self-hosted runner labeled `foundry-private` in environment `foundry-private-env`.
- Manual VM RunCommand loops are no longer required for routine provision/deploy smoke + telemetry gate execution.

Validation notes:

- Workflow YAML parsed successfully after changes.
- Full end-to-end runtime validation still depends on running the workflows in GitHub against the private runner.

## Latest execution update (2026-07-08, orchestrator dispatch blocker)

Completed:

- Successfully bootstrapped GitHub repo/environment configuration from local env sources:
  - environment: `foundry-private-env`
  - repo variables: runner label, Azure IDs, Foundry IDs/endpoints, App Insights app id
  - environment secret: `FOUNDRY_RUNTIME_ENV`
- Pushed workflow updates to branch `feature/foundry-private-network-vnet`.
- Triggered orchestrator run via branch push:
  - run id: `28970241915`
  - workflow: `Foundry Orchestrator`

Observed blocker:

- Provision job remains queued with labels `self-hosted,foundry-private`.
- Repository self-hosted runner inventory returned `total_count: 0`.

Learning:

- Workflow wiring is valid, but execution cannot start unless at least one online repo (or eligible org) runner advertises label `foundry-private`.
- Keep `workflow_dispatch` path for post-merge default-branch usage, and use branch `push` trigger for pre-merge validation.

Next unblocking step:

- Register/start the self-hosted runner for this repo with label `foundry-private`, then rerun or resume orchestrator to complete provision/deploy/smoke/telemetry gates.

## Latest execution update (2026-07-08, runner registration attempts)

Completed:

- Confirmed the orchestrator run exists and is waiting on labels:
  - run id: `28970241915`
  - queued job label requirement: `self-hosted,foundry-private`
- Confirmed repo runner inventory is empty:
  - `actions/runners -> total_count: 0`
- Added helper automation script for VM-side runner registration:
  - `scripts/github/register_vm_runner.sh`

Observed blocker:

- Azure VM command channel (`RunCommand`) is stuck in `Another execution in progress` state, which prevented reliable remote runner bootstrap from this session.

Learning:

- When remote bootstrap scripts are interrupted mid-stream, `RunCommand` can remain locked and block subsequent automation.
- Keep runner bootstrap idempotent and prefer persistent VM startup/service provisioning for the GitHub runner rather than one-off ad-hoc shell sessions.

Immediate next step to unblock:

- SSH/Bastion into `vm-maforani-runner` and run `scripts/github/register_vm_runner.sh` logic locally on the VM (or install the runner service manually) so the runner appears with label `foundry-private`.
- Once the runner is online, rerun or resume `Foundry Orchestrator` and continue with provision/deploy/smoke/telemetry validation.

## Latest execution update (2026-07-08, workflow auth mode correction)

Completed:

- Brought the GitHub self-hosted runner online with required label:
  - `vm-maforani-runner-foundry-private`
- Captured provision failure root cause from workflow logs:
  - `AADSTS70025` on `azure/login@v2` using OIDC for client `uami-maffnd-runner`.

Learning:

- For this self-hosted runner model (GitHub runner running on Azure VM with UAMI), workflow auth should use VM managed identity login:
  - `az login --identity --client-id <UAMI_CLIENT_ID>`
- OIDC federated login via `azure/login@v2` requires federated credentials configured on the Entra app/service principal and was not configured for this UAMI.

Change made:

- Updated workflows to authenticate with managed identity on-runner instead of `azure/login@v2` OIDC.

Next step:

- Re-run orchestrator and continue with provision, deploy, smoke, and telemetry gate checks.

## Latest execution update (2026-07-08, azd installer failure on full root disk)

Failure observed:

- `Foundry Orchestrator` run `28972606141` failed in provision at step `Azure/setup-azd@v2`.
- Error details:
  - `mkdir: cannot create directory '/root/.azd': No space left on device`
  - runner warning showed root disk at 100%.

Learning:

- Runner already had `azd` preinstalled (`azd version 1.27.0`).
- Installing `azd` via setup action was unnecessary and used root paths that are currently full.

Change made:

- Removed `Azure/setup-azd@v2` from provision/deploy workflows.
- Added workflow step to force writable paths on `/mnt`:
  - `HOME=/mnt/.home`
  - `AZD_CONFIG_DIR=/mnt/.azd`
  - `TMPDIR=/mnt/.tmp`
- Added `azd version` verification step.

Next step:

- Re-run orchestrator and verify full chain: provision -> deploy -> smoke -> telemetry gate.

## Latest execution update (2026-07-08, runner disk emergency remediation)

Root cause confirmed:

- VM root disk was full because Azure RunCommand extension artifacts under:
  - `/var/lib/waagent/run-command/download/*/stdout`
- Three stale `stdout` files consumed ~27 GB.

Actions taken:

- Truncated stale large files and restored root free space:
  - before: `/` 100% used
  - after: `/` 10% used (~27 GB free)
- Fixed hostname mapping so `sudo` no longer emits host-resolution warnings.
- Hardened workflows to force Azure CLI config/log path onto `/mnt` by setting:
  - `AZURE_CONFIG_DIR=/mnt/.azure`

Expected effect:

- Managed identity login and subsequent `az`/`azd` operations should no longer fail due to root disk exhaustion.

## Latest execution update (2026-07-08, foundry-sync-env path fix)

Failure observed:

- Provision progressed to `make foundry-sync-env` and failed with:
  - `cp: cannot create regular file 'agent/runtime/.env': No such file or directory`

Root cause:

- `agent/runtime` may be absent in a fresh checkout if directory is empty/untracked.

Change made:

- Updated `Makefile` target `foundry-sync-env` to create destination folders before copy:
  - `mkdir -p agent/runtime ../../backend/foundry/runtime`

Expected effect:

- Env mirroring step is robust across clean runner checkouts.

## Latest execution update (2026-07-08, workflow-level sync hardening)

Observation:

- Despite Makefile update, repeated job attempts still executed a stale `foundry-sync-env` recipe on runner and failed on `agent/runtime/.env` copy.

Change made:

- Moved env sync logic directly into `.github/workflows/foundry-provision.yml` step `Sync env into azd and runtime mirrors`.
- The step now:
  - validates runtime env file and App Insights connection string
  - creates required destination directories
  - mirrors env file to runtime locations
  - syncs all key/value pairs into azd environment

Expected effect:

- Provision no longer depends on Makefile state for env synchronization in CI.

## Latest execution update (2026-07-08, azd managed-identity auth)

Failure observed:

- Provision reached `azd provision` and failed with:
  - `ERROR: not logged in, run azd auth login to login`

Root cause:

- `az login --identity` authenticates Azure CLI, but `azd` keeps independent auth state.

Change made:

- Added explicit non-interactive azd login in both provision and deploy workflows:
  - `azd auth login --managed-identity --client-id <AZURE_CLIENT_ID> --tenant-id <AZURE_TENANT_ID> --no-prompt`

Expected effect:

- `azd provision` and `azd deploy` can execute under managed identity in CI.

## Latest execution update (2026-07-08, azd host extension requirement)

Failure observed:

- `azd provision` failed with:
  - `service host 'azure.ai.agent' for service 'order-resolution-hosted' is unsupported`
  - CI cannot auto-install extensions.

Root cause:

- Project host in `azure.yaml` requires azd extension `azure.ai.agents`.

Change made:

- Added explicit extension install/update step in both provision and deploy workflows:
  - `azd extension install azure.ai.agents` (or update if already present)

Correction:

- Initial workflow logic checked for extension presence by ID only, which is always listed even when not installed.
- Updated logic now checks `Installed Version` from `azd extension show azure.ai.agents` and then:
  - installs if `N/A`
  - upgrades if already installed

Expected effect:

- `azd` recognizes `azure.ai.agent` host in CI and proceeds with provision/deploy.

We hit a repeat of the VM-side invoke/RBAC loop in the current region.

What was validated:

- Infra remained healthy (`vm-maforani-runner`, Bastion, NAT, PE, subnet delegation all `Succeeded`).
- Public invoke from local host failed as expected (`Public access is disabled`).
- Private VM invoke reached Foundry but returned persistent `403`:
  - `Identity(object id: d77e1944-7251-41ef-be3b-883d0e503046) does not have permissions for Microsoft.CognitiveServices/accounts/AIServices/agents/write actions.`

What was tried (and still failed):

- `Foundry Project Manager`, `Foundry User`, `Foundry Owner` on account scope.
- `Foundry Owner` on project scope.
- `Cognitive Services Contributor` on account scope.
- `Owner` on resource-group scope.

Result:

- VM invoke still `403` on `agents/write`.
- App Insights remained empty for the validation window (`traces/requests/dependencies/exceptions = 0`) because no successful write/invoke occurred.
- Temporary troubleshooting role assignments were removed after testing.

### Non-repetition checklist (run before changing RBAC)

1. Identify the exact caller identity first (token `oid`), then grant roles to that exact object id only.
2. Keep invoke path consistent with the known-good runbook:
   - deploy via deploy-scoped service principal on VM,
   - invoke via the same validated principal/path.
3. Do not run iterative role-escalation loops (`User` -> `Manager` -> `Owner` -> `RG Owner`) without a principal/path change.
4. If the same `agents/write` 403 persists after one scoped RBAC update + propagation window, stop and treat as identity/path mismatch (not infra drift).
5. Record outcome in this file immediately before trying another region or principal.

### Deletion gate (do not skip)

Do not delete `rg-maf-ora-foundry` until all three are true in the same run:

- health check passes,
- private e2e invoke succeeds,
- App Insights shows fresh telemetry rows for the validation window.

## Latest verification update (2026-07-07)

Status moved from blocked to unblocked for deployment execution:

- Tried `azd config set auth.useAzCliAuth true` with UAMI login on VM.
- Result: same failure (`failed to resolve user '' access to subscription ...`).
- Switched only deploy auth mode to a deploy-scoped service principal on the same VM path.
- `azd deploy order-resolution-hosted --no-prompt` succeeded.
- Post-deploy smoke invoke succeeded from the same VM using invocations protocol.

This confirms the earlier hypothesis: the blocker was in azd managed-identity subscription/user resolution, not in IaC, private networking, or Foundry data-plane reachability.

## Latest execution update (2026-07-07, env-governance + deploy)

Completed per latest request:

- Enforced single Foundry source env at `infra/foundry-hosted/runtime/.env`.
- Updated sync workflow so derived env files are generated from that single source:
  - `infra/foundry-hosted/agent/runtime/.env`
  - `backend/foundry/runtime/.env`
- Added guard in `make foundry-sync-env` to fail fast when `APPLICATIONINSIGHTS_CONNECTION_STRING` is empty.
- Pulled live App Insights connection string from:
  - `rg-maf-ora-ni-eus-07080910` / `maffnd-mon-ktbblpk7mli2a-appi`
  - and wrote it into `infra/foundry-hosted/runtime/.env`.

Deployment/invoke verification in this pass:

- Local host deploy path (outside private VNet) failed with expected private access 403:
  - `Public access is disabled. Please configure private endpoint.`
- Private VM deploy path (`vm-maffnd-runner-iac`) succeeded:
  - `azd deploy order-resolution-hosted --no-prompt` completed.
- Private VM smoke invoke succeeded:
  - `azd ai agent invoke order-resolution-hosted '{"message":"telemetry check from private vm"}' --protocol invocations --no-prompt`
  - trace id observed: `67320660ba87656990f0703089045af0`

Current telemetry status after this deploy/invoke:

- App Insights query still returns zero rows for this trace id.
- Last 30 minutes counts remain:
  - `traces`: `0`
  - `requests`: `0`

Conclusion for this update:

- Deployment path and private-network execution are healthy.
- Env source-of-truth and App Insights connection-string propagation are now explicit and enforced.
- Remaining issue is telemetry ingestion absence after successful hosted invocation.

## Latest execution update (2026-07-07, NAT rollout + redeploy)

Completed:

- Added NAT gateway IaC to Foundry stack and attached it to `snet-agent-host`.
- Re-provisioned infra in `ora-private-uami` environment (VNet and NAT updates applied).
- Re-deployed hosted agent from private VM runner (`vm-maffnd-runner-iac`).
- Re-ran smoke invoke after deploy.

Verification:

- NAT gateway now exists in `rg-maf-ora-ni-eus-07080910`:
  - `maffnd-nat-ktbblpk7mli2a` (Succeeded)
- Agent subnet now shows NAT association:
  - `maffnd-vnet/snet-agent-host` -> `.../natGateways/maffnd-nat-ktbblpk7mli2a`
- Private-VM deploy and invoke succeeded:
  - invoke trace id: `1de2cde8e5f4fde27a24b74d7a2bf3fb`

Current remaining issue:

- App Insights ingestion still empty after NAT rollout and fresh invoke.
- Query across `traces`, `requests`, `dependencies`, and `exceptions` still returns zero rows.

Additional blocker observed during provision:

- Azure Search update intermittently fails due regional capacity (`InsufficientResourcesAvailable` in `eastus2`).
- This did not block NAT creation, VNet update, hosted agent deploy, or invoke.

## Executive summary

We moved from ad-hoc Azure commands to repeatable Bicep for private access infrastructure, added a private runner VM and Bastion path, then upgraded that VM to use a User-Assigned Managed Identity (UAMI).

Network + identity are now validated from the private VM to Foundry data-plane APIs.

Current blocker is not VNet reachability and not Foundry RBAC itself. The current blocker is `azd` identity/subscription resolution while packaging/deploying the hosted agent under managed identity context (error: `failed to resolve user '' access to subscription ...`).

## What changed (important)

### 1) Repeatable IaC for private access path

Added dedicated Bicep entrypoint and module for runner/Bastion resources:

- [infra/foundry-hosted/iac/access-path.bicep](../../infra/foundry-hosted/iac/access-path.bicep)
- [infra/foundry-hosted/iac/access-path.parameters.json](../../infra/foundry-hosted/iac/access-path.parameters.json)
- [infra/foundry-hosted/iac/modules/private-runner-access.bicep](../../infra/foundry-hosted/iac/modules/private-runner-access.bicep)

Added Make target for repeatable deployment:

- [Makefile](../../Makefile)

Target:

- `make foundry-access-path`

### 2) UAMI support for VM runner

`private-runner-access` now supports:

- UAMI creation (`createRunnerUami`, `runnerUamiName`)
- attaching UAMI to VM identity
- outputs for UAMI client/principal IDs

Resulting UAMI outputs from deployment:

- `runnerUamiClientId`: `7fcd23e4-3ca3-457b-9e53-fc63ad58bf75`
- `runnerUamiPrincipalId`: `06060201-cd7f-4df2-a5e0-785b2dcf9a16`

### 3) Foundry hosted azd config updates

- [infra/foundry-hosted/azure.yaml](../../infra/foundry-hosted/azure.yaml)

Added:

- `docker.remoteBuild: true`

Purpose:

- avoid local Docker dependency on the private VM for hosted-agent packaging.

### 4) Runbook documentation updated

- [infra/foundry-hosted/README.md](../../infra/foundry-hosted/README.md)

Added:

- access-path deploy instructions
- VM UAMI workflow
- role assignment examples
- private API validation command

## Azure resources provisioned/updated

In `rg-maf-ora-ni-eus-07080910`:

- VNet subnet: `snet-runner`
- VNet subnet: `AzureBastionSubnet`
- NSG: `nsg-maffnd-runner`
- Bastion host: `bas-maffnd`
- Bastion PIP: `pip-maffnd-bastion`
- VM: `vm-maffnd-runner-iac`
- UAMI: `uami-maffnd-runner`

## RBAC assignments applied (runner identity path)

For UAMI principal `06060201-cd7f-4df2-a5e0-785b2dcf9a16`:

- Contributor on `rg-maf-ora-ni-eus-07080910`
- Foundry Project Manager (`eadc314b-1a2d-4efa-be10-5d325db5065e`) on Foundry account scope
- Foundry User (`53ca6127-db72-4b80-b1b0-d745d6d5456d`) on Foundry account scope

## What worked (verified)

### A) Private network path is valid

From VM via UAMI login:

- `az login --identity --client-id 7fcd23e4-3ca3-457b-9e53-fc63ad58bf75`
- `az rest GET https://<foundryAccount>.services.ai.azure.com/api/projects/order-resolution/agents?api-version=v1 --resource https://ai.azure.com`

Observed response:

- HTTP success with payload structure (`data`, `has_more`, `object`).

This confirms:

- private DNS + private endpoint routing is functioning from VM
- UAMI token is accepted by Foundry data-plane for agent list read

### B) IaC convergence is repeatable

- `make foundry-access-path` succeeded after transient ARM network lock retries.

## Issues encountered and how they were handled

### 1) ARM transient lock: `AnotherOperationInProgress`

Symptom:

- access-path deploy intermittently failed on network resources.

Fix:

- rerun same declarative deployment until ARM operation completed.

Status:

- resolved.

### 2) Existing VM immutable SSH key update

Symptom:

- `PropertyChangeNotAllowed` on `linuxConfiguration.ssh.publicKeys` when reusing previously created VM.

Fix:

- switched to IaC-managed VM name (`vm-maffnd-runner-iac`) for clean lifecycle.

Status:

- resolved.

### 3) Foundry role confusion (renamed roles)

Symptom:

- 403 on agents read/publish with incomplete/incorrect role assumptions.

Fix:

- aligned to Foundry role IDs (`Foundry User`, `Foundry Project Manager`) plus scoped RG permissions.

Status:

- partially resolved; direct API access works.

### 4) `azd` host/tooling bootstrap issues on VM

Symptoms:

- unsupported host `azure.ai.agent` before extension install
- no Docker/Podman runtime

Fixes:

- azd extension installed (`azure.ai.agents`)
- set `docker.remoteBuild: true`

Status:

- resolved.

## Current blocker: why `azd deploy` still fails

Primary failing message (current):

- `failed to get tenant ID for subscription ... failed to resolve user '' access to subscription ...`

Where it fails:

- packaging step in `azd deploy` for hosted-agent service.

Why this is different from RBAC/network:

- direct UAMI call to Foundry API works from same VM and same private path.
- this indicates identity token and private routing are functional.
- failure occurs inside azd subscription/user resolution logic (identity metadata handling in this path), before or during service packaging/publish orchestration.

Interpretation:

- this is a tool-layer/auth-context issue with azd + managed identity in this environment.
- not an infrastructure drift issue and not a private endpoint reachability issue.

Current state after workaround:

- no longer blocked for deployment, provided azd uses service-principal auth in this environment.
- managed-identity path in azd remains unresolved and should be tracked as a tooling issue.

## Recommended next step (before further infra changes)

Use this decision path:

1. Keep current IaC/UAMI baseline unchanged.
2. For deployment action, use an identity mode that azd resolves reliably (service principal/OIDC), while still running from this private VM network path.
3. Continue to use UAMI for direct operational calls where possible.

This avoids unnecessary infra churn and targets the actual failing layer.

## Command record (high-value)

- Access path deploy:
  - `make foundry-access-path`
- UAMI private API validation (works):
  - `az login --identity --client-id 7fcd23e4-3ca3-457b-9e53-fc63ad58bf75`
  - `az rest --method get --uri "https://maffndaiktbblpk7mli2a.services.ai.azure.com/api/projects/order-resolution/agents?api-version=v1" --resource https://ai.azure.com`
- azd failing point:
  - `azd deploy order-resolution-hosted --no-prompt`
  - error: `failed to resolve user '' access to subscription ...`
- azd workaround path (succeeded):
  - `azd auth login --client-id <sp-app-id> --client-secret <sp-secret> --tenant-id <tenant-id>`
  - `azd deploy order-resolution-hosted --no-prompt`
  - result: deployment completed and agent endpoint published
- smoke invoke (succeeded):
  - `azd ai agent invoke order-resolution-hosted '{"message":"health check"}' --protocol invocations --no-prompt`

## Files touched in this phase

- [Makefile](../../Makefile)
- [infra/foundry-hosted/azure.yaml](../../infra/foundry-hosted/azure.yaml)
- [infra/foundry-hosted/README.md](../../infra/foundry-hosted/README.md)
- [infra/foundry-hosted/iac/access-path.bicep](../../infra/foundry-hosted/iac/access-path.bicep)
- [infra/foundry-hosted/iac/access-path.parameters.json](../../infra/foundry-hosted/iac/access-path.parameters.json)
- [infra/foundry-hosted/iac/modules/private-runner-access.bicep](../../infra/foundry-hosted/iac/modules/private-runner-access.bicep)
