# Issues, Changes, and Fixes (Foundry Private VM Path)

Date: 2026-07-07
Scope: Foundry hosted-agent deployment from private network path in `rg-maf-ora-ni-eus-07080910`.

## Latest execution update (2026-07-18, private preflight + IaC wiring hardening)

### What changed

1. Removed unsupported post-creation network-injection ARM patching from workflows.
2. Added deterministic private deploy preflight in `.github/workflows/foundry-deploy.yml` that now:
   - validates OIDC deployment principal has `Foundry User` on account scope,
   - verifies Foundry private endpoint connection approval state,
   - captures runner proxy/no_proxy context,
   - probes `FOUNDRY_PROJECTS_ENDPOINT` via `curl --noproxy '*'` using the same OIDC login token,
   - exports hardened `NO_PROXY/no_proxy` for downstream deploy/smoke steps.
3. Stopped forcing `--no-state` on all provisions:
   - `.github/workflows/foundry-provision.yml` now exposes `provision_no_state` input (default `false`).
4. Wired canonical private/public control parameters into AZD/Bicep:
   - `infra/foundry-hosted/iac/main.parameters.json` now maps capability-host, RBAC, private endpoint/DNS/NAT/runner, and injection parameters.
   - workflow env seeding now uses canonical uppercase keys (`CREATE_*`, `ASSIGN_*`, `MANAGE_*`).
   - `scripts/foundry/ensure_foundry_azd_defaults.sh` now seeds these canonical keys (and keeps legacy lowercase aliases for transitional compatibility).
5. Updated Foundry account injection shape in IaC:
   - `infra/foundry-hosted/iac/main.bicep` now uses `Microsoft.CognitiveServices/accounts@2025-04-01-preview`,
   - includes `useMicrosoftManagedNetwork: false` in `networkInjections`,
   - outputs `foundryNetworkInjectionCount` for deploy-time validation evidence.

### Validation executed

- `bash -n scripts/foundry/ensure_foundry_azd_defaults.sh`
- `jq empty infra/foundry-hosted/iac/main.parameters.json`
- `az bicep build --file infra/foundry-hosted/iac/main.bicep`

### Next execution step

Run private `foundry-provision` + `foundry-deploy` with the new preflight active to capture whether deploy-path `403 Traffic is not from an approved private endpoint` is now eliminated (or blocked with precise preflight evidence before deploy).

### Follow-up after first rerun

- Private reprovision run `29625658341` failed during ARM apply with role-assignment authorization errors on Search/Storage/Cosmos scopes (`Microsoft.Authorization/roleAssignments/write`) for the OIDC deployment principal.
- To prevent repeated mid-deployment failures, workflows were hardened to:
  - auto-disable capability-host RBAC toggles when the deployment principal lacks `User Access Administrator`/`Owner` at resource-group scope,
  - keep private preflight authorization acceptance as `Foundry User` **or** `Contributor/Owner` at resource-group scope,
  - emit explicit warnings when `Foundry User` cannot be auto-assigned because elevated RBAC is missing.
- Rerun results after those changes:
  - private provision rerun `29625774875`: **success**,
  - private deploy rerun `29625850910`: **failed at new private preflight** before deploy.
- Preflight evidence from `29625850910`:
  - runner has no proxy env values (`http_proxy/https_proxy/NO_PROXY` empty),
  - DNS resolves Foundry endpoint to private IP (`10.90.2.8`, `*.privatelink.services.ai.azure.com`),
  - account private endpoint connection validation passes,
  - authenticated data-plane call still returns:
    - HTTP `403`
    - `{"error":{"code":"403","message":"Traffic is not from an approved private endpoint."}}`
- This confirms the original deploy blocker remains, but is now deterministically surfaced before `azd deploy` instead of failing later in deploy internals.
- Additional parity check against Microsoft sample (`15-private-network-standard-agent-setup`) found one critical networking delta:
  - sample Foundry account uses `networkAcls.defaultAction='Deny'` with `virtualNetworkRules: []` (no subnet allowlist), plus private endpoints and network injection;
  - our template was still enforcing `virtualNetworkRules` to the agent subnet only.
- Applied parity fix in `infra/foundry-hosted/iac/main.bicep`:
  - private mode now sets `networkAcls` to `defaultAction: 'Deny'`, `virtualNetworkRules: []`, `ipRules: []`, `bypass: 'AzureServices'`.
  - network isolation remains enforced by private endpoints + network injection, matching the sample design.
- Validation after parity fix:
  - private provision `29626207072`: **success**,
  - private deploy `29626295212`: still **fails preflight** with authenticated `403 Traffic is not from an approved private endpoint`.
- Latest preflight evidence (`29626295212`) still shows:
  - `maffndaiktbblpk7mli2a.services.ai.azure.com -> 10.90.2.8` via private DNS,
  - private endpoint connection state approved,
  - no proxy env variables in runner process,
  - direct `curl --noproxy '*'` with OIDC token returns `403` from Foundry data plane.
- Conclusion: Foundry account networking template parity improved, but private endpoint admission rejection persists and remains the gating blocker before deploy/smoke/e2e.

## Latest execution update (2026-07-18, private smoke 500 RCA and network injection repair)

### What failed

Private deploy smoke failed with a non-retryable internal error (not `session_not_ready`) after introducing explicit private model-path parity:

- `ERROR: agent error (): An internal server error occurred.`

### Root cause

Hosted runtime started and passed `/readiness`, but model calls failed from inside the private hosted container:

- `POST .../api/projects/order-resolution/openai/v1/responses -> HTTP 403 Forbidden`
- `Public access is disabled. Please configure private endpoint.`

The private Foundry account had `publicNetworkAccess=Disabled` and private DNS/endpoints configured, but `properties.networkInjections` was `null`, so model-path traffic resolved to blocked public access instead of the private injected path.

### Fixes applied

1. Added an explicit private network-injection enforcement step in:
   - `.github/workflows/foundry-provision.yml`
   - `.github/workflows/foundry-deploy.yml`
2. For private profile runs, workflows now:
   - resolve account + subnet from account network ACLs,
   - patch `properties.networkInjections=[{scenario: agent, subnetArmId: ...}]` via ARM update,
   - verify injection is persisted before proceeding.
3. Manual verification command confirmed the account now reports injected private agent subnet.

### Follow-up in progress

1. Microsoft documentation review confirms hosted-agent limitation: virtual network
   injection must be configured when the Foundry account is first created; adding it to
   an existing hosted account is not supported.
2. Current remediation path is in-flight:
   - deleted private Foundry project/account in `rg-maf-ora-foundry`,
   - dispatched private reprovision to recreate the account with private network
     injection from creation time,
   - pending re-deploy + smoke + hosted E2E validation on the recreated account.
3. First reprovision attempt (`29623675722`) reported `SUCCESS: There are no changes to provision`
   after account deletion because AZD state comparison skipped drifted resources. Follow-up
   fix applied:
   - `Makefile` `foundry-provision` now supports `FOUNDRY_PROVISION_NO_STATE=1` to pass
     `azd provision --no-state`.
   - `.github/workflows/foundry-provision.yml` now runs private reprovision with
     `FOUNDRY_PROVISION_NO_STATE=1` to force missing-resource recreation.
4. Next reprovision attempt (`29623747234`) failed during ARM validation because the deleted
   Foundry account name was still soft-deleted and blocking redeploy:
   - `ERROR: A soft-deleted resource with this name exists and is blocking deployment.`
   - executed explicit purge with location:
     `az cognitiveservices account purge -g rg-maf-ora-foundry -n maffndaiktbblpk7mli2a -l eastus2`
   - private reprovision rerun is now in progress.
5. Reprovision rerun (`29623827564`) recreated Foundry account/project/deployments but failed on
   stale disconnected Foundry private endpoint:
   - `PrivateEndpointCannotBeUpdatedInDisconnectedState` on
     `maffnd-foundry-pe-ktbblpk7mli2a`
   - remediation executed: deleted disconnected private endpoint to allow clean recreate.
6. Provision config now explicitly enables capability-host path in private reprovision
   (account + project capability hosts and pre/post caphost RBAC) to align private hosted
   model access with network-secured routing expectations.
7. Private reprovision with capability-host settings succeeded (`29624207214`); private
   deploy + smoke + hosted E2E run has been dispatched for validation.
8. Private deploy validation runs `29624319214` and `29624435798` both failed before smoke at
   `azd deploy` agent existence check with the same data-plane denial:
   - `403 Forbidden`
   - `Traffic is not from an approved private endpoint.`
   This indicates private runner traffic still fails Foundry private-endpoint admission for
   project data-plane calls even after account/project recreation and successful infra
   reprovision.
9. VM identity check:
   - `vm-maffnd-runner` currently has **system-assigned MI only** (`f8aa29aa-b0df-4693-9012-172273b03145`);
     no user-assigned identity is attached.
   - no RBAC role assignments were found for that VM system-assigned principal on the new
     Foundry account/project scopes.
   - deploy workflow is using federated `azure/login` service principals, so this does not
     fully explain the current `Traffic is not from an approved private endpoint` denial, but
     confirms VM MI/UAMI is not provisioned for direct Foundry access.

## Latest execution update (2026-07-17, design-review bootstrap + private/public trace parity alignment)

### What failed

1. CI `Deterministic design-review gate` failed in Playwright stage due missing local prereqs in job context:
   - missing `backend/.env` for docker-backed local bootstrap
   - missing Playwright npm/binary setup.
2. Private trace topology remained flatter than public because private lane lacked explicit `FOUNDRY_MODEL_DEPLOYMENT_NAME` env seeding.

### Fixes applied

1. Updated `scripts/skills/design-review-skill.sh` to bootstrap E2E prerequisites before running `make test-e2e`:
   - copy `backend/.env.example` -> `backend/.env` when absent,
   - install Playwright npm dependencies when absent,
   - install Chromium runtime when Playwright cache is absent.
2. Updated Foundry workflows to seed canonical model/project env for private/public parity:
   - `.github/workflows/foundry-deploy.yml`
     - set `FOUNDRY_PROJECTS_ENDPOINT` from resolved project endpoint
     - set `FOUNDRY_MODEL_DEPLOYMENT_NAME` (default `gpt-4o-mini` when variable is unset)
   - `.github/workflows/foundry-provision.yml`
     - set `FOUNDRY_MODEL_DEPLOYMENT_NAME` (default `gpt-4o-mini`)
     - seed `FOUNDRY_PROJECTS_ENDPOINT` from workflow environment variables when available.

## Latest execution update (2026-07-17, private smoke/e2e restored from GH runner)

### What failed

Private Foundry deploys kept failing smoke with `HTTP 424 session_not_ready`, even after
deploy succeeded.

### Root cause

Container startup was failing in readiness due to PostgreSQL auth mismatch:

- repeated `password authentication failed for user "pgadmin"`
- startup traceback at `app/core/container.py -> postgres_db.ensure_schema()`
- terminal error `psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec`

This confirms `session_not_ready` was a downstream readiness symptom, not a model/runtime protocol issue.

### Fixes applied

1. Added hosted diagnostics capture in `.github/workflows/foundry-deploy.yml`:
   - on smoke failure, collect `azd ai agent show` and `azd ai agent monitor` logs.
2. Hardened deploy/provision DB env setup in workflows:
   - reject masked/localhost DB URLs
   - derive runtime DB URL from current Azure PostgreSQL server + admin secret when needed.
3. Rotated PostgreSQL admin password on `maffndpg7930` and updated GitHub environment secrets:
   - `foundry-private-env`: `POSTGRES_ADMIN_PASSWORD`, `FOUNDRY_DATABASE_URL`
   - `foundry-public-env`: `POSTGRES_ADMIN_PASSWORD`, `FOUNDRY_DATABASE_URL`
4. Re-ran private deploy-only orchestrator from branch `feature/foundry-private-network-vnet`.

### Validation evidence

- Failed diagnostic run (captured root cause): `29616784230`
- Successful private recovery run: `29617103198`
  - `deploy_only / Deploy Foundry hosted agent`: success
  - smoke validation: success
  - hosted E2E validation: success

## Latest execution update (2026-07-17, single-source hosted deploy path adopted)

### What changed

To eliminate backend/staged-folder drift, hosted deploys now use an automated sync
from `backend/` to the deploy folder before `azd deploy`.

### Changes applied

1. Kept `infra/foundry-hosted/azure.yaml` service project as `./agent` (required by
   `azd`: service paths cannot include `..`).
2. Removed copy-based staging steps from:
   - `scripts/foundry/deploy_public_dev.sh`
   - `.github/workflows/foundry-deploy.yml`
   - `.github/workflows/foundry-provision.yml`
3. Added automated sync helper `scripts/foundry/sync_hosted_source.sh` and wired it
   into `make foundry-deploy` so the deploy payload is refreshed from `backend/` every
   time.
4. Added deploy guardrails:
   - source-file checks (`backend/agent.yaml`, `backend/foundry/main.py`) in deploy
     script and workflows
   - `make foundry-deploy` now verifies active agent metadata after deploy via
     `azd ai agent show`.
5. Updated readmes to document the sync-based deploy source path.

## Latest execution update (2026-07-17, stage hierarchy visibility restored on public-dev2)

### What failed

Foundry traces for some recent conversations still looked flat/generic even after
workflow stage span naming updates were merged.

### Root cause

The hosted deployment source is `infra/foundry-hosted/agent` (`azure.yaml` uses
`project: ./agent`). The latest backend workflow changes were present in
`backend/app/maf/workflows/order_resolution.py` but had not been re-staged into
`infra/foundry-hosted/agent` before deploy, so the active hosted version still ran the
older package.

### Fixes applied

1. Re-staged the hosted deployment source from `backend/` into
   `infra/foundry-hosted/agent`.
2. Redeployed to the existing public environment `foundry-public-dev2`
   (`rg-maf-ora-foundry-public-dev2`) as active hosted version **34**.
3. Re-ran both workflow paths on the same deployed version:
   - no-HITL (`ORD-1001`)
   - HITL + approve resume (`ORD-1009` + `Approve`).

### Validation evidence

- No-HITL conversation:
  - `conv_37db5738471e938f009iDLANKQ6qyIl4Bgch5kZws06LUnryXi`
  - status: `completed`
  - stages/events include: `triage` -> `policy_retrieval` -> `resolution` -> `workflow.output`
- HITL conversation:
  - `conv_d6712704932b2dd100qkldJm1g8mgQHvoXKGTqMidtBsbp9HOM`
  - status: `waiting_approval` then `completed` after approve
  - stages/events include: `triage` -> `policy_retrieval` -> `resolution` ->
    `checkpoint.created` -> `hitl.request` -> `hitl.response` -> `workflow.output`
- Public active deploy version:
  - `order-resolution-hosted` version `34`

## Latest execution update (2026-07-17, public deploy recovered; smoke + hosted E2E passing)

### What failed

Public `foundry-public-dev` deployments initially activated, but hosted smoke returned
`session_not_ready` (`HTTP 424`) and no request reached workflow execution.

### Root cause

1. `AZURE_AI_PROJECT_ID`/`FOUNDRY_PROJECT_ENDPOINT` were missing in the selected AZD
   environment, causing early deploy failures.
2. Hosted runtime readiness then failed on database startup:
   - first with invalid/masked `DATABASE_URL` values propagated into the env (literal
     masked prefix produced `invalid connection option`), and
   - with stale Postgres credentials (`password authentication failed for user "pgadmin"`).
3. `session_not_ready` was a downstream symptom of container startup failing at
   `postgres_db.ensure_schema()`.

### Fixes applied

- Selected `foundry-public-dev` AZD environment and set:
  - `AZURE_AI_PROJECT_ID`
  - `FOUNDRY_PROJECT_ENDPOINT` / `FOUNDRY_PROJECTS_ENDPOINT`
  - `FOUNDRY_MODEL_DEPLOYMENT_NAME`
- Rotated public PostgreSQL admin password on server `maffndpg7930`.
- Rewrote runtime DB envs with an explicit valid URL:
  - `DATABASE_URL`
  - `RUNTIME_DATABASE_URL`
  - `FOUNDRY_RUNTIME_DATABASE_URL`
- Redeployed hosted agent after env correction.

### Public evidence captured

- Deploy succeeded to active public hosted version **4**.
- Smoke succeeded with HITL-waiting response and full expected event chain:
  - conversation: `conv_a79a1a4bf2ebc96300VTzsnsqVlmhtp5rBAcizkwioNud4SUAQ`
  - trace id: `3d55c2063dd8702021f31ffe3416508b`
  - includes `policy_retrieval` started/completed stages and `hitl.request`.
- Hosted Responses E2E script passed:
  - conversations:
    - `conv_3d51b53241332b8800KqGBxirCuBNKJHxvEa3OMD0in21HJAzC`
    - `conv_98ed6beaa836501c00nf0m4N5ddDBjB9o1rTxRe1xPbFwOVqdH`
    - `conv_dbc83201dfe48c3500nDIgsDBbP8hQaNQJcpurfFDpCpfizgXJ`

### Telemetry note

- App Insights query checks against known app IDs in this env currently return zero
  rows; runtime functionality is recovered, but telemetry evidence remains pending
  follow-up in this lane.

## Latest execution update (2026-07-17, corrected to existing public-dev2 Foundry project)

### Correction

Deployment target was corrected back to the existing public project in:

- resource group: `rg-maf-ora-foundry-public-dev2`
- Foundry account: `maffndaibfscpfhjr7sp4`
- project: `order-resolution-public-dev`

### Actions

1. Selected AZD env `foundry-public-dev2`.
2. Repaired env drift in that environment:
   - set canonical `FOUNDRY_PROJECTS_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT_NAME`,
   - set `FOUNDRY_DEPLOYMENT_PROFILE=public`,
   - corrected runtime DB URL values.
3. Redeployed hosted agent to **version 33** in `public-dev2`.
4. Re-ran smoke and hosted E2E on that existing target.

### Evidence on existing target

- Smoke conversation:
  - `conv_72b1df3023f100a400F6vrfYrpbsGK7Vxgk4oUHztX7I84aLKI`
  - trace id: `73550ae478ee1087e7495fb0978e02cc`
  - status: `waiting_approval` with expected `hitl.request`.
- Hosted E2E passed:
  - `conv_5044cad9fb88ee1700gTGKRUW4okvaEjLfMmzqU9r2EKYqZmer`
  - `conv_0d350cbfa28eaeda00nYOK2Sz5Bz4dHIhPIfrVoyfHVAI4EFEE`
  - `conv_7d1d658f23cb109200b8GO3DCOc4hNuzrOOdpplvGN6bBgvj7B`
- Session proof for version 33:
  - `b7cecfbea4058bc1094abaa9c4afa8b46e8ca2b04997e216b37513e3472959f`
- App Insights (`b29359cf-47cd-4bc1-b962-246f7f4da5c0`, last 60m):
  - `dependency=30`, `trace=133`, `exception=4`.

## Latest execution update (2026-07-15, public Conversations/Transactions restored; private regression under investigation)

### What was the issue

`order-resolution-hosted` intermittently produced successful smoke/E2E output but did
not consistently produce Foundry portal-visible Conversations/Transactions in the
public lane.

### Confirmed root cause and fix (public)

1. Hosted runtime had an instrumentation incompatibility when
   `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` was present for this path.
2. That flag introduced a stream wrapper path incompatible with the
   `FoundryChatClient` parsing contract used by the hosted workflow runtime.
3. Removing the flag from `backend/agent.yaml` restored stable Foundry model-stream
   behavior and Transactions visibility.
4. Deploy/probe checks were tightened to assert semantic trace evidence rather than
   relying only on generic correlated telemetry.

Public evidence captured in this cycle:

- Workflow run `29378272598` succeeded.
- Active public version `32` served Responses traffic with Foundry model mode.
- Portal screenshots and live checks confirmed Conversations/Transactions are visible.

### Current private status (open)

Private deploy still activates successfully, but smoke/probe can return upstream
`HTTP 500 server_error` afterward. Current failing evidence set includes:

- Deploy failures at smoke gate: `29416532488`, `29416754351`, `29417048134`, `29417630436`
- Probe failures: `29416834894`, `29416963146`, `29417223018`, `29417301347`, `29417441836`
- Header evidence repeatedly resolves private hosted version `56`

Next action remains runner/deploy-lane traceback capture from the activated private
container to isolate the post-activation runtime fault.

## Latest execution update (2026-07-14, Foundry Conversations root cause fixed)

The clean Microsoft Agent Framework hosted sample proved that the public Foundry
project, Application Insights connection, hosted runtime, and Conversations portal
index were healthy. The remaining fault was specific to the order-resolution hosted
package and manifest.

Confirmed root-cause chain:

1. The deploy workflow set `FOUNDRY_DEPLOYMENT_PROFILE=public` in the AZD environment,
   but `backend/agent.yaml` did not declare that variable for hosted-container
   substitution.
2. The public runtime therefore received no profile and selected
   `InMemoryResponseProvider`. Deploy, smoke, hosted E2E, and custom App Insights
   telemetry still passed, but no response was persisted for the Foundry Conversations
   index.
3. After fixing profile propagation, the pinned
   `azure-ai-agentserver-responses==1.0.0b7` activated `FoundryStorageProvider` but sent
   obsolete user/chat isolation headers. The current protocol 2.0 storage service
   requires the platform `x-agent-foundry-call-id`, so every new conversation history
   lookup returned HTTP 404.
4. The working Microsoft sample used `azure-ai-agentserver-responses==1.0.0b8`, which
   forwards the Foundry call ID. Upgrading to `1.0.0b8` resolved the storage lookup and
   response persistence failures.

Changes:

- Added `FOUNDRY_DEPLOYMENT_PROFILE` to `backend/agent.yaml`.
- Upgraded `azure-ai-agentserver-responses` from `1.0.0b7` to `1.0.0b8`.
- Added hosted store-selection regression tests.
- Added a deployment gate that verifies the live provider and, for public deployments,
  requires a successful Foundry response-storage write.

Final validation evidence on commit `3cf3272`:

- **Public run `29373917392`: success**
  - `storage_provider=FoundryStorageProvider`
  - `GET .../storage/history/item_ids` -> HTTP 200 with `has_call_id=True`
  - `POST .../storage/responses` -> HTTP 201 with `has_call_id=True`
  - smoke conversation: `conv_10f4367e52cce11700N6EfzlnUCTMUAKs7Xk8zcfLWanmJ7lNt`
  - hosted E2E: passed
  - App Insights telemetry gate: passed
- **Private run `29374068390`: success**
  - `storage_provider=InMemoryResponseProvider`
  - smoke + hosted E2E + App Insights telemetry gate: passed

Corrected validation learning:

- Successful Responses output and correlated custom App Insights spans do not prove
  Foundry Conversations persistence.
- Public validation must assert the selected `FoundryStorageProvider` and a successful
  `POST .../storage/responses`; otherwise an in-memory response path can produce a
  false-positive green deployment.

## Latest execution update (2026-07-14, profile-gated response store validated on both lanes)

Completed in this pass:

- Re-ran full deploy validation on latest code commit `bd21077` after the Foundry runtime response-store profile gating:
  - public profile uses platform-backed response storage,
  - private profile keeps in-memory response storage to avoid private storage public-access dependency failures.
- Confirmed full deploy + smoke + hosted E2E + telemetry gate success on both profiles at the same commit.

Validation evidence:

- **Private profile run**: `29364985311` (success)
  - deploy: success
  - smoke: low-risk + high-risk verified
  - hosted E2E: passed
  - telemetry gate (App Insights): passed
- **Public profile run**: `29365152738` (success)
  - deploy: success
  - smoke: low-risk + high-risk verified
  - hosted E2E: passed
  - telemetry gate (App Insights): passed

Learning:

1. The profile-gated response-store strategy removes the private bootstrap/storage contention while preserving public lane conversation persistence intent.
2. With this gating, no regression was observed in deploy, smoke, hosted E2E, or App Insights telemetry gates across either lane.

## Latest execution update (2026-07-14, public+private parity restored)

Completed in this pass:

- Fixed the public Foundry lane and re-validated both deployment profiles on latest code.
- Rotated shared Azure PostgreSQL admin password on `maffndpg7930` and synchronized GitHub environment secrets:
  - `FOUNDRY_DATABASE_URL` in `foundry-private-env`
  - `FOUNDRY_DATABASE_URL` in `foundry-public-env`
  - `POSTGRES_ADMIN_PASSWORD` in both environments
- Added missing telemetry query RBAC for runner identity (`uami-maffnd-runner`) on public resources:
  - `Reader` + `Monitoring Reader` on `rg-maf-ora-foundry-public-dev2`
  - `Monitoring Reader` + `Application Insights Component Contributor` on public App Insights component
  - `Log Analytics Reader` on public Log Analytics workspace

Validation evidence:

- **Private profile run**: `29351349372` (success)
  - smoke: low-risk + high-risk verified
  - E2E: passed
  - telemetry: `telemetry_count=4` (attempt 1/20), gate passed
- **Public profile run**: `29351940898` (success)
  - smoke: low-risk + high-risk verified
  - E2E: passed
  - telemetry: `telemetry_count=19` (attempt 1/20), gate passed

Root-cause closure:

1. Public smoke `session_not_ready` was caused by PostgreSQL credential drift (`password authentication failed for user "pgadmin"`).
2. After DB credential fix, public telemetry gate still failed due runner identity query permissions (`InsufficientAccessError`) on App Insights/Log Analytics.
3. With DB secret alignment + telemetry RBAC grants, both public and private deploy+smoke+E2E+telemetry paths are now green.

## Latest execution update (2026-07-14, strict Responses-native conversation mode)

Completed in this pass:

- Implemented a Foundry-only runtime change in `backend/foundry/main.py` to enforce strict Responses-native continuity:
  - use `conversation` / `conversation.id` and `previous_response_id` for conversation identity,
  - removed metadata/session/thread fallback from hosted conversation resolution.
- Updated hosted-entrypoint tests in `backend/tests/test_foundry_hosted.py` for strict mode behavior.
- Validation on strict commit `7af8b1a`:
  - private profile run `29360090478`: success (deploy + smoke + hosted E2E + telemetry gate)
  - public profile run `29361070244`: success (deploy + smoke + hosted E2E + telemetry gate)

Evidence highlights:

- Private telemetry gate: `telemetry_count=19` for thread `conv_2240b1de1ca027cb00fpdCwnUhFM1ldKh7uurWqUlBVxyVdYSW`.
- Public telemetry gate: `telemetry_count=19` for thread `conv_a6498cad6b64d427002oBZ5B4GbvaQ2p2shmNrTxYUZGdcz02z`.

## Latest execution update (2026-07-14, private VNet lane fully green)

Completed in this pass:

- Verified the private orchestrator run triggered after DB credential rotation:
  - run: `29348257181`
  - URL: `https://github.com/ppenumatsa1/maf-order-resolution-agent/actions/runs/29348257181`
- Confirmed full private lane success in one run:
  - `runner_preflight`: success
  - `provision / Provision Foundry Infra`: success
  - `deploy_after_provision / Deploy Foundry Hosted Agent`: success
  - smoke step: success (`Low-risk smoke path verified`, `High-risk smoke path verified`)
  - hosted E2E regression: success
  - telemetry gate (App Insights): success
- Captured smoke/telemetry correlation evidence:
  - smoke thread id: `conv_ad53788b0ff694bb00FQWSM6LAP7veWs3FNkqDaofZvh1kG1Kb`
  - telemetry gate: `telemetry_count=6` on attempt `1/20`, `Telemetry gate passed`

Root-cause learning (private `session_not_ready`):

1. `session_not_ready` was a downstream symptom, not the primary failure.
2. Primary startup failures progressed through two concrete causes:
   - incorrect loopback DB target (`127.0.0.1:5432`) from env propagation mismatch,
   - then PostgreSQL auth mismatch (`password authentication failed for user "pgadmin"`).
3. Durable fix was the combination of:
   - stricter deploy/provision DB env validation + propagation,
   - hosted startup DB URL override safeguards in `backend/foundry/main.py`,
   - aligned hosted env mapping in `backend/agent.yaml`,
   - rotated PostgreSQL credentials + matching GitHub environment secret refresh.

## Latest execution update (2026-07-13, public Foundry dev lane validated)

Completed in this pass:

- Implemented and exercised the dedicated public development lane in `rg-maf-ora-foundry-public-dev2` with AZD env `foundry-public-dev2`.
- Kept the Responses-native hosted runtime path and fixed cloud HITL resume parsing so approval messages in hosted Responses sessions now resolve pending checkpoints and emit `hitl.response`.
- Hardened local/public deploy and validation scripts:
  - stage runtime env before packaging,
  - mirror runtime env into staged `agent/runtime/.env` and `agent/app/runtime.env`,
  - make hosted E2E resilient to transient transport resets after successful payload emission,
  - force smoke runs to use new conversation/session for deterministic results.

Cloud validation evidence:

- Hosted agent deployed successfully through version `15`.
- Public smoke (`make foundry-smoke`) now deterministically returns HITL events with fresh session/conversation.
- Hosted E2E passed end-to-end:
  - `Foundry Responses hosted E2E passed for conversations: conv_1de57237154b1e6300295UscQz11cAGxsCLW3LZZY5mKiquNJG, conv_e2fe883a6e54341800Byg2FaGS7NGf5AahmusMrZVS4xR8vfkN, conv_78f9083a7b23dfc600LVkxbJS87OACKIvV0ToKysHFYlV1RGQX`
- Application Insights telemetry verified in the public-dev App Insights component:
  - appId: `b29359cf-47cd-4bc1-b962-246f7f4da5c0`
  - correlated thread query for `conv_e2fe883a6e54341800Byg2FaGS7NGf5AahmusMrZVS4xR8vfkN` returned non-zero telemetry (`total=26`, `dependencies=16`, `traces=10`, `exceptions=0`).

Local validation note:

- Repository-local gates pass when run against the local Docker PostgreSQL endpoint:
  - `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable make test`
  - `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable make eval-backend`
  - `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable make test-e2e`
  - `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable ./scripts/skills/design-review-skill.sh`

## Latest execution update (2026-07-12, shared workflow Responses cutover + docs sync)

Completed in this pass:

- Cut over to one shared MAF business workflow path and removed app-side dual runtime switching.
- Replaced hosted invocations adapter flow with Responses-first hosted entrypoint (`backend/foundry/main.py`) that composes the same shared workflow.
- Removed legacy Foundry proxy/adapter routes and modules (`/api/foundry*`, `backend/app/foundry/*`) and aligned hosted packaging/manifests to `backend/` roots.
- Added hosted Responses behavior coverage and follow-up explanation coverage in backend tests.
- Synchronized architecture/runtime documentation to match the cutover:
  - `README.md`
  - `backend/README.md`
  - `docs/design/userflow.md`
  - `docs/design/hitl-approval-conditions.md`
  - `.github/copilot-instructions.md`
  - `agents.md`

Validation evidence:

- `make test` passed.
- `make eval-backend` passed.
- `make test-e2e` passed.
- `./scripts/skills/design-review-skill.sh` passed.

## Latest execution update (2026-07-12, private deployment + hosted evidence pass)

Completed in this pass:

- Ran Foundry orchestrator on `feature/foundry-private-network-vnet`:
  - run: `29205980252`
  - URL: `https://github.com/ppenumatsa1/maf-order-resolution-agent/actions/runs/29205980252`
- Confirmed all required cloud jobs passed:
  - `runner_preflight`: success
  - `provision / Provision Foundry Infra`: success
  - `deploy_after_provision / Deploy Foundry Hosted Agent`: success
- Captured hosted execution evidence from the successful run:
  - smoke thread id: `foundry-smoke-29205980252-1`
  - hosted E2E: `Foundry hosted E2E passed for thread base: foundry-e2e-29205980252-1`
  - telemetry gate: `telemetry_count=1` (attempt `1/20`), `Telemetry gate passed`

Issue fixed during run:

- Initial run `29205863827` failed at `actions/checkout@v4` on private runner with
  workspace cleanup `EACCES` (`None/.cache` root-owned path).
- Fixed by adding a pre-checkout workspace permission reset and cleanup step in:
  - `.github/workflows/foundry-provision.yml`
  - `.github/workflows/foundry-deploy.yml`
- Re-run from commit `96f9371` completed successfully.

## Latest execution update (2026-07-09, runner readiness hardening)

## Latest execution update (2026-07-09, EastUS2 provision hardening + remaining platform blocker)

Completed in this pass:

- Stabilized provision behavior for shared private-runner VNet:
  - `infra/foundry-hosted/iac/main.bicep`
    - always keeps runner and Bastion subnets declared in VNet module input to avoid subnet-pruning drift on reruns.
  - `infra/foundry-hosted/iac/modules/vnet.bicep`
    - added runner subnet NAT gateway attachment support.
    - added `Microsoft.CognitiveServices` service endpoint on `snet-agent-host` for Foundry account network ACL requirements.
  - `infra/foundry-hosted/iac/main.bicep`
    - added Foundry account `networkAcls` (default deny + agent subnet VNet rule) required by current account API behavior.
- Hardened provision workflow env seeding:
  - `.github/workflows/foundry-provision.yml`
  - pinned rerun-safe flags for shared environments (`createPrivateRunnerAccess=true`, `createRunnerVm=false`).
- Recovered runner connectivity after failed provisions removed subnet outbound:
  - reattached NAT gateway to `snet-runner` (`nat-maffnd-runner`)
  - restarted runner service on `vm-maffnd-runner`
  - confirmed runner returned online (`vm-maforani-runner-foundry-private`).

Validation evidence:

- Full orchestrator attempts:
  - `29037073536`
  - `29039975664`
  - `29040220564`
- Deploy-only orchestrator passed end-to-end on private runner:
  - `29040570942` (`deploy_only / Deploy Foundry Hosted Agent` success)
- Latest ARM deployment failure narrowed to one remaining resource:
  - deployment: `foundry-private-env-1783621283`
  - failed operation:
    - target: `Microsoft.Search/searchServices/maffndsrchktbblpk7mli2a`
    - code: `InsufficientResourcesAvailable`
    - message: EastUS2 currently out of capacity for new Search service provisioning.
- Previous blockers are no longer the top failure in latest run:
  - no more `InUseSubnetCannotBeDeleted` on Bastion/runner/private-endpoint subnets.
  - no more Foundry account `NetworkAcls is required` / missing service endpoint error.

Current hard blocker:

- EastUS2 Search service capacity exhaustion (`InsufficientResourcesAvailable`) is the only remaining provision failure gate in current runs.
- Because provision fails at this platform gate, downstream `deploy_after_provision` is skipped even though deploy-only flow previously passed.

## Latest execution update (2026-07-09, full-cloud closure achieved)

Completed in this pass:

- Implemented deterministic Search capacity fallback while keeping Foundry private VNet in East US 2:
  - `infra/foundry-hosted/iac/main.bicep`
    - added `aiSearchLocation` parameter and defaulted Search provisioning region to `eastus`.
  - `.github/workflows/foundry-provision.yml`
    - seeds `aiSearchLocation` in azd env for provision workflow runs.
- Re-ran full orchestrator after fallback and captured a fully passing run:
  - `29041614595`
  - `runner_preflight`: success
  - `provision / Provision Foundry Infra`: success
  - `deploy_after_provision / Deploy Foundry Hosted Agent`: success

End-to-end evidence from passing run `29041614595`:

- Hosted agent deploy succeeded with endpoint outputs emitted by azd.
- Smoke invoke succeeded with correlated thread:
  - `thread_id=foundry-smoke-29041614595-1`
  - emitted HITL events (`checkpoint.created`, `hitl.request`).
- Hosted E2E suite passed:
  - `Foundry hosted E2E passed for thread base: foundry-e2e-29041614595-1`
- App Insights telemetry gate passed with correlated thread id:
  - attempt 1: `telemetry_count=0`
  - attempt 2: `telemetry_count=1`
  - `Telemetry gate passed`

Result:

- Goal path is now proven end-to-end through GitHub self-hosted private runner flow:
  - BYO VNet Foundry infra provisioned
  - hosted agent deployed
  - smoke + E2E checks passed
  - telemetry verified in App Insights

## Latest execution update (2026-07-09, manual-testing matrix local + Foundry)

Manual matrix source:

- `docs/manual-testing.md` ORD-1001..ORD-1010 matrix
- command runner: `make manual-matrix`

### Local matrix (maf_sdk path) — PASS

Environment used:

- docker compose with `WORKFLOW_MODE=maf_sdk` (local backend orchestration path)

Result:

- all 10 cases passed (`ORD-1001` through `ORD-1010`)
- representative threads:
  - `ORD-1001`: `5bbc70bf-677c-43a3-9692-f977b1aaf65c`
  - `ORD-1009`: `d89f25d3-32e4-4a81-8033-a7ff963124a8`

### Foundry matrix from public localhost adapter — expected FAIL

Environment used:

- local docker backend adapter with `WORKFLOW_MODE=foundry_hosted`
- hosted endpoint `https://maffndaiktbblpk7mli2a.services.ai.azure.com/.../invocations`

Result:

- all cases failed at `/api/chat/run` with backend 500.
- backend root cause:
  - Foundry invoke returned `403`
  - message: `Public access is disabled. Please configure private endpoint.`

Interpretation:

- this is expected for public localhost execution against private-endpoint-only Foundry account.
- local public host is not a valid execution surface for private Foundry matrix runs.

### Foundry matrix from private VM (inside VNet) — PASS

Execution surface:

- VM: `vm-maffnd-runner` (private VNet path)
- repo workspace on VM runner volume
- docker compose backend adapter in `foundry_hosted` mode with hosted endpoint + token

Result:

- all 10 cases passed (`ORD-1001` through `ORD-1010`)
- representative threads:
  - `ORD-1001`: `9ee7c78f-1c85-41b8-b146-5936ed7e2e96`
  - `ORD-1009`: `05d5846c-6e4c-40a9-9952-5ea7a22d67aa`

Key learnings:

1. Private Foundry parity/manual matrix must run from a private-network execution host (runner VM or equivalent), not from public localhost.
2. Local parity remains useful in `maf_sdk` mode for deterministic baseline validation.
3. For Foundry-hosted matrix runs, retain quota-safe timing (`--request-timeout 120 --timeout 120 --case-delay 10` or higher).

### Rubber-duck review summary (2026-07-09)

Review focus:

- recent Foundry private-VNet closure commits + workflow/IaC hardening.

Top findings:

1. **High**: Search fallback to `eastus` while Foundry/VNet stays in `eastus2` introduces cross-region data path and latency/compliance considerations that should be explicitly documented/guarded.
2. **Medium**: runner preflight currently treats `actions/runners` API `403` as pass; this can produce false-green preflight and delayed queued-job failures when runner is offline.
3. **Medium**: ACR remains public (`publicNetworkAccess=Enabled`) while rest of stack is private; this is an intentionality gap for private-surface posture.
4. **Low**: docs-only commits currently match orchestrator push paths and can trigger expensive infra runs unnecessarily.

Follow-up actions captured:

- document cross-region Search tradeoff at parameter/workflow level.
- tighten preflight behavior for runner API permission failures.
- decide and document ACR private endpoint/public access posture.
- remove docs-only trigger from orchestrator push paths unless explicitly desired.

### Rubber-duck follow-up implementation (2026-07-09)

Implemented in this pass:

1. Runner preflight now fails on GitHub runners API `403` instead of passing silently:
   - `scripts/github/verify_foundry_runner_ready.sh`
2. Orchestrator trigger scope tightened:
   - removed docs-only path trigger from `.github/workflows/foundry-orchestrator.yml`.
3. Orchestrator `deploy_only` runner/default behavior normalized:
   - `runner_label`, `environment`, and smoke/telemetry/e2e flags now use same defaults as other orchestrator branches.
4. ACR private-surface hardening:
   - `infra/foundry-hosted/iac/main.bicep`
   - set ACR `publicNetworkAccess` to `Disabled`.
   - added ACR private endpoint (`groupId=registry`) and DNS zone wiring (`privatelink.azurecr.io`).
5. Search cross-region guard/visibility:
   - `infra/foundry-hosted/iac/main.bicep` now exposes `aiSearchTopologyWarning` output when Search region differs from deployment location.
   - `.github/workflows/foundry-provision.yml` now emits an explicit workflow summary warning when `FOUNDRY_AI_SEARCH_LOCATION != FOUNDRY_LOCATION`.

Completed in this pass:

- Added VM host bootstrap script for GitHub runner prerequisites:
  - `scripts/github/bootstrap_vm_runner_host.sh`
  - installs/verifies `git`, `curl`, `jq`, `tar`, `unzip`, `make`, `python3`, docker, Azure CLI, and `azd`
  - configures `/mnt` tool paths used by Foundry workflows
- Hardened runner registration script:
  - `scripts/github/register_vm_runner.sh`
  - now runs host bootstrap by default and performs explicit preflight checks (`git`, `docker`, `az`, `azd`)
- Added runner readiness verification script:
  - `scripts/github/verify_foundry_runner_ready.sh`
  - validates that a `foundry-private` labeled runner is online in GitHub before dispatch
- Added orchestrator preflight job:
  - `.github/workflows/foundry-orchestrator.yml` now checks runner readiness on `ubuntu-latest` before provision/deploy jobs
- Updated Foundry README with VM runbook and troubleshooting for offline/queued runner scenarios.

Current blocker:

- Runner queue issue is cleared using `copilot-temp-foundry-private` (online self-hosted runner with `foundry-private` label).
- New hard blocker is Foundry data-plane authorization during deploy:
  - workflow run: `29031213475`
  - job: `deploy_only / Deploy Foundry Hosted Agent`
  - failure: `403 Forbidden` on
    `GET https://maffndaiktbblpk7mli2a.services.ai.azure.com/api/projects/order-resolution/agents/order-resolution-hosted`
- Because deploy fails, smoke/E2E/telemetry steps are not reachable in the same run.

## Latest execution update (2026-07-09, cloud-proof attempts after runner recovery)

Completed in this pass:

- Cleared queue blocker by registering a temporary runner:
  - `copilot-temp-foundry-private` (`online`)
- Updated and pushed workflow hardening for auth/path resilience:
  - fallback writable config paths when `/mnt` is unavailable
  - telemetry query YAML parsing fix
  - runner preflight made non-blocking for `GITHUB_TOKEN` `actions/runners` 403 in hosted preflight job
  - OIDC fallback path for workflows when `AZURE_CLIENT_SECRET` is absent
- Aligned environment variables to active eastus2 Foundry project:
  - `FOUNDRY_RESOURCE_GROUP=rg-maf-ora-foundry`
  - `FOUNDRY_PROJECT_ID=/subscriptions/.../resourceGroups/rg-maf-ora-foundry/providers/Microsoft.CognitiveServices/accounts/maffndaiktbblpk7mli2a/projects/order-resolution`
  - `FOUNDRY_PROJECT_ENDPOINT=https://maffndaiktbblpk7mli2a.services.ai.azure.com/api/projects/order-resolution`
  - `FOUNDRY_LOCATION=eastus2`, `APPINSIGHTS_APP_ID=e6e3fa8d-1f5e-487a-be6a-dfd1874fb7a3`
- Configured OIDC federation for UAMI principal:
  - identity: `uami-maffnd-runner` (`clientId=7fcd23e4-3ca3-457b-9e53-fc63ad58bf75`)
  - federated subjects:
    - `repo:ppenumatsa1/maf-order-resolution-agent:environment:foundry-private-env`
    - `repo:ppenumatsa1/maf-order-resolution-agent:ref:refs/heads/feature/foundry-private-network-vnet`
- Applied RBAC assignments for the same principal at RG/account/project scopes.

Observed outcomes:

- Provision can now execute and complete in some runs (example: orchestrator run `29029857025`, provision job succeeded).
- Full provision is still unstable when forced:
  - `InUseSubnetCannotBeDeleted` (subnet `snet-runner` currently attached to VM NIC)
  - `InsufficientResourcesAvailable` in `eastus2`
- Deploy consistently fails with Foundry agent data-plane `403` despite management-plane RBAC:
  - latest confirmed: run `29031213475`
  - this is the active blocker for cloud-proof completion.

## Latest execution update (2026-07-08, azd project-root mismatch root cause)

New root cause identified:

- `infra/foundry-hosted/azure.yaml` was present only in local workspace and not tracked in git.
- On VM/CI checkouts, that file was missing, so running `azd` from `infra/foundry-hosted` resolved upward to repo-root `azure.yaml`.
- Repo-root `azure.yaml` points to `infra/azure-apphosted/iac`, which carries chat model defaults tied to the recurring `gpt-4.1-mini` validation failure.

Impact:

- Prior attempts that appeared to run "foundry-hosted" were actually provisioning the apphosted stack.
- This explains persistent `gpt-4.1-mini` validation errors even when foundry-hosted Bicep defaults had `gpt-4o-mini`.

Action in progress:

- Track and commit `infra/foundry-hosted/azure.yaml` so VM/CI resolves to the intended foundry-hosted azd project.
- Re-run provision/deploy from VM after pull to separate true regional platform blockers from wrong-project execution.

Follow-up findings after pull:

- Once `infra/foundry-hosted/azure.yaml` became available on VM, additional repository tracking gaps surfaced:
  - `infra/foundry-hosted/iac/modules/private-runner-access.bicep` was not tracked in git.
  - `infra/foundry-hosted/iac/modules/vnet.bicep` local changes (new params consumed by `main.bicep`) were not yet committed.
- This caused Bicep compile failures (`BCP037`, `BCP091`, `BCP062`) before Azure validation.
- Service path in `infra/foundry-hosted/azure.yaml` originally targeted `./agent` (untracked directory in repo state). Updated to tracked path `../../backend/foundry`.

Additional corrections from validation:

- `azd` rejects service project paths containing `..` in `azure.yaml`; cross-directory service path is invalid.
- Reverted service path to `./agent` and moved to tracking required files under `infra/foundry-hosted/agent`.
- Bicep compile blocked by `BCP177` because module output was referenced in another module's `if` condition.
- Updated `runnerSubscriptionRbac` module condition to avoid output-dependent compile-time evaluation.

Immediate corrective action:

- Commit module/interface alignment files plus tracked service path so VM/CI can execute the intended stack without local-only artifacts.

## Latest execution update (2026-07-08, unblock actions applied)

Completed in this pass:

- Applied subscription-scope RBAC to runner identity `d77e1944-7251-41ef-be3b-883d0e503046`:
  - `Contributor`
  - `User Access Administrator`
- Re-ran private VM flow after RBAC update and repaired env corruption source in root azd env path.
- Seeded `POSTGRES_ADMIN_PASSWORD` non-interactively to clear provisioning input prompt.

Current blockers after rerun (updated):

1. Provision is now blocked by model support mismatch, not RBAC:
  - `DeploymentModelNotSupported`
  - model: `gpt-4.1-mini` version `2024-07-18`
  - region: `centralus`
2. Deploy remains blocked by hosted-agent regional support:
  - `Unsupported region for Foundry Hosted Agents`
  - request id: `345c50279ccfac14e00bb67a5cd9f12a`

Result:

- Subscription validation-permission blocker (`Microsoft.Resources/deployments/validate/action`) is no longer the first failing gate after RBAC fix.
- Remaining unblock path is region/model alignment for Foundry account/project and model deployment.

## Latest execution update (2026-07-08, tracked-source fixes + endpoint retarget)

Completed in this pass:

- Applied and pushed repository fixes so VM/CI no longer depend on local-only files:
  - tracked `infra/foundry-hosted/azure.yaml`
  - tracked `infra/foundry-hosted/iac/modules/private-runner-access.bicep`
  - tracked `infra/foundry-hosted/agent/*` source files needed by azd packaging
  - aligned VNet module interface consumed by `main.bicep`
  - fixed Bicep compile-time condition (`BCP177`) in runner subscription RBAC module gating
- Validation after these fixes:
  - `azd provision --preview` now succeeds from `infra/foundry-hosted` and plans `gpt-4o-mini` + `text-embedding-3-small` (no `gpt-4.1-mini` validation failure on this path).
- Retargeted azd environment to newly provisioned Foundry project:
  - account: `maffndaizb4lxy66zp2uk`
  - project: `order-resolution`
  - updated env keys: `AZURE_AI_PROJECT_ID`, `FOUNDRY_PROJECT_ID`, `FOUNDRY_PROJECT_ENDPOINT`

Current blockers after retarget:

1. Deploy/invoke now fail with network access error on new account endpoint:
   - `403 Public access is disabled. Please configure private endpoint.`
   - indicates deploy is finally targeting new account/project but private-link access path for that endpoint is not yet effective for VM path.
2. Deploy against old endpoint still fails with hosted-agent regional support error.

Net result:

- RBAC and source-control hygiene blockers are substantially reduced.
- Remaining blockers are private endpoint routing/policy for the new Foundry account and hosted-agent regional capability for the legacy endpoint.

## Latest execution update (2026-07-08, post-RBAC-IaC rerun on private VM)

Completed in this pass:

- Confirmed IaC RBAC module changes are pushed to branch `feature/foundry-private-network-vnet` (`1eccddc`).
- Re-ran end-to-end flow from private VM path (provision -> deploy -> smoke -> e2e -> telemetry query).
- Found and fixed an azd environment corruption on VM at:
  - `.azure/ora-private-uami/.env`
  - Corruption pattern was escaped quote pollution (`\"...`) introduced by prior env mutation attempts.
- Repaired VM env by copying clean env from:
  - `infra/foundry-hosted/.azure/ora-private-uami/.env`

Current blocker outcomes after rerun:

- Provision still fails at subscription validation due to RBAC:
  - `AuthorizationFailed`
  - principal: `1aefdd7d-d497-434f-815a-89ce3b335edb` (object `d77e1944-7251-41ef-be3b-883d0e503046`)
  - missing action: `Microsoft.Resources/deployments/validate/action`
  - scope: subscription `4f18d577-3506-4a11-85e5-a83b14727a84`
- Deploy fails with region support error:
  - `Unsupported region for Foundry Hosted Agents`
  - request id: `9a24c095d1df32441f472f010fb2e095`
- Smoke invoke fails expectedly after deploy failure:
  - `404 Agent 'order-resolution-hosted' not found`
  - request id: `f6756982cadc36031350b290423cc94d`
- E2E fails because runtime/API endpoint is unavailable and VM lacks npm:
  - repeated `curl: (7) Failed to connect to 127.0.0.1:<port>`
  - `bash: npm: command not found`
- App Insights query fails for current caller with insufficient access:
  - `InsufficientAccessError: The provided credentials have insufficient access to perform the requested operation`

Status codes from this run:

- `PROVISION_RC=1`
- `DEPLOY_RC=1`
- `SMOKE_RC=1`
- `E2E_RC=2`

Open external blockers (unchanged priority):

1. Subscription-scope RBAC for runner identity still insufficient for deployment validation.
2. Hosted agent region support mismatch remains (`centralus` path warning/error context).
3. Telemetry verification requires additional App Insights read permissions for the executing identity.

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

## Latest execution update (2026-07-08, non-interactive subscription input)

Failure observed:

- `azd provision --no-prompt` failed with `prompt required` and reported missing input:
  - `subscription` (`AZURE_SUBSCRIPTION_ID`)

Change made:

- Added explicit azd environment seeding in provision/deploy workflows:
  - `azd env set AZURE_SUBSCRIPTION_ID ${{ vars.AZURE_SUBSCRIPTION_ID }}`

Expected effect:

- `azd provision` runs non-interactively without subscription prompts.

## Latest execution update (2026-07-08, postgres admin password input)

Failure observed:

- Provision initialization still failed with missing required input:
  - `postgresAdministratorPassword`
  - expected env var `POSTGRES_ADMIN_PASSWORD`

Change made:

- In provision workflow env-seeding step:
  - use `secrets.POSTGRES_ADMIN_PASSWORD` when available
  - otherwise generate a strong fallback password and set `POSTGRES_ADMIN_PASSWORD` in azd env

Expected effect:

- `azd provision --no-prompt` no longer blocks on missing Postgres admin password.

## Latest execution update (2026-07-08, final provisioning blocker)

Current status:

- Provision pipeline now gets through auth, azd extension install, env sync, and non-interactive input seeding.
- Provision stops at Azure deployment validation with RBAC failure.

Blocking error:

- `AuthorizationFailed` for client `1aefdd7d-d497-434f-815a-89ce3b335edb` (object `d77e1944-7251-41ef-be3b-883d0e503046`)
- Missing permission for action:
  - `Microsoft.Resources/deployments/validate/action`
- Scope:
  - `/subscriptions/4f18d577-3506-4a11-85e5-a83b14727a84`

Operational note:

- Runner runtime prerequisites were remediated (disk, DNS, azd extension, docker install/access), and those are no longer the active blocker.

Additional warning seen during validation:

- Model `gpt-4.1-mini` (`GlobalStandard`, version `2024-07-18`) not found in `centralus`; even after RBAC is fixed, this model mapping may require adjustment.

Required external action:

- Grant the runner identity sufficient RBAC at subscription/resource-group scope (Contributor minimum, and Owner/User Access Administrator if role assignments are created by template), then rerun orchestrator.

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

---

## 2026-07-18T02:30Z — DEFINITIVE RCA: private 403 = missing PROJECT capability host

Back-tracked from the last-known-good deploy (`feb052b`, run `29617103198`, 2026-07-17)
to HEAD and inspected live control-plane state of the recreated account
`maffndaiktbblpk7mli2a` (RG `rg-maf-ora-foundry`).

### Confirmed facts (live `az` queries, subscription `4f18d577-...`)

- Account capability host EXISTS and is healthy:
  `maffndaiktbblpk7mli2a@aml_aiagentservice`, `capabilityHostKind=Agents`,
  `customerSubnet=snet-agent-host`, `provisioningState=Succeeded` (created 00:47 with the
  account). => network injection effectively applied at account creation.
- **PROJECT capability host list is EMPTY (`[]`)** for `projects/order-resolution`.
- Project managed identity (`5425b213-...`) has ONLY `Foundry User` on the account. It is
  MISSING every pre-caphost data-plane role (Storage Blob Data Contributor on storage,
  Cosmos DB Operator on cosmos, Search Index Data Contributor + Search Service Contributor
  on search) and post-caphost container roles (Storage Blob Data Owner, Cosmos DB Built-in
  Data Contributor).
- OIDC deployment SP (`appId 1aefdd7d-...`) has only **Contributor** at RG scope (the two RG
  role assignments are both Contributor; none is User Access Administrator or Owner). It
  cannot create role assignments — which is why provision `29625658341` failed with a
  roleAssignments/write authorization error.

### Root-cause chain

1. Account recreate needed the OIDC principal to assign project-identity RBAC, but that
   principal only has Contributor at RG (no UAA/Owner) → role-assignment writes fail.
2. RBAC-guard added in commit `92841ea` (foundry-provision.yml) detected the missing
   UAA/Owner and **silently disabled** `assign_pre_caphost_rbac`,
   `assign_post_caphost_rbac`, and `create_project_capability_host` to avoid a hard failure.
3. Provision then "succeeded" but skipped project-identity RBAC and the project capability
   host entirely.
4. Without the project capability host, the project Agents data-plane private admission path
   is never established → `/api/projects/order-resolution/agents` returns
   `403 Traffic is not from an approved private endpoint` (same missing data-plane also
   explains the container→model 403).

### Where it worked vs now

- Working account (2026-07-17) had a project capability host + project-identity data-plane
  RBAC (created when the principal had sufficient rights / older account). Deploy+smoke+e2e
  passed; only defect was the model path not being exercised (deterministic).
- Recreated account (2026-07-18) is missing the project capability host and project RBAC.
  The `virtualNetworkRules:[]` and API-version diffs are NOT the cause; the missing project
  caphost is.

### Fix options

- Option A (targeted, no account recreate; fastest to green): as subscription Owner, assign
  the four pre-caphost roles to the project identity, create the project capability host,
  then assign post-caphost container roles; re-run deploy to confirm the 403 clears. Then
  make it reproducible: grant the OIDC SP `User Access Administrator` at RG and replace the
  silent RBAC auto-disable with an explicit preflight failure.
- Option B (reproducible-first): grant OIDC SP `User Access Administrator` at RG, remove the
  silent auto-disable, re-run provision (creates RBAC + project caphost), then deploy.

### 2026-07-18T02:55Z — Targeted repair applied (project caphost + RBAC)

As subscription Owner, replicated the repo IaC modules manually on account
`maffndaiktbblpk7mli2a` / project `order-resolution` (project identity `5425b213-...`):

- Pre-caphost RBAC assigned: Storage Blob Data Contributor (storage
  `maffndstktbblpk7mli2a`), Cosmos DB Operator (cosmos `maffndcosmosktbblpk7mli2a`),
  Search Index Data Contributor + Search Service Contributor (search
  `maffndsrchktbblpk7mli2a`).
- Created project capability host `caphostproj` (`capabilityHostKind=Agents`,
  vectorStore=search conn, storage=storage conn, threadStorage=cosmos conn),
  api-version `2025-04-01-preview` -> `provisioningState=Succeeded`.
- Post-caphost RBAC assigned: Storage Blob Data Owner (conditional ABAC on
  `<workspaceId 26d64a8e...>*-azureml-agent` containers) and Cosmos DB Built-in Data
  Contributor (SQL role on `enterprise_memory`).

Verified role set now matches the IaC/docs exactly. Docs cross-check
(learn.microsoft.com standard agent setup) confirms same roles/ordering and API.
Next: trigger private deploy to prove the `/agents` 403 clears, then fold these into IaC
(OIDC UAA + project-identity RBAC + caphost) so a clean provision reproduces this.

### 2026-07-18T03:20Z — Agents management-API 403 is NOT fixable by account config toggles

After creating the project caphost + RBAC and applying networkInjections, ran a
controlled elimination from INSIDE the VNet (runner VM `vm-maffnd-runner`, snet-runner,
via approved account PE 10.90.2.8). Probed the agents management API and other data-plane
paths on the same account/host:

| Path (host services.ai.azure.com -> 10.90.2.8) | Result |
| --- | --- |
| `/api/projects/order-resolution/agents?api-version=v1` | **403 "Traffic is not from an approved private endpoint"** |
| `/openai/deployments?api-version=2024-10-21` | 404 Resource not found (network OK, reached service) |
| `/openai/models?api-version=2024-10-21` (cognitiveservices token) | 401 PermissionDenied (network OK, authz only) |

Same host/IP; only the AGENTS path returns the network-admission 403. The openai/cognitive
paths are reachable. => the agents management data-plane enforces its own private
admission, independent of the account PE.

The `/agents` 403 persisted UNCHANGED across every toggle tested (each reverted after):

- project capability host present (created `caphostproj`, Succeeded);
- project-identity data-plane RBAC (all 6 roles present);
- `networkInjections` PATCHed onto the account (reads back populated, state Succeeded);
- `networkAcls.virtualNetworkRules = [agentSubnet]` vs `[]`;
- `publicNetworkAccess = Enabled` vs `Disabled`;
- caller identity granted `Foundry User` + `Azure AI User` on the account.

Models `gpt-4o-mini` + `text-embedding-3-small` are deployed (Succeeded).

### Interpretation

- Microsoft Learn: hosted-agent network injection must be present at **account creation**;
  adding it later is unsupported. The control plane ACCEPTED a post-creation
  `networkInjections` PATCH (property now populated) but the agents admission path did not
  start working — consistent with injection needing to be wired at creation, not patched.
- The last clean provision emitted NO injection because `enableStandardAgentNetworkInjection`
  resolved false; the account capability host `customerSubnet` came from the
  `add-account-capability-host` module, which is a separate mechanism and does not wire the
  agents admission path.
- `infra/foundry-hosted/iac/main.bicep:376` DOES spread `networkInjections` into the account
  creation PUT, but only when `enableStandardAgentNetworkInjection` is true.

### Genuine fixes applied (retained on the live account)

- project capability host `caphostproj` (Succeeded);
- project-identity RBAC: Storage Blob Data Contributor, Cosmos DB Operator, Search Index
  Data Contributor, Search Service Contributor, Storage Blob Data Owner (conditional),
  Cosmos DB Built-in Data Contributor (enterprise_memory);
- `networkInjections` populated on the account (will be re-applied at creation on next clean
  provision).

### Verdict

The private agents management data-plane admission cannot be repaired by in-place account
configuration. A reliable private lane requires a CLEAN account creation with
`enableStandardAgentNetworkInjection=true` so injection is in the initial account PUT, plus
OIDC UAA so provision creates project caphost + RBAC deterministically (no silent skip).
This is a deploy-workflow-validated operation; `gh workflow run` is currently blocked in this
environment, so the clean re-provision must be dispatched by the user or via re-enabled CI.

### 2026-07-17T22:20Z — Execution unblock verified + OIDC SP identity corrected

Verification only (no dispatch, no provisioning). User switched `gh` to account
`ppenumatsa1` and shifted to autopilot to unblock CI dispatch.

- `gh auth status`: active account = `ppenumatsa1`, scopes `repo`,`workflow`; repo
  permissions `admin:true,push:true`. `foundry-provision.yml` and `foundry-deploy.yml`
  are visible/active. => `gh workflow run` dispatch is now available (earlier
  "Permission denied and could not request permission from user" is resolved).
- `az account show`: logged in as `ppenumatsa@microsoft.com` (subscription Owner).

Correction to prior RCA (identity was wrong):

- The private env `foundry-private-env` uses env-scoped `AZURE_CLIENT_ID =
  7fcd23e4-3ca3-457b-9e53-fc63ad58bf75` (SP objectId `06060201-cd7f-4df2-a5e0-785b2dcf9a16`),
  NOT the repo-level `1aefdd7d-...` recorded earlier. The repo-level appId no longer
  resolves as an SP (stale variable; env-scoped value is authoritative).
- Actual RBAC of the real OIDC SP `7fcd23e4-...`:
  - `Contributor` on `rg-maf-ora-foundry`
  - `Foundry Project Manager` at subscription scope
  - NO `User Access Administrator`/`Owner`. `Foundry Project Manager` does not grant
    `Microsoft.Authorization/roleAssignments/write`.

Implication: the remaining reproducible-provision prerequisite is unchanged in substance
(grant the OIDC SP `User Access Administrator` on the target RG before provision) but now
targets SP `7fcd23e4-...` / objectId `06060201-...`. Not yet applied (implementation
deferred per user: "we will run later").

### 2026-07-17T22:18Z — UAA granted to correct OIDC SP + pre-implementation readiness check

Per user request, granted `User Access Administrator` to the **actual** private-env OIDC SP
before implementation:

- Target SP appId: `7fcd23e4-3ca3-457b-9e53-fc63ad58bf75`
- Target SP objectId: `06060201-cd7f-4df2-a5e0-785b2dcf9a16`
- Scope: `/subscriptions/4f18d577-3506-4a11-85e5-a83b14727a84/resourceGroups/rg-maf-ora-foundry`
- Result: assignment created successfully (`UAA_COUNT` changed from `0` to present)

Effective role set after grant:

- RG `rg-maf-ora-foundry`: `Contributor`, `User Access Administrator`
- Subscription scope: `Foundry Project Manager`

Readiness checks completed (no deploy/provision dispatched yet):

- `gh` active account = `ppenumatsa1`, scopes include `workflow`, repo admin true
- Foundry workflows visible and active: `foundry-provision.yml`, `foundry-deploy.yml`
- `az` context = subscription `4f18d577-3506-4a11-85e5-a83b14727a84`, user
  `ppenumatsa@microsoft.com`
- `foundry-private-env` variables point at current private account/project and use
  `AZURE_CLIENT_ID=7fcd23e4-...` with `FOUNDRY_DEPLOY_AUTH_MODE=service-principal`

### 2026-07-17T22:26Z — IaC/workflow guard fix implemented (fail-fast + deterministic network wiring)

Implemented the first private reproducibility fix in `.github/workflows/foundry-provision.yml`:

- Removed the silent auto-disable path that previously turned off:
  - `CREATE_PROJECT_CAPABILITY_HOST`
  - `ASSIGN_PRE_CAPHOST_RBAC`
  - `ASSIGN_POST_CAPHOST_RBAC`
  when the deployment SP lacked UAA/Owner.
- Replaced with explicit fail-fast behavior:
  - if UAA/Owner is missing at RG scope, workflow exits with a clear remediation message.
  - no hidden state mutations / no false-green provisions.
- Added deterministic profile wiring for AZD env values each run:
  - private profile now explicitly sets
    `CREATE_PRIVATE_DNS_VNET_LINKS=true`,
    `CREATE_PRIVATE_ENDPOINTS=true`,
    `CREATE_NAT_GATEWAY=true`,
    `CREATE_PRIVATE_RUNNER_ACCESS=false`,
    `CREATE_BASTION_HOST=true`,
    `CREATE_RUNNER_VM=true`,
    `ENABLE_STANDARD_AGENT_NETWORK_INJECTION=true`.
  - public profile now explicitly sets those to `false`, including
    `ENABLE_STANDARD_AGENT_NETWORK_INJECTION=false`.

This closes the specific drift/regression where stale env values or missing UAA caused private
reprovision to skip caphost/RBAC and later fail with agents data-plane admission 403.

### 2026-07-17T22:31Z — Fleet + rubber-duck follow-up hardening applied

Ran parallel fleet scan + rubber-duck review on the workflow fix and applied two high-signal
hardening updates:

1. **Inherited RBAC check correctness**
   - Updated UAA/Owner/Contributor role checks to include inherited assignments:
     `az role assignment list --include-inherited ...`
   - This prevents false negatives when UAA/Owner is granted at parent scopes.

2. **Creation-time injection guard for existing private accounts**
   - Added explicit guard in private provision and private deploy preflight:
     - if an existing Foundry account has `properties.networkInjections` length `0`,
       fail fast with a clear recreate instruction.
   - This avoids accidental reruns that pretend injection can be retrofitted in-place.

This keeps the fail-fast behavior deterministic while preventing two known failure modes:
scope-inheritance RBAC false fails and no-injection existing-account drift.

### 2026-07-17T22:35Z — Started clean private recreate execution (new RG lane)

Execution phase started per plan after pre-reqs were in place.

- Local AZD environments remain the expected two:
  - `foundry-private-env` (default)
  - `foundry-public-dev2`
- New target resource group for clean recreate:
  - `rg-maf-ora-foundry-v2` (not present before start)
- Current `foundry-private-env` had no explicit
  `ENABLE_STANDARD_AGENT_NETWORK_INJECTION` / caphost/RBAC toggle keys; this is exactly why
  workflow-side explicit profile wiring was added.

Next actions in this run:
- create `rg-maf-ora-foundry-v2`,
- repoint `foundry-private-env` to the new RG,
- run `make foundry-provision`,
- then `make foundry-deploy` + smoke + hosted E2E if provision succeeds.

### 2026-07-17T22:40Z — Provision attempt #1 failed; RCA = transient account Accepted state

`make foundry-provision` in `rg-maf-ora-foundry-v2` created most resources but failed while
creating the Foundry private endpoint deployment with:

- `AccountProvisioningStateInvalid`
- message: account `maffndai4aiw7fw5gjdo4` still in `Accepted` when PE creation ran

Post-failure inspection:

- account provisioning moved to `Succeeded`
- `networkInjections` is correctly present (preview API check), with
  `scenario=agent`, `subnetArmId=.../snet-agent-host`, `useMicrosoftManagedNetwork=false`
- failed unit was nested deployment `private-endpoint-foundry-account`

Action: rerun provision now that account is fully `Succeeded` to complete pending PE wiring.

### 2026-07-17T22:46Z — Provision retry succeeded in new RG

Re-ran `make foundry-provision` against `rg-maf-ora-foundry-v2` after the transient Accepted
state cleared.

Result: success. The previously failing Foundry private endpoint now completed:

- `maffnd-foundry-pe-4aiw7fw5gjdo4` => `Succeeded`

Provision status now green for the clean private stack in the new RG. Proceeding to deploy.

### 2026-07-17T22:50Z — Deploy attempt #1 failed: missing AZURE_AI_PROJECT_ID in local AZD env

`make foundry-deploy` failed early with:

- `Microsoft Foundry project ID is required: AZURE_AI_PROJECT_ID is not set`

Why this occurred:

- local `make foundry-deploy` path does not auto-derive project id/endpoint from the newly
  provisioned resources (CI workflow does this in its environment-setup step).

Action:

- resolve account + project in `rg-maf-ora-foundry-v2`,
- set `AZURE_AI_PROJECT_ID` and related Foundry endpoint/id keys in `foundry-private-env`,
- rerun deploy.

### 2026-07-17T22:53Z — Deploy attempt #2 from local host blocked by private network (expected)

After setting project id/endpoint keys locally, `make foundry-deploy` reached the agent
existence check but failed with:

- `403 Public access is disabled. Please configure private endpoint.`

This confirms local operator-host deploy is outside the private data-plane admission path.
Expected path for private lane is the self-hosted private runner / workflow execution.

Action:

- update GitHub `foundry-private-env` variables to the new RG/account/project,
- dispatch `foundry-deploy.yml` on `foundry-private` runner with smoke (+ e2e),
- continue validation from that in-VNet execution path.

### 2026-07-17T22:48Z — First in-VNet deploy workflow run failed preflight on data-plane RBAC

Dispatched `foundry-deploy.yml` from branch `feature/foundry-private-network-vnet` against
`foundry-private-env` (new RG/account values). Run:

- `29629446157`

Failure details:

- step: `Private runner path preflight`
- message:
  `Missing account data-plane authorization. Expected Foundry User on .../accounts/maffndai4aiw7fw5gjdo4 or Contributor/Owner on .../resourceGroups/rg-maf-ora-foundry-v2`

RCA:

- OIDC deployment SP had Contributor+UAA at RG (control-plane sufficient), but lacked
  Foundry data-plane role at the new account scope.

Fix applied:

- assigned `Foundry User` to SP `7fcd23e4-...` on account
  `/subscriptions/4f18d577-.../resourceGroups/rg-maf-ora-foundry-v2/providers/Microsoft.CognitiveServices/accounts/maffndai4aiw7fw5gjdo4`

Re-dispatched deploy workflow:

- `29629465681` (queued/in-progress after fix)

### 2026-07-17T22:52Z — Second in-VNet deploy run failed on DNS resolution path

Run `29629465681` progressed past RBAC checks but failed preflight at DNS resolution:

- `curl: (6) Could not resolve host: maffndai4aiw7fw5gjdo4.services.ai.azure.com`

RCA:

- private runner remains in old VNet (`rg-maf-ora-foundry`),
- clean recreated account is in new RG/VNet (`rg-maf-ora-foundry-v2`),
- runner VNet has no DNS/network path to the new account private endpoint.

Attempted VNet peering old<->new failed because both VNets use overlapping CIDR `10.90.0.0/16`
(`VnetAddressSpacesOverlap`).

Recovery pivot:

- keep the clean recreated account,
- bridge connectivity by creating an additional Foundry account private endpoint in the old
  runner VNet + attach old private DNS zones,
- then rerun deploy workflow.

### 2026-07-17T22:56Z — User decision: no cross-VNet sharing; runner must be in new VNet

User directive:

- **do not cross-share across VNets**
- create a **new VM later in the new VNet** and use that runner path for private validation

Actions taken immediately:

- stopped cross-VNet recovery path (no VNet peering / no bridge endpoint rollout continuation)
- marked private deploy/smoke/e2e validation as blocked until new in-VNet runner is created in
  `rg-maf-ora-foundry-v2`

Current state preserved:

- workflow hardening + fail-fast guards are committed/pushed (`06e1d96`)
- clean private stack provision in new RG succeeded (`maffndai4aiw7fw5gjdo4`)
- deploy from old runner remains intentionally blocked by policy until runner relocation

### 2026-07-17T23:12Z — New in-VNet runner created and registered (no cross-VNet sharing)

Executed user-approved path: create a new runner in the new VNet, no peering/bridging.

- Created VM `vm-maffnd-runner-v2` in `rg-maf-ora-foundry-v2`, subnet `snet-runner`
  (private IP `10.90.3.4`), with no public IP.
- Registered GitHub self-hosted runner service on the VM and verified online status.
- Added dedicated label `foundry-private-v2` to force dispatch to the new in-VNet runner.

Runner bootstrap fixes applied during setup:

- installed Azure CLI on VM (`az` required by `azure/login@v2` + workflow steps),
- enabled passwordless sudo for user `runner` (required by `Azure/setup-azd@v2` installer),
- installed `make` + `jq` (required by workflow `make foundry-deploy` path).

Validation evidence:

- runner appears online with labels: `self-hosted`, `Linux`, `X64`, `foundry-private-v2`.

### 2026-07-17T23:18Z — Deploy on new runner reached smoke; smoke failed on conversation timeout

Run `29630359693` on label `foundry-private-v2`:

- preflight passed (DNS resolved to private IP `10.90.2.12`, account/project checks passed)
- deploy step succeeded and agent version active
- smoke failed on first low-risk call (`ORD-1001`) with:
  - `failed to create conversation ... context deadline exceeded`

To make smoke resilient to this transient startup behavior, updated workflow retry logic in
`.github/workflows/foundry-deploy.yml` to treat these as retryable:

- `session_not_ready`
- `context deadline exceeded`
- `failed to create conversation`
- `timed out`

This keeps non-retryable failures hard-failing while allowing startup/network transient retries.
## Latest execution update (2026-07-18, private-v2 runner evidence after successful deploy run `29630486149`)

### What was validated

1. Re-checked private-v2 state from the in-VNet runner `vm-maffnd-runner-v2` after successful deploy/smoke/E2E run `29630486149`.
2. Verified PostgreSQL runtime target from runner AZD env context:
   - host: `maffndpg7930.postgres.database.azure.com`
   - database: `maf_workflow`
3. Queried workflow persistence tables from the runner path and confirmed fresh write activity:
   - `workflow_runs=105`
   - `workflow_events=819`
   - `RECENT_WORKFLOW_RUNS=5` (last 2 hours at query time)
4. Collected recent correlation evidence:
   - run rows include private conversations in `completed` and `waiting_approval` states,
   - `workflow_events` include expected `hitl.request`, `hitl.response`, and `workflow.output` patterns,
   - `checkpoints`/`approvals` show pending and approved HITL transitions for recent `ord-1009`/`ord-1001` activity.

### New finding (remaining gap)

Private-v2 telemetry parity is still open:

- App Insights component `maffnd-mon-4aiw7fw5gjdo4-appi` and workspace `maffnd-mon-4aiw7fw5gjdo4-law` currently return zero rows for `AppRequests/AppDependencies/AppTraces` in the recent window.
- Runner AZD env snapshot shows `FOUNDRY_RUNTIME_ENV` currently unset in the checked-out private env file, so telemetry env payload propagation remains the prime suspect for missing App Insights evidence.

### Next focused action

Patch private deploy/provision env seeding so `FOUNDRY_RUNTIME_ENV` is always set (including App Insights/OTEL keys), then rerun private deploy workflow and re-check App Insights KQL for run-correlated request/dependency/trace rows.

## Latest execution update (2026-07-18, repeatable PostgreSQL fix via IaC)

### What failed

- Recent private deploy runs started failing smoke with `HTTP 424 session_not_ready`.
- Hosted runtime logs showed deterministic DB bootstrap failure:
  - `failed to resolve host 'maffndpg7930.postgres.database.azure.com'`
  - `psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec`

### Root cause

- The private-v2 lane expected `maffndpg7930` in `rg-maf-ora-foundry-v2`, but no repeatable IaC-managed PostgreSQL definition existed in the Foundry hosted template.
- Workflows were deriving runtime DB URLs from “first server in RG” fallback logic, which is non-deterministic and fragile.

### Fix applied (repeatable IaC path)

1. Added PostgreSQL Flexible Server + firewall rule + `maf_workflow` database resources to `infra/foundry-hosted/iac/main.bicep`.
2. Added PostgreSQL parameters to `infra/foundry-hosted/iac/main.parameters.json`:
   - `CREATE_POSTGRES_SERVER`
   - `POSTGRES_SERVER_NAME`
   - `POSTGRES_ADMIN_USERNAME`
   - `POSTGRES_ADMIN_PASSWORD`
   - `POSTGRES_DATABASE_NAME`
   - `POSTGRES_LOCATION`
3. Added defaults for these env keys in `scripts/foundry/ensure_foundry_azd_defaults.sh`.
4. Hardened both Foundry workflows to use deterministic PostgreSQL env keys and server-name-based URL construction instead of list-first fallback.
