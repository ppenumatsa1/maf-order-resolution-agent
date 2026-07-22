# Issues, Changes, and Fixes (Foundry Private VM Path)

Date: 2026-07-07
Scope: Foundry hosted-agent deployment from private network path in `rg-maf-ora-ni-eus-07080910`.

## Latest execution update (2026-07-22, private scratch lane: smoke `session_not_ready` root-cause)

### Symptom

Hosted deploy succeeded, but smoke repeatedly failed with:

- HTTP `424 Failed Dependency`
- `error.code=session_not_ready`
- message: session did not become ready in time; check runtime `/readiness`

### Root cause observed from hosted system logs

For failing smoke session `d2ae288f70f55a36b29bbde054af36b84101e62b60a19a954bfdae404a87cb7`, hosted logs showed app startup failing on database initialization:

1. runtime attempted PostgreSQL pool connections to `127.0.0.1:5432`
2. repeated `connection refused`
3. startup crashed with `psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec`

This confirms DB URL wiring was not reaching the hosted runtime, so runtime fell back to loopback defaults and never became ready.

### Fixes applied

1. `scripts/foundry/ensure_foundry_azd_defaults.sh`
   - auto-compute `RUNTIME_DATABASE_URL` from provisioned PostgreSQL settings when missing
   - set `DATABASE_URL` from `RUNTIME_DATABASE_URL` when missing
   - mirror both to legacy lowercase aliases for IaC/workflow compatibility
2. `Makefile` (`foundry-deploy`)
   - before `azd deploy`, hydrate shell env from selected azd env via:
     - `set -a && eval "$(azd env get-values)" && set +a`
   - ensures `backend/agent.yaml` `${...}` substitutions resolve with actual azd env values during deploy packaging
3. Workflow env-seeding hardening (`.github/workflows/foundry-deploy.yml`, `.github/workflows/foundry-provision.yml`)
   - explicitly seed azd env with `POSTGRES_ADMIN_PASSWORD` (from environment secret)
   - removed direct seeding from `FOUNDRY_DATABASE_URL` secret to avoid stale-host drift after scratch reprovision
   - this prevents new/recreated azd environments from silently deploying hosted agents with stale DB URL hostnames
4. Hosted runtime secret binding hardening (`backend/agent.yaml`)
   - switched hosted DB runtime env vars to Foundry connection placeholders:
     - `FOUNDRY_RUNTIME_DATABASE_URL=${{connections.orderresolutionruntimesecrets.credentials.database_url}}`
     - `RUNTIME_DATABASE_URL=${{connections.orderresolutionruntimesecrets.credentials.database_url}}`
   - avoids dependence on ad-hoc shell env interpolation for DB connection strings.
5. Runtime DB URL drift guard (`scripts/foundry/ensure_foundry_azd_defaults.sh`)
   - when current `RUNTIME_DATABASE_URL` host does not match `POSTGRES_SERVER_NAME`, script now rewrites
     `RUNTIME_DATABASE_URL`/`DATABASE_URL` (+ lowercase aliases) to the computed current-server URL.

### Parallel observation: permissions

While diagnosing, VM-side log access initially failed with:

- `403` for `Microsoft.CognitiveServices/accounts/AIServices/agents/read`

VM runner identity was granted Foundry roles (`Azure AI Developer`, `Cognitive Services User`, `Azure AI Administrator`) at account/project scopes to unblock agent log retrieval for diagnosis.

## Latest execution update (2026-07-18, private preflight + IaC wiring hardening)

## Latest execution update (2026-07-18, private deploy gate green + Foundry eval run completed and populated)

### Final validation run

1. Workflow: `.github/workflows/foundry-deploy.yml`
2. Run: `29663475651`
3. Result: success (deploy + smoke + hosted E2E + report-only eval + artifact upload)
4. Artifact: `foundry-eval-29663475651-1`

### Foundry eval evidence

Report emitted by `backend/evals/foundry_eval_runner.py` in the run:

- `status`: `completed`
- `eval_id`: `eval_c545af3ae3764260b7fe4217a2541d8e`
- `run_id`: `evalrun_ec39c2c140b746959e6a3621205c87a0`
- `report_url`: `https://maffndai4aiw7fw5gjdo4.services.ai.azure.com/api/projects/order-resolution/evaluation/evaluations/eval_c545af3ae3764260b7fe4217a2541d8e/runs/evalrun_ec39c2c140b746959e6a3621205c87a0`
- `result_counts`: `total=10`, `errored=10`, `passed=0`, `failed=0`, `skipped=0`

This confirms Foundry eval runs are now being created and reaching completed state in private-lane CI; remaining quality work is evaluator-item diagnostics (errors inside completed eval run), not deploy-gate execution wiring.

## Latest execution update (2026-07-18, Foundry eval population verified + storage-permission RBAC closure via IaC)

### What was verified

1. Private deploy run `29661230552` completed deploy + smoke + hosted E2E and executed the Foundry report-only eval step.
2. Eval artifact was published:
   - artifact: `foundry-eval-29661230552-1`
   - report file: `backend/.foundry/results/foundry-report.json`
3. Foundry eval run metadata was populated:
   - `eval_id`: `eval_8b0feaefdaf8473485a97c62eb7b82ec`
   - `run_id`: `evalrun_8d34b7dc88304eb089b34ff05929e8c6`
   - `report_url`: `https://maffndai4aiw7fw5gjdo4.services.ai.azure.com/api/projects/order-resolution/evaluation/evaluations/eval_8b0feaefdaf8473485a97c62eb7b82ec/runs/evalrun_8d34b7dc88304eb089b34ff05929e8c6`

### Remaining failure cause from report

Foundry eval status was `failed` with 403:

- `UserError/Auth/Authorization/ResourceMsiTokenDoesntHavePermissionsOnStorage`
- message identifies project MSI permissions on storage account `maffndst4aiw7fw5gjdo4`.

### IaC fix applied (no ad-hoc permission mutation)

Updated `infra/foundry-hosted/iac/main.bicep` to assign storage-account RBAC through IaC to both identities involved in hosted/eval paths:

1. existing: project identity -> Storage Blob Data Contributor
2. added: Foundry account identity -> Storage Blob Data Contributor

Also expanded `infra/foundry-hosted/iac/modules/azure-storage-account-role-assignment.bicep` so each assigned identity gets both:

- `Storage Blob Data Contributor`
- `Storage Account Contributor`

The new module dependency is wired into project capability-host creation ordering so provisioning remains deterministic.

### Re-validation after IaC permission updates

1. Provision rerun (IaC applied): `29661812852` -> success.
2. Deploy + smoke + hosted E2E + eval rerun: `29661920808` -> workflow success, eval artifact published.
3. Foundry eval still reports the same 403 (`ResourceMsiTokenDoesntHavePermissionsOnStorage`) for:
   - `eval_id`: `eval_543158136bf5477e9cdf212d50a224b6`
   - `run_id`: `evalrun_0a1139eb458b482181800be57dfbf49c`
4. Post-provision RBAC checks now confirm both project/account identities have expected storage roles at account scope, so this failure is not due to missing IaC role assignment entries.

### Follow-up IaC change for private lane eval ingress

Given RBAC was present but eval still failed with `temporaryDataReference/createOrGet` 403, we added a network-path correction in IaC for storage:

1. `infra/foundry-hosted/iac/main.bicep` storage account now keeps private-endpoint topology while setting:
   - `publicNetworkAccess: Enabled`
   - private mode `networkAcls.defaultAction: Deny`
   - private mode `networkAcls.bypass: AzureServices`
2. This preserves deny-by-default network ACLs for public clients and allows trusted Azure service ingress required by Foundry cloud-eval assetstore staging.

### Re-test result after ingress correction

1. Deploy rerun `29662436805` completed deploy + smoke + hosted E2E.
2. Foundry report-only eval no longer returned `ResourceMsiTokenDoesntHavePermissionsOnStorage` 403.
3. New eval outcome switched to timeout (`Foundry eval run timed out after 300.0 seconds`), indicating storage-auth blocker is resolved and remaining issue is runtime duration.
4. Updated eval timeout contract:
   - `backend/eval.yaml` `foundry.timeout` increased to `900`
   - `backend/evals/foundry_eval_runner.py` now supports env overrides:
     - `FOUNDRY_EVAL_TIMEOUT`
     - `FOUNDRY_EVAL_POLL_INTERVAL`

### Report-only gate behavior hardening

To keep deploy gates non-blocking while still publishing Foundry eval evidence:

1. `backend/evals/foundry_eval_runner.py` now always writes a report and exits successfully in report-only mode, including when cloud eval status is delayed/timeout.
2. Timeout now records structured payload (`status: timeout`, `eval_id`, `run_id`, `report_url`, `run_status`) instead of failing the workflow step.
3. Strict failure remains available via `FOUNDRY_EVAL_ENFORCE_PASS=true`.

## Latest execution update (2026-07-18, eval architecture execution: deterministic + Foundry report gate)

### What changed

Implemented the eval plan end-to-end on the canonical `.foundry` surfaces (no duplicate eval tree):

1. Expanded canonical dataset:
   - `backend/.foundry/datasets/order-resolution-hosted-cases.jsonl`
   - added explicit expectations for order/policy/action/amount, terminal status, approve/reject decisions, explanation follow-up, and duplicate HITL idempotency checks.
2. Refactored deterministic eval harness:
   - `backend/evals/eval_runner.py`
   - now executes contract assertions across low-risk, high-risk approve/reject, explanation follow-up, and duplicate HITL response paths.
   - writes both deterministic verdicts and generated capture artifacts.
3. Added report-only Foundry eval runner:
   - `backend/evals/foundry_eval_runner.py`
   - reads `backend/eval.yaml`, runs Foundry evaluators against hosted target, and writes `backend/.foundry/results/foundry-report.json`.
4. Updated eval configuration and gate wiring:
   - `backend/eval.yaml` expanded to include deterministic + Foundry report settings.
   - `Makefile` adds `eval-foundry` and `eval-all`.
   - `.github/workflows/foundry-deploy.yml` adds optional post-E2E report-only eval step + artifact upload (`foundry-report.json`, `report.json`, `contract_capture.json`).
5. Added repository skill and contract docs sync:
   - `.github/skills/foundry-agent-evaluation/SKILL.md`
   - `docs/design/engineering-operating-model.md`, `README.md`, `backend/README.md`,
     `.github/copilot-instructions.md`, `agents.md`, and
     `docs/design/hitl-approval-conditions.md`.

### Local validation evidence

1. `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable make test` -> passed (`89 passed`).
2. `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable make eval-backend` -> passed (`10/10` cases, `100%`).
3. `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable make test-e2e` -> passed (`7 passed`).
4. `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable ./scripts/skills/design-review-skill.sh` -> passed.

### Notes

- Foundry eval remains report-only by default; blocking behavior is opt-in via `FOUNDRY_EVAL_ENFORCE_PASS=true`.
- Workflow now publishes eval artifacts on deploy runs when `run_eval=true`.

## Latest execution update (2026-07-18, operating-model private-lane contract alignment)

### What changed

Aligned operating-model contract wording to the current execution policy: hosted gates are private-lane-first.

Updated:

1. `docs/design/engineering-operating-model.md`
   - added explicit **Current lane policy** section
   - changed MAF/Foundry runtime hosted gate row from public lane wording to private lane wording
2. `.github/copilot-instructions.md`
   - added private-lane-first hosted gate posture note
3. `agents.md`
   - added matching private-lane-first hosted gate posture note

### Why

Current validated release evidence and workflow execution are on the private Foundry path. The contract now reflects actual required gate behavior and avoids ambiguity between public/private hosted lanes.

## Latest execution update (2026-07-18, private deploy + smoke + hosted E2E + telemetry confirmation)

### Run executed

- Workflow: `.github/workflows/foundry-deploy.yml`
- Run: `29653898864`
- Job: `88104766075`
- Result: `success`

### Use-case validation

Smoke step passed both baseline scenarios:

1. `Resolve delayed order ORD-1001` -> completed, no HITL
2. `Resolve delayed order ORD-1009` -> `waiting_approval` with `hitl.request` and checkpoint creation

Hosted E2E step also passed in the same run.

### App Insights telemetry confirmation

Verified against private component `maffnd-mon-4aiw7fw5gjdo4-appi` (`appId=f3bf2e8e-9ca7-433c-ab54-0a886618d564`):

1. Post-run volume since `2026-07-18T17:25:00Z`:
   - `traces`: `429`
   - `dependencies`: `140`
2. Smoke trace IDs from workflow logs are query-visible:
   - `f235b65a6398e7b9bc597ae7af5b0759` (ORD-1001)
   - `4f302f64f02f2b4459e5d20873f8b204` (ORD-1009)
3. End-to-end dependency graph entries present for those traces, including:
   - `foundry.responses.invoke`
   - `workflow.run`
   - `workflow.stage.triage.*`
   - `workflow.stage.policy_retrieval.*`
   - `invoke_agent PolicyAgent`
   - `invoke_agent ResolutionAgent`
   - outbound HTTP dependencies to `...services.ai.azure.com`
4. No exceptions for those smoke trace IDs in the same window.

## Latest execution update (2026-07-18, App Insights connection-string shape parity vs hosted-agent docs/samples)

### What was checked

1. Reviewed hosted-agent tutorial and Foundry samples for telemetry wiring guidance.
2. Verified current Foundry project connections in `rg-maf-ora-foundry-v2` and runtime env shaping.
3. Ran direct telemetry probes against `maffnd-mon-4aiw7fw5gjdo4-appi`.

### Findings

1. Official hosted guidance/samples expect `APPLICATIONINSIGHTS_CONNECTION_STRING` to be auto-injected when AppInsights project connection exists.
2. Current project has storage/cosmos/search/customkeys connections, but no AppInsights project connection.
3. Our private workflow was compacting the connection string to `InstrumentationKey=<key>` for both:
   - `APPLICATIONINSIGHTS_CONNECTION_STRING`
   - `APPINSIGHTS_CONNECTION_STRING`
4. `InstrumentationKey`-only works for ingestion API probes but breaks `azure.monitor.opentelemetry` exporter path with:
   - `Exporter is missing a valid region.`
   - no telemetry rows emitted for probe spans.

### Fixes applied

1. Updated `.github/workflows/foundry-deploy.yml` and `.github/workflows/foundry-provision.yml`:
   - preserve full region-aware connection string in `APPINSIGHTS_CONNECTION_STRING`
   - keep compact canonical value only in `APPLICATIONINSIGHTS_CONNECTION_STRING` for hosted AgentServer bootstrap compatibility
2. Updated `backend/app/core/telemetry.py`:
   - prefer full `APPINSIGHTS_CONNECTION_STRING` when it includes `IngestionEndpoint=...`
   - stop collapsing telemetry exporter connection strings down to instrumentation-key only
3. Added regression test:
   - `backend/tests/test_telemetry.py::test_setup_observability_prefers_full_alias_over_compact_canonical`

### Validation evidence

1. `backend/.venv/bin/pytest backend/tests/test_telemetry.py backend/tests/test_foundry_hosted.py` -> passed (40 tests).
2. Manual telemetry probes:
   - `v2/track` custom event -> `itemsAccepted=1`, query returned row in `customEvents`.
   - OpenTelemetry span with full connection string -> row observed in `dependencies`.
   - OpenTelemetry span with instrumentation-key-only string -> `Exporter is missing a valid region` and no query row (expected failure mode, now avoided by fix).

## Latest execution update (2026-07-18, deploy env bootstrap failure + deterministic Postgres name parsing fix)

### What failed

Private deploy-only run `29647407543` failed in `Select and configure azd environment` before deploy/smoke:

- `ERROR: environment 'foundry-private-env' does not exist: environment not found` (expected first-select miss before `azd env new`)
- immediate follow-on failure while resolving PostgreSQL FQDN:
  - `Unable to resolve PostgreSQL server '$postgres_server_name' in resource group rg-maf-ora-foundry-v2`

### Root cause

The workflow pulled PostgreSQL identifiers from AZD env values without sanitizing quoted/whitespace output. On new/rehydrated env bootstrap, this can produce invalid server-name input for `az postgres flexible-server show`, causing deterministic pre-deploy failure even though the server exists (`maffndpg7930`).

### Fixes applied

1. Hardened PostgreSQL env-value parsing in both workflows:
   - `.github/workflows/foundry-deploy.yml`
   - `.github/workflows/foundry-provision.yml`
2. Workflow now strips quotes and whitespace when reading:
   - `POSTGRES_SERVER_NAME`
   - `POSTGRES_ADMIN_USERNAME`
   - `POSTGRES_DATABASE_NAME`
3. This keeps env bootstrap deterministic and prevents false not-found failures on private lane reruns.

### Verification next step

Re-dispatch private `foundry-deploy.yml` (same branch, private profile) and confirm deploy progresses past env bootstrap into smoke + hosted E2E.

## Latest execution update (2026-07-18, empty env bootstrap on new AZD env + hard fallback seeding)

### What failed

Rerun `29647821492` still failed in `Select and configure azd environment`:

- `ERROR: environment 'foundry-private-env' does not exist: environment not found` (expected before `azd env new`)
- then immediate failure resolving DB server in the same step:
  - `Unable to resolve PostgreSQL server '$postgres_server_name' in resource group rg-maf-ora-foundry-v2`

### Root cause

On newly created/re-hydrated AZD envs, `azd env get-value POSTGRES_*` may return empty at first read even after initial env set operations. The workflow still depended on those reads to derive runtime DB URL, so it could fail with an empty `postgres_server_name`.

### Fixes applied

1. Added hard fallback defaults when any `POSTGRES_*` AZD lookup is empty:
   - `POSTGRES_SERVER_NAME` -> `maffndpg7930`
   - `POSTGRES_ADMIN_USERNAME` -> `pgadmin`
   - `POSTGRES_DATABASE_NAME` -> `maf_workflow`
2. Persisted fallback-resolved values back into AZD env immediately in both:
   - `.github/workflows/foundry-deploy.yml`
   - `.github/workflows/foundry-provision.yml`
3. This removes first-run AZD env race/drift and makes DB URL derivation deterministic on private reruns.

### Verification next step

Re-dispatch private deploy with `runner_label=foundry-private-v2`, then continue through smoke + hosted E2E + telemetry checks.

## Latest execution update (2026-07-18, shell unbound-variable fix in private env bootstrap)

### What failed

Run `29647939305` still failed in `Select and configure azd environment`, but root cause changed:

- shell error: `line 99: fMk3Cq58Itu4ALjqXMs: unbound variable`

### Root cause

The step used inline `${{ secrets.* }}` interpolation inside a `set -euo pipefail` bash block. A secret value containing `$...` was expanded as a shell variable reference, triggering `set -u` unbound-variable failure before deploy/smoke.

### Fixes applied

1. Moved secret ingestion to step-level `env` in both workflows:
   - `FOUNDRY_DATABASE_URL_SECRET`
   - `POSTGRES_ADMIN_PASSWORD_SECRET`
   - `APPLICATIONINSIGHTS_CONNECTION_STRING_SECRET`
2. Updated script reads to use `${ENV_VAR:-}` values instead of direct `${{ secrets.* }}` interpolation.
3. Kept existing deterministic PostgreSQL fallback seeding and persisted resolved `POSTGRES_*` values back into AZD env.

### Verification next step

Re-run private deploy from `feature/foundry-private-network-vnet` on `foundry-private-v2` and validate progression beyond env bootstrap into deploy/smoke/e2e.

## Latest execution update (2026-07-18, private telemetry bootstrap hardening)

### What failed

Deploy/smoke/e2e recovered in run `29648027673`, but telemetry verification remained empty when queried by the private v2 App Insights app.

### Root cause

Workflow fallback for `APPLICATIONINSIGHTS_CONNECTION_STRING` depended on:

- `az resource list --resource-type Microsoft.Insights/components --query [0]`

In this lane, that generic list path can return empty, leaving runtime telemetry connection string unset even though deterministic IaC-created App Insights exists in the RG.

### Fixes applied

1. Added deterministic private App Insights name resolution in deploy/provision workflows:
   - infer suffix from Foundry account name (`...ai<suffix>`)
   - resolve `maffnd-mon-<suffix>-appi` directly via:
     - `az monitor app-insights component show --app <name> --query connectionString`
2. Kept legacy generic `az resource list` fallback as secondary path.
3. This ensures runtime telemetry env seeding reliably binds to the IaC-created App Insights component for private lane runs.

### Verification next step

Re-run private deploy/smoke/e2e and verify recent telemetry rows in:

- `traces`, `requests`, `dependencies`, `exceptions`
- for the private v2 App Insights app id (`f3bf2e8e-9ca7-433c-ab54-0a886618d564`).

### Follow-up correction

- Private profile now **prefers deterministic IaC App Insights connection string**
  over environment secret value to prevent stale secret drift to old/deleted apps.
- Secret/variable/generic-list lookups remain as fallback for non-private paths.
- Deterministic lookup now resolves the App Insights connection string first via
  ARM resource query (`az resource show ... Microsoft.Insights/components`) so
  private workflow seeding does not depend on optional CLI extension behavior.
- Runtime telemetry bootstrap now accepts both `APPLICATIONINSIGHTS_CONNECTION_STRING`
  and `APPINSIGHTS_CONNECTION_STRING` env names (plus instrumentation-key fallback),
  and logs hosted startup observability status for deterministic diagnostics.
- Hosted logs now surfaced explicit telemetry parse failure:
  - `ValueError: Invalid connection string`
  - `appinsights_configured=False`
  which indicates stale/invalid private connection string injection. Private profile
  workflow now hard-fails when resolved App Insights connection string is missing or
  malformed (must contain `InstrumentationKey=`) rather than silently deploying.
- Final RCA refinement: Azure resource API returns App Insights connection strings
  with trailing semicolon; Azure AgentServer parser treats empty trailing segment as
  invalid (`dictionary update sequence element #0 has length 1`). Workflows now trim
  trailing semicolons/whitespace before seeding runtime env.
- Runtime telemetry setup now also normalizes the resolved App Insights connection
  string (`strip().rstrip(';')`) before calling Azure Monitor OpenTelemetry setup,
  covering APPINSIGHTS-only hosted environments where the value still includes a
  trailing semicolon.
- Runtime now canonicalizes App Insights input to `InstrumentationKey=<key>` when
  an instrumentation key is present, avoiding parser incompatibilities with
  extended connection-string variants emitted by hosted runtime surfaces.
- Direct ingestion probe to `maffnd-mon-4aiw7fw5gjdo4-appi` succeeded:
  - HTTP `200`
  - `itemsReceived=1`, `itemsAccepted=1`
  confirming target App Insights key/ingestion endpoint is valid.
- Private workflow now seeds compact App Insights format for hosted runtime:
  - `APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=<key>`
  - `APPINSIGHTS_CONNECTION_STRING=InstrumentationKey=<key>`
  to avoid AgentServer parser failures on extended connection-string variants.
- Root-cause fix in hosted runtime bootstrap:
  - `backend/foundry/main.py` now promotes `APPINSIGHTS_CONNECTION_STRING` to
    `APPLICATIONINSIGHTS_CONNECTION_STRING` (compact `InstrumentationKey=<uuid>`
    form) **before** `ResponsesAgentServerHost()` initializes AgentServer
    observability.
  - This directly addresses AgentServer b7 behavior, which reads only
    `APPLICATIONINSIGHTS_CONNECTION_STRING` during startup and throws
    `Invalid connection string` when it is empty.

### Validation after runtime alias promotion

- Branch commit: `e2074cb`
- Validation run: `29652488288` (private deploy + smoke + hosted E2E)
- Hosted runtime diagnostics now show:
  - `APPLICATIONINSIGHTS_CONNECTION_STRING` present (`InstrumentationKey=<uuid>`)
  - `APPINSIGHTS_CONNECTION_STRING` also present (platform-provided extended string)
  - `appinsights_configured=True`
  - `Invalid connection string` no longer appears in hosted runtime logs.
- Functional checks remain green in same run:
  - ORD-1001 no HITL path completed
  - ORD-1009 emitted `hitl.request`
  - hosted E2E passed
- Added hosted startup env diagnostics in `backend/foundry/main.py` (presence +
  placeholder detection, no secret values) for App Insights and DB env keys so
  future runs can prove whether runtime placeholder substitution is occurring.
- Diagnostics now emit explicit `HOSTED_ENV_DIAGNOSTIC` JSON to stderr to ensure
  visibility even when module logger level filters out `logger.info`.
- Diagnostic payload now includes structural metadata (`length`, segment counts,
  equals/semicolon counts) for connection-string shape validation without exposing
  secret content.

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

## Latest execution update (2026-07-21, private-branch cleanup to remove public/app-hosted surfaces)

### Goal

Keep this branch focused on:

- local end-to-end MAF workflow (`frontend` + `backend` + PostgreSQL), and
- retained private-VNet Foundry hosted lane for later deployment.

### Cleanup applied

1. Removed Azure app-hosted lane assets:
   - deleted `infra/azure-apphosted/**`
   - deleted `.github/workflows/azure-apphosted.yml`
2. Removed public Foundry deployment helpers and public profile artifacts:
   - deleted `scripts/foundry/deploy_public_dev.sh`
   - deleted `scripts/foundry/check_public_postgres_readiness.sh`
   - deleted `infra/foundry-hosted/iac/parameters.public-dev.json`
3. Removed hosted GitHub Actions deployment workflow set that carried public profile toggles:
   - deleted `.github/workflows/foundry-{provision,deploy,orchestrator,runner-probe}.yml`
4. Updated runtime/deploy wiring and docs for private-only posture:
   - `azure.yaml` now points to `infra/foundry-hosted/iac` and keeps only hosted agent service
   - `Makefile` removed public/app-hosted targets and scripts; parity target now runs `local foundry`
   - updated README/doc surfaces to remove Azure app-hosted/public lane instructions.
5. Private hosted runtime behavior tightened:
   - `backend/foundry/main.py` now always uses in-memory response storage for private-network safety.

### Outcome

The branch now removes public/app-hosted deploy surfaces and keeps the local + private-hosted path as the only active contract.

## Latest execution update (2026-07-21, private Foundry provision/deploy run from local host)

### Goal

Execute the requested full lane from this branch:

- Local E2E
- Foundry deployment path (IaC + deploy + hosted E2E + Foundry evals + App Insights checks)

### What succeeded

1. Local validation path:
   - `make test` passed
   - `make eval-backend` passed
   - `make test-e2e` passed (using compose runtime with in-network MCP URL `http://mock-mcp:8011/mcp`)
2. Azure validation path:
   - `az bicep build --file infra/foundry-hosted/iac/main.bicep` passed (warnings only)
   - `azd provision --preview` passed after seeding private env keys
3. Private IaC provisioning:
   - `make foundry-provision` eventually passed after:
     - setting `POSTGRES_ADMIN_PASSWORD` in `infra/foundry-hosted` azd env
     - rotating `POSTGRES_SERVER_NAME` to a unique value (`maffndpg07211051`) due global-name collision

### What failed / blocker

Hosted deploy and hosted eval/smoke from this developer machine fail with private endpoint access control:

- `make foundry-deploy` failed with `HTTP 403`:
  - `"Public access is disabled. Please configure private endpoint."`
- `make foundry-smoke` failed with the same `HTTP 403`.
- `make eval-foundry` produced report status `failed` with the same `HTTP 403` after model env vars were set.

### Root cause

The private Foundry project endpoint is reachable only from the private network path (in-VNet runner/VM). Running deploy/smoke/eval from this public workstation is blocked by design once public access is disabled.

### Changes made to support reproducible private provisioning

1. Fixed `scripts/foundry/ensure_foundry_azd_defaults.sh` so it can reliably seed missing azd env keys:
   - ignore empty default values instead of failing on empty assignments
   - treat missing `azd env get-value` keys correctly (without capturing azd error text as a value)
2. Seeded missing private env values (`AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP`, `NETWORK_MODE`, postgres/foundry defaults).

### Next action required

Run deploy/smoke/hosted E2E/foundry eval/telemetry validation from an in-VNet private runner VM (or equivalent private endpoint path), then collect App Insights evidence.

## Latest execution update (2026-07-21, private-runner rerun success + telemetry evidence)

### Deployment/e2e/eval rerun outcome

1. Reran Foundry orchestrator on `feature/foundry-private-network-vnet`:
   - run: `29848715851`
   - result: `success`
2. Prior failure cause was runtime DB bootstrap timeout in hosted container:
   - `psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec`
3. Fix applied before rerun:
   - started PostgreSQL server `maffndpg7930` in `rg-maf-ora-foundry-v2`
4. Successful rerun completed:
   - deploy hosted agent
   - smoke validation
   - hosted E2E validation
   - Foundry report-only evaluation + artifact upload

### App Insights / Log Analytics validation evidence

Workspace used: `maffnd-mon-4aiw7fw5gjdo4-law` (`2288ca32-1c34-4099-ab3b-886ae7a96be6`), lookback `2h`.

1. Row-volume query:
   - `AppDependenciesRows=779`
   - `AppTracesRows=2118`
   - `AppExceptionsRows=341`
   - `AppRequestsRows=0`
2. Workflow/HITL dependency spans observed:
   - `workflow.run=93`
   - `workflow.resolution_submit=5`
   - `workflow.workflow_output=3`
   - `workflow.hitl_resume=2`
   - `workflow.hitl_response=2`
3. HITL trace evidence in logs/traces:
   - `workflow.event` rows with `event.type="hitl.response"` and `workflow.thread_id` present.
4. Attribute hygiene:
   - `Invalid type NoneType for attribute` count = `0`.

### Open issue observed during eval telemetry window

AppExceptions include repeated rate-limit failures from Foundry model calls:

- `agent_framework.exceptions.ChatClientException`
- message: `Your requests to gpt-4o-mini for gpt-4o-mini in eastus2 have exceeded rate limit.`

This explains the `workflow.workflow_failed` dependency events in the same window and is now the primary remaining hosted quality issue (capacity/rate-limit), not deploy wiring or private network reachability.

## Latest execution update (2026-07-21, model capacity increase + rerun)

### Change applied

Raised Foundry chat deployment capacity for `gpt-4o-mini` in private lane account:

- account: `maffndai4aiw7fw5gjdo4`
- deployment: `gpt-4o-mini`
- capacity: `1 -> 3`
- effective limits after update:
  - requests/min: `30`
  - tokens/min: `3000`

### Rerun result

Reran orchestrator `29848715851` after the capacity increase.

- result: `success`
- completed stages: deploy hosted agent, smoke, hosted E2E, Foundry report-only eval, artifact upload
- eval report URL:
  - `https://maffndai4aiw7fw5gjdo4.services.ai.azure.com/api/projects/order-resolution/evaluation/evaluations/eval_878d2d76489d4691941cfbda3159e8c8/runs/evalrun_facb8bb19b4b4068a422a8e86a1a447b`

### Post-change telemetry spot-check

Lookback window: `45m` after capacity increase.

1. Rate-limit exceptions containing `exceeded rate limit`: `0`
2. `workflow.workflow_failed` dependency events: `0`
3. Positive workflow spans still present:
   - `workflow.resolution_submit=4`
   - `workflow.workflow_output=4`
   - `workflow.hitl_resume=2`
   - `workflow.hitl_response=2`

## Latest execution update (2026-07-22, private-branch verification + outstanding tasks)

### Verification scope

- branch: `feature/foundry-private-network-vnet`
- objective: verify this branch retains only private-lane hosted posture plus local MAF E2E path, and identify remaining work for IAC/deploy/E2E/evals/App Insights readiness.
- method: fleet-style parallel verification (surface audit + validation gate run) followed by rubber-duck challenge pass.

### Private-lane cleanup verification result

1. Confirmed removed surfaces in working tree:
   - `infra/azure-apphosted/**` removed
   - legacy/public-oriented workflow files removed (`.github/workflows/azure-apphosted.yml`, `foundry-deploy.yml`, `foundry-orchestrator.yml`, `foundry-provision.yml`, `foundry-runner-probe.yml`)
   - `infra/foundry-hosted/iac/parameters.public-dev.json` removed
   - `scripts/foundry/deploy_public_dev.sh` and `scripts/foundry/check_public_postgres_readiness.sh` removed
2. Active guidance remains private-lane-first in:
   - `README.md`
   - `backend/README.md`
   - `docs/design/engineering-operating-model.md`
   - `.github/copilot-instructions.md`
3. Residual public/app-hosted mentions found are archival/history-oriented:
   - `.azure/deployment-plan.md` (legacy app-hosted plan content)
   - historical entries in this file (`docs/design/issues-changes-fixes.md`)

### Validation run results (current environment)

1. `make test` -> **PASS** (`89` tests passed)
2. `make eval-backend` -> **PASS** (`10/10` deterministic eval cases)
3. `make test-e2e` -> **FAIL** (backend not running for Playwright base URL in this run context)
4. `make eval-foundry` -> **FAIL** (missing env vars: `FOUNDRY_PROJECTS_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`)
5. `./scripts/skills/design-review-skill.sh` -> **FAIL** (same E2E backend availability blocker)

### IAC static verification result

- `az bicep build --file infra/foundry-hosted/iac/main.bicep` -> **PASS** (non-blocking linter warnings only)

### Rubber-duck review findings (high-signal)

1. Verification should be considered against a reviewable commit/diff, not only a dirty working tree snapshot.
2. `infra/foundry-hosted/iac/main.bicep` keeps storage account `publicNetworkAccess: 'Enabled'` with `networkAcls` deny+AzureServices bypass in private mode; this is an intentional exception and should remain explicitly documented/accepted as risk posture.
3. E2E failure must be root-caused to environment/startup availability vs branch regressions before sign-off.

### Outstanding tasks (autopilot handoff)

1. **E2E gate closure**
   - run backend/frontend in deterministic local mode and rerun `make test-e2e` until green.
   - rerun `./scripts/skills/design-review-skill.sh` after E2E pass.
2. **Foundry eval closure (private lane)**
   - set `FOUNDRY_PROJECTS_ENDPOINT` + `FOUNDRY_MODEL_DEPLOYMENT_NAME` (and related hosted env vars as needed) and rerun `make eval-foundry`.
3. **Deploy/telemetry refresh evidence**
   - run private-lane hosted deploy path and append current run IDs + App Insights query evidence for this branch tip.
4. **Archival public-doc decision**
   - decide whether to keep `.azure/deployment-plan.md` as legacy archive or replace it with a private-lane-only deployment/validation plan.

## Latest execution update (2026-07-22, autopilot fix pass: e2e + private workflow restore)

### Fixes applied

1. **E2E harness hardening in `Makefile`**
   - `make test-e2e` now launches an isolated local backend on a random port with deterministic local settings.
   - frontend Vite launch now sets both:
     - `VITE_PROXY_TARGET=http://127.0.0.1:<backend_port>`
     - `VITE_API_BASE=http://127.0.0.1:<backend_port>`
   - this prevents accidental use of an unrelated backend on `localhost:8000` and removes false negatives from stale runtime sessions.
2. **Foundry eval env alias loading in `Makefile`**
   - `make eval-foundry` now auto-loads private AZD env (`infra/foundry-hosted/.azure/foundry-private-env/.env`) when present.
   - canonical eval env vars are inferred from hosted aliases when needed:
     - `FOUNDRY_PROJECT_ENDPOINT` -> `FOUNDRY_PROJECTS_ENDPOINT`
     - `AZURE_AI_MODEL_DEPLOYMENT_NAME` -> `FOUNDRY_MODEL_DEPLOYMENT_NAME`
3. **Private deployment workflow restoration**
   - restored private-lane-only GitHub workflows (without public profile branches):
     - `.github/workflows/foundry-provision.yml`
     - `.github/workflows/foundry-deploy.yml`
     - `.github/workflows/foundry-orchestrator.yml`
     - `.github/workflows/foundry-runner-probe.yml`
   - retained deletion of `.github/workflows/azure-apphosted.yml`.

### Validation results after fixes

1. `make test` -> **PASS**
2. `make eval-backend` -> **PASS** (`10/10`)
3. `make test-e2e` -> **PASS** (`7/7`)
4. `./scripts/skills/design-review-skill.sh` -> **PASS**
5. `make eval-foundry` -> runs and writes report, but status remains:
   - `failed`
   - error: `403 Access denied due to Virtual Network/Firewall rules.`

### Current blockers / outstanding tasks

1. **Run private-lane deploy/eval from inside private network runner**
   - local execution outside private VNET is expected to hit `403`.
   - execute via restored private workflows on `foundry-private` runner.
2. **Runner readiness**
   - verify private self-hosted runner is online before dispatching orchestration/deploy/eval.
3. **Hosted telemetry evidence refresh**
   - after a successful private workflow run, append current deploy run IDs, hosted E2E proof, Foundry eval artifact URL, and App Insights query evidence.

## Latest execution update (2026-07-22, private V2 runner lane execution)

### Environment and runner targeting

1. Repointed private AZD environment context to V2 RG:
   - `AZURE_RESOURCE_GROUP=rg-maf-ora-foundry-v2`
2. Verified GitHub runner availability:
   - online: `vm-maffnd-runner-v2-foundry-private` (labels include `foundry-private-v2`)
   - offline: `vm-maforani-runner-foundry-private`

### Workflow dispatches and outcomes

1. **Run `29941873552`** (orchestrator, deploy-only path on `foundry-private-v2`) -> **failed**
   - failure step: Smoke validation
   - root cause from hosted runtime logs:
     - `psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec`
2. Investigated V2 RG runtime dependency state:
   - PostgreSQL server `maffndpg7930` in `rg-maf-ora-foundry-v2` was `Stopped`.
3. Started PostgreSQL server:
   - `az postgres flexible-server start -g rg-maf-ora-foundry-v2 -n maffndpg7930`
   - post-check state: `Ready`
4. **Run `29942484645`** (same orchestrator inputs) -> **success**
   - deploy: success
   - smoke: success
   - hosted E2E: success
   - Foundry eval step: completed but report status timed out (see below)

### Foundry eval artifact evidence (run `29942484645`)

Artifact:
- `foundry-eval-29942484645-1/foundry-report.json`

Report summary:
- `status`: `timeout`
- `error`: `Foundry eval run timed out after 900.0 seconds`
- `eval_id`: `eval_d1fbff9a8a184cfd83f2520f6d4e6971`
- `run_id`: `evalrun_7de123dd55dd4aa09e1d4fd8ce0ef9b2`
- `report_url`:
  - `https://maffndai4aiw7fw5gjdo4.services.ai.azure.com/api/projects/order-resolution/evaluation/evaluations/eval_d1fbff9a8a184cfd83f2520f6d4e6971/runs/evalrun_7de123dd55dd4aa09e1d4fd8ce0ef9b2`

### App Insights / Log Analytics spot-check (RG V2 workspace)

Workspace:
- `maffnd-mon-4aiw7fw5gjdo4-law` (`2288ca32-1c34-4099-ab3b-886ae7a96be6`)

Lookback:
- `2h`

Observed:
1. Row volumes:
   - `AppDependenciesRows=362`
   - `AppTracesRows=963`
   - `AppExceptionsRows=6`
   - `AppRequestsRows=0`
2. Workflow dependency spans present:
   - `workflow.run=20`
   - `workflow.resolution_submit=4`
   - `workflow.workflow_output=4`
   - `workflow.hitl_resume=2`
   - `workflow.hitl_response=2`
3. `workflow.workflow_failed` dependency events:
   - `2`
4. Recent exceptions (same window):
   - `requests.exceptions.ConnectionError` (6 rows, during rollout window)

### Remaining follow-ups

1. Foundry eval run timeout requires follow-up (reduce evaluation scope and/or rerun with tuned timeout/profile on private runner).
2. Continue telemetry monitoring after next eval rerun to confirm no recurring `workflow.workflow_failed` spikes.

## Latest execution update (2026-07-22, capacity check + scale-up)

### Capacity checks performed

1. Subscription/region quota checks:
   - `az quota list` for `Microsoft.CognitiveServices` in `eastus2` returns `BadRequest` (known API limitation for this provider).
   - used `az cognitiveservices usage list -l eastus2` as fallback.
2. Relevant OpenAI quota headroom before changes:
   - `OpenAI.GlobalStandard.gpt-4o-mini`: `current=12`, `limit=6000`
   - `OpenAI.GlobalStandard.text-embedding-3-small`: `current=256`, `limit=3000`
   - result: **regional quota was not saturated**.
3. Deployment-level capacity was low relative to workload:
   - `gpt-4o-mini`: capacity `3`, limits `30 RPM / 3000 TPM`
   - `text-embedding-3-small`: capacity `1`, limits `1 req/10s / 1000 TPM`

### Capacity increases applied (RG V2)

Updated account: `maffndai4aiw7fw5gjdo4` (`rg-maf-ora-foundry-v2`)

1. `gpt-4o-mini`:
   - capacity `3 -> 6`
   - effective limits `30 RPM / 3000 TPM -> 60 RPM / 6000 TPM`
2. `text-embedding-3-small`:
   - capacity `1 -> 2`
   - effective limits `1 req/10s / 1000 TPM -> 2 req/10s / 2000 TPM`

### Post-scale validation run

Dispatched private runner workflow:
- run: `29944660113` (`foundry-deploy.yml`, `foundry-private-v2`, eval enabled)
- workflow result: `success`
- eval artifact report (`foundry-eval-29944660113-1/foundry-report.json`) status:
  - `timeout`
  - `eval_id=eval_bb1487ede79e4a77bebb591ebe6c8d43`
  - `run_id=evalrun_119d23ba341c4b9dade34265e771a071`

### Conclusion

Capacity was increased and quota headroom is healthy, but eval timeout persists.  
Current evidence indicates the timeout is **not solely a quota/capacity constraint** and needs eval-runner/workflow tuning (timeout/query count/evaluator set) in the next pass.

## Latest execution update (2026-07-22, private-lane reference cleanup before push)

### Removed residual public/app-hosted lane assets

1. Deleted app-hosted/public deployment surfaces that should not exist in this branch:
   - `infra/azure-apphosted/**`
   - `.github/workflows/azure-apphosted.yml`
   - `scripts/foundry/deploy_public_dev.sh`
   - `scripts/foundry/check_public_postgres_readiness.sh`
   - `infra/foundry-hosted/iac/parameters.public-dev.json`
2. Removed transitional archival doc with app-hosted/public lane content:
   - `docs/design/local-azure-foundry-decisions.md`

### Private-only contract tightening

1. Updated hosted IaC network-mode allowed values to private-only:
   - `infra/foundry-hosted/iac/main.bicep`
   - `infra/foundry-hosted/iac/main.json`
2. Updated hosted test coverage to remove explicit public-profile parameterization:
   - `backend/tests/test_foundry_hosted.py`
3. Removed remaining app-hosted/public lane wording from active docs:
   - `README.md`
   - `scripts/README.md`
   - `docs/design/engineering-operating-model.md`

### Post-cleanup scan status

1. No active repo assets remain for the public/app-hosted deployment lane.
2. Residual public/app-hosted text matches are limited to:
   - historical execution log entries in this file
   - vendored skill metadata under `.github/skills/*`
