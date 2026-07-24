# Azure Deployment Plan

> **Status:** Validated for authenticated private release; deployment is pending.
> The IaC explicitly preserves private Storage/Cosmos networking and Cosmos
> automatic failover; the corrected authenticated preview passed without either
> unsafe change.

Current target (2026-07-24):

- AZD project: `infra/foundry-hosted`
- AZD environment: `foundry-private-env`
- GitHub environment: `foundry-private-env`
- private runner label: `foundry-private-v2`
- resource group: `rg-maf-ora-foundry-v2`
- location: `eastus2` with PostgreSQL in `centralus`
- latest recorded canonical PostgreSQL server:
  `maffndpgv20722.postgres.database.azure.com`; release preflight remains the
  authority and requires `RUNTIME_DATABASE_URL` to match the current
  `POSTGRES_SERVER_NAME` FQDN exactly
- deployment path: local preflight -> non-mutating private provision preview ->
  private provision -> backend/frontend ACA deploy -> optional hosted-agent refresh
  -> ACA/hosted PostgreSQL connectivity proof -> explicit PostgreSQL public-access
  lockdown -> hosted E2E evidence -> Foundry conversation trace evaluation ->
  correlated Application Insights verification
- telemetry source: supported Foundry `ApplicationInsights` project connection;
  no manual hosted connection-string aliases or fallback payloads

Private web extension (2026-07-24):

- one VNet-integrated Container Apps environment on a dedicated
  `snet-container-apps` subnet;
- external frontend ACA only, with same-origin `/api` and SSE proxying;
- internal FastAPI ACA with managed-identity access to private Foundry
  Responses and PostgreSQL;
- PostgreSQL private endpoint and
  `privatelink.postgres.database.azure.com` DNS are provisioned first;
- `scripts/foundry/harden_postgres_private_access.sh` disables PostgreSQL public
  access and removes `allow-azure-services` only after
  `private-connectivity-proof.json` records ACA and hosted-agent private
  database connectivity for the canonical FQDN. The proof is fresh for at most
  one hour by default, and lockdown also verifies the approved
  `postgresqlServer` private endpoint and its private-DNS record.
- GitHub Actions PR/static validation is credential-free. Protected manual
  provision/deploy dispatches use Azure OIDC only on
  `self-hosted,foundry-private-v2` in `foundry-private-env`; the runner retains
  the selected AZD environment and no Azure or database secret is in workflow
  configuration. The local `make foundry-release` flow remains the full
  provision, proof, lockdown, and evidence path.

The corrected authenticated 2026-07-24 preview plans the frontend/backend ACA,
ACA environment, PostgreSQL private endpoint, and VNet subnet additions. It
keeps Storage `publicNetworkAccess` disabled in private mode and Cosmos DB
`enableAutomaticFailover` true, matching the existing secure resources.

The older Azure Container Apps evidence below is retained as historical context;
it is not the target of this private Foundry deployment.

Validation evidence (2026-07-23):

- Bicep compilation passed.
- `azd provision --preview --no-prompt` passed in 43 seconds and planned creation
  of the `ApplicationInsights` project connection.
- private Foundry account has public access disabled, default network action
  `Deny`, and an approved private endpoint.
- `foundry-private-v2` runner is online and idle.
- PostgreSQL `maffndpgv20722` is `Ready` in `centralus`.
- local gates passed: 98 backend tests, 10/10 deterministic eval cases, 7/7
  Playwright tests, and the deterministic design-review gate.

Generated: 2026-06-10

---

## 1. Project Overview

**Goal:** Move the E2E-tested MAF order-resolution application from local scaffolding to an Azure app-hosted implementation with production-shaped infrastructure, CI/CD, Azure Container Apps, PostgreSQL, observability, and security controls.

**Path:** Modernize Existing

**Decision on compatibility shims:** Azure app-hosted parity and CI/CD are green, so legacy compatibility shims have been removed. Use only canonical backend namespaces going forward.

**Execution mode requested:** Build on autopilot, use fleet-style parallel implementation for independent workstreams, run rubber-duck review before validation handoff, then proceed through the required Azure sequence:

```text
azure-prepare implementation -> azure-validate -> azure-deploy
```

Deployment commands such as `azd up`, `azd deploy`, or `az deployment` should not be run during prepare. This plan will produce the IaC, app configuration, CI/CD, and validation-ready code first; deployment execution follows via the Azure deployment workflow after validation.

Current update note: Foundry Models client wiring, canonical Foundry env vars,
Application Insights/OpenTelemetry instrumentation, and MAF executor event
observation are implemented in code/IaC/docs. This update has passed Azure
validation, deployment, hosted parity, and Application Insights ingestion
checks.

Current follow-up note: HITL trace-correlation improvements add explicit
workflow/HITL/resolution spans, FastAPI request instrumentation, and a
post-deploy `azure-telemetry-validation` skill. Local validation and Azure
readiness validation passed on 2026-06-11T00:37:00Z; deployment and KQL
verification passed on 2026-06-11T01:10:00Z.

Current release note: shim removal, MAF middleware/rich events, and the
frontend Workflow History API proxy fix passed local validation, Bicep build,
`azd provision --preview`, `azd provision`, `azd deploy`, hosted smoke,
hosted Playwright UI parity, and App Insights KQL telemetry validation on
2026-06-11T15:10:00Z.

Foundry provisioning note: the Azure AI Foundry/Azure AI Services resource,
project, chat/embeddings model deployments, model-client endpoint outputs, and
backend/project managed identity RBAC are now provisioned in the `maf-ora-central`
Azure environment.

Rationale:

- Azure migration will touch Dockerfiles, runtime env, IaC, secrets, connection strings, ingress, health probes, CI/CD, and Postgres provider behavior.
- Shim removal was intentionally deferred until after Azure app-hosted parity was proven.
- Shims were internal compatibility surfaces and did not affect Azure runtime contracts while canonical imports remained documented and validated.
- Current state: parity is proven, shim paths are removed, and future work should not recreate or import legacy shim namespaces.

---

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | POC / Development moving toward production-shaped app-hosted path |
| Scale | Small |
| Budget | Cost-Optimized / Balanced |
| **Subscription** | ME-MngEnvMCAP328033-ppenumatsa-1 (`4f18d577-3506-4a11-85e5-a83b14727a84`) |
| **Planned Location** | `eastus2` |
| **Deployed Location** | `centralus` |

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| Backend API/workflow | API container | Python 3.12, FastAPI, MAF SDK, psycopg, OpenTelemetry | `backend/` |
| Frontend UI | Web container | React 18, Vite, TypeScript | `frontend/` |
| Workflow state | Database | PostgreSQL schema under `backend/app/sql/schema.sql` | Azure Database for PostgreSQL Flexible Server |
| RAG persistence | Database-backed local provider today | pgvector-compatible scaffold persisted in Postgres | Azure PostgreSQL first; Azure AI Search later |
| MCP integration | External HTTP integration | `MCP_SERVER_URL`, auth headers | Container App env/secrets |
| Manual/eval verification | Test assets | Playwright, pytest, eval JSONL | `scripts/playwright`, `backend/tests`, `backend/evals` |

---

## 4. Recipe Selection

**Selected:** AZD + Bicep + Azure Container Apps

**Rationale:**

- App is already containerized with backend/frontend Dockerfiles.
- Existing scaffold is Bicep under `infra/azure-apphosted`.
- Azure Container Apps is a good fit for a small API + frontend POC with HTTP ingress, revisions, managed identity, and Log Analytics.
- AZD gives a clean handoff path to `azure-validate` and later `azure-deploy`.

---

## 5. Architecture

**Stack:** Containers on Azure Container Apps

### Service Mapping

| Component | Azure Service | SKU / Shape |
|-----------|---------------|-------------|
| Backend API/workflow | Azure Container Apps | External ingress, target port 8000, min replicas 1 for demo stability |
| Frontend UI | Azure Container Apps | External ingress, target port 5173, production Nginx container serving the Vite build |
| Container images | Azure Container Registry | Basic |
| Workflow database | Azure Database for PostgreSQL Flexible Server | Burstable/dev SKU initially, TLS required |
| Secrets | Azure Key Vault | RBAC authorization, soft delete, purge protection |
| Logs | Log Analytics Workspace | 30-day retention initially |
| APM | Application Insights | Workspace-based |
| Identity | Managed Identity | System-assigned identity per Container App |

### Target Runtime Configuration

Backend:

- `APP_ENV=azure-apphosted`
- `WORKFLOW_MODE=maf_sdk`
- `STORE_PROVIDER=postgres` for first Azure cutover because runtime currently enforces Postgres-backed store behavior; later alias `azure_postgres` once provider switching is implemented.
- `RAG_PROVIDER=pgvector` for first Azure parity because it is currently fully wired and persisted in Postgres; later move to `azure_ai_search`.
- `MEMORY_PROVIDER=postgres`
- `DATABASE_URL` from Key Vault secret or Container Apps secret.
- `MCP_SERVER_URL`, `MCP_API_KEY`, `MCP_BEARER_TOKEN` from secrets only when real MCP is available.
- Foundry Models via non-secret `FOUNDRY_PROJECTS_ENDPOINT`,
  `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and
  `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`; missing Foundry config falls back only
  to deterministic triage summary, not a separate workflow path.
- OTEL/App Insights connection via `APPLICATIONINSIGHTS_CONNECTION_STRING`,
  with `ENABLE_TELEMETRY`, `ENABLE_INSTRUMENTATION`, and
  `OTEL_RECORD_CONTENT` controlling export, instrumentation, and content
  capture.

Frontend:

- Point browser API calls to the deployed backend URL.
- Preserve `/api` and `/health` behavior.

### Security Baseline

- No secrets in source, Bicep parameters, or GitHub Actions logs.
- Managed identities enabled for Container Apps.
- Key Vault RBAC with soft delete enabled for future secret externalization. The first cutover uses secure AZD/Bicep parameters mirrored into Container Apps secrets to avoid first-provision identity/Key Vault circular dependencies. Purge protection is not explicitly set in the POC/dev template; enable it for long-lived production environments.
- ACR pull via managed identity using `AcrPull`.
- PostgreSQL requires TLS.
- Public ingress only for frontend/backend endpoints needed for demo; database and Key Vault should be restricted as much as feasible for the selected environment.
- Diagnostic logs and Application Insights enabled.

---

## 6. Provisioning Limit Checklist

**Capacity validation method:** `az quota` could not be used because `Microsoft.Quota` is not registered in the subscription. Providers needed by this plan (`Microsoft.App`, `Microsoft.DBforPostgreSQL`, `Microsoft.ContainerRegistry`) are registered. Current resource counts were fetched with Azure Resource Graph; limits below are standard documented service limits / low-risk POC assumptions and must be rechecked with `az quota` after registering `Microsoft.Quota` or by `azure-validate`.

| Resource Type | Number to Deploy | Existing in `eastus2` | Total After Deployment | Limit/Quota | Notes |
|---------------|------------------|------------------------|------------------------|-------------|-------|
| `Microsoft.App/managedEnvironments` | 1 | 3 | 4 | Service limit expected above this POC usage | Resource Graph count; quota CLI unavailable due `Microsoft.Quota` registration |
| `Microsoft.App/containerApps` | 2 | 2 | 4 | Service limit expected above this POC usage | Backend + frontend |
| `Microsoft.ContainerRegistry/registries` | 1 | 3 | 4 | Standard subscription limits expected above this POC usage | Use Basic SKU |
| `Microsoft.DBforPostgreSQL/flexibleServers` | 1 | 0 | 1 | Standard subscription limits expected above this POC usage | Dev SKU |
| `Microsoft.KeyVault/vaults` | 1 | 0 | 1 | Standard subscription limits expected above this POC usage | RBAC + soft delete |
| `Microsoft.OperationalInsights/workspaces` | 1 | 4 | 5 | Standard subscription limits expected above this POC usage | 30-day retention |
| `Microsoft.Insights/components` | 1 | 3 | 4 | Standard subscription limits expected above this POC usage | Workspace-based App Insights |
| `Microsoft.CognitiveServices/accounts` | 1 | TBD | 1 | Requires target-region model availability/quota for selected deployments | `AIServices`/`S0`, local auth disabled |
| `Microsoft.CognitiveServices/accounts/projects` | 1 | TBD | 1 | Child project under generated Foundry/Azure AI Services account | App-hosted model client metadata |
| `Microsoft.CognitiveServices/accounts/deployments` | 2 | TBD | 2 | Chat + embeddings deployments; capacity defaults to 1 and is parameterized | Override model/SKU/version per region/quota |

**Status:** `eastus2` provisioning was blocked by Azure Database for PostgreSQL Flexible Server location offer restriction for this subscription. Deployment completed in `centralus`.

---

## 7. Execution Checklist

### Phase 1: Planning

- [x] Analyze workspace.
- [x] Gather requirements from README/docs/current infra.
- [x] Confirm subscription and location with user.
- [x] Prepare resource inventory.
- [x] Attempt quota validation and document fallback.
- [x] Scan codebase and current Azure scaffold.
- [x] Select recipe.
- [x] Plan architecture.
- [x] User approved this plan.

### Phase 2: Execution

- [x] Create root `azure.yaml` for AZD.
- [x] Promote `infra/azure-apphosted/iac` from scaffold to deployable Bicep.
- [x] Add modules/resources for ACR, Container Apps environment, backend ACA, frontend ACA, PostgreSQL Flexible Server, Key Vault, App Insights, Log Analytics, managed identities, role assignments, secrets, and outputs.
- [x] Add Azure AI Foundry/Azure AI Services account, project, chat deployment, embeddings deployment, model-client env outputs, and backend managed identity data-plane RBAC.
- [x] Update Dockerfiles for Azure runtime readiness:
  - backend health/port/runtime env
  - frontend production container or explicitly documented dev-server POC container
- [x] Implement Azure Postgres runtime configuration without changing workflow behavior.
- [x] Add GitHub Actions CI for lint/tests/evals/e2e and deployment validation.
- [x] Add GitHub Actions deployment workflow using OIDC/federated credentials or documented AZD auth.
- [x] Add smoke tests for deployed backend/frontend endpoints and ORD-1001/ORD-1009 parity.
- [x] Run fleet-style implementation streams where safe:
  - AZD/IaC generation
  - Docker/runtime configuration
  - CI/CD and smoke scripts
  - documentation updates
- [x] Add shim-removal guardrails:
  - keep shims for Azure implementation
  - prohibit new canonical code from importing shims
  - remove shims only after Azure parity is green
- [x] Update docs: README, backend README, infra README, manual testing, and implementation phases.
- [x] Run rubber-duck review and address material design or reliability issues.
- [x] Update plan status to `Ready for Validation`.

### Phase 3: Validation

- [x] Invoke `azure-validate`.
- [x] Validate Bicep/AZD syntax.
- [x] Validate Docker builds.
- [x] Validate security/secrets posture.
- [x] Validate local functional gates:
  - `make test`
  - `make eval-backend`
  - `make test-e2e`
  - `./scripts/skills/design-review-skill.sh`
- [x] Validate Azure smoke test plan.
- [x] Static RBAC verification:
  - backend Container App identity gets `AcrPull` scoped to ACR.
  - frontend Container App identity gets `AcrPull` scoped to ACR.
  - backend Container App identity gets `Cognitive Services OpenAI User` scoped to the generated Foundry/Azure AI Services account and `Foundry User` scoped to the generated project.
  - generated Foundry project identity gets `Foundry User` scoped to the generated Foundry/Azure AI Services account.
  - no broad `Owner`, `Contributor`, or subscription/resource-group-scoped runtime role assignments are generated.
- [x] Azure Policy validation:
  - policy assignments were listed successfully.
  - detailed read of management-group policy definition `Block Azure RM Resource Creation` failed due insufficient management-group permission.
  - subscription-scope ARM template validation and what-if both completed successfully under the target subscription/location, confirming no policy deny was raised for the planned deployment.

### Phase 4: Deployment

- [x] Invoke `azure-deploy`.
- [x] Deploy infrastructure and app images.
- [x] Run post-deploy smoke tests.
- [x] Record endpoint URLs and validation proof.

---

## 8. Validation Proof

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|-----------|
| AZD installation/auth | `azd version && azd auth login --check-status` | Passed: azd 1.25.2, logged in as `ppenumatsa@microsoft.com` | 2026-06-10T13:27:33-05:00 |
| AZD schema | Azure MCP `azd validate_azure_yaml` for `azure.yaml` | Passed | 2026-06-10T13:27:33-05:00 |
| AZD environment | `azd env new maf-order-resolution-validate --subscription 4f18d577-3506-4a11-85e5-a83b14727a84 --location eastus2 --no-prompt` and `azd env get-values` | Passed using validation-only environment and placeholder non-secret password | 2026-06-10T13:27:33-05:00 |
| Aspire check | `find . -name '*AppHost.csproj' -o -name '*.csproj' ...` | Passed: no Aspire markers found; Aspire checks skipped | 2026-06-10T13:27:33-05:00 |
| Provision preview | `azd provision --preview --no-prompt` | Passed: preview generated for RG, backend/frontend Container Apps, ACA environment, ACR, PostgreSQL, App Insights, Key Vault, Log Analytics | 2026-06-10T13:27:33-05:00 |
| Bicep build | `az bicep build --file infra/azure-apphosted/iac/main.bicep --stdout` | Passed | 2026-06-10T13:27:33-05:00 |
| Docker/package | `azd package --no-prompt` | Passed: backend and frontend packaged/tagged | 2026-06-10T13:27:33-05:00 |
| Frontend build | `npm --prefix frontend run build` | Passed | 2026-06-10T13:27:33-05:00 |
| Diff hygiene | `git --no-pager diff --check` | Passed | 2026-06-10T13:27:33-05:00 |
| Local deterministic gate | `./scripts/skills/design-review-skill.sh` | Passed: backend lint/tests, evals 10/10, rubric, Playwright E2E 3/3 | 2026-06-10T13:27:33-05:00 |
| Static RBAC verification | reviewed `infra/azure-apphosted/iac/**/*role*.bicep` and `main.bicep` role modules | Passed: only ACR `AcrPull` role assignments scoped to ACR for backend/frontend managed identities | 2026-06-10T13:27:33-05:00 |
| Azure Policy assignments | Azure MCP `policy_assignment_list` for subscription `4f18d577-3506-4a11-85e5-a83b14727a84` | Blocked: assignments listed, but management-group deny policy details cannot be inspected with current permissions | 2026-06-10T13:27:33-05:00 |
| Subscription template validation | `az deployment sub validate --location eastus2 --template-file infra/azure-apphosted/iac/main.bicep --parameters environmentName=maf-order-resolution-validate location=eastus2 namePrefix=maf-order-resolution-validate postgresAdministratorPassword=ValidationOnlyPassword123 mcpServerUrl='' mcpApiKey='' mcpBearerToken=''` | Passed: Azure accepted the subscription-scope template under current context | 2026-06-10T13:49:41-05:00 |
| Subscription what-if | `az deployment sub what-if --location eastus2 --template-file infra/azure-apphosted/iac/main.bicep --parameters environmentName=maf-order-resolution-validate location=eastus2 namePrefix=maf-order-resolution-validate postgresAdministratorPassword=ValidationOnlyPassword123 mcpServerUrl='' mcpApiKey='' mcpBearerToken=''` | Passed: planned 11 creates; 2 role assignment resources marked unsupported by what-if due runtime principal IDs; no policy deny surfaced | 2026-06-10T13:49:41-05:00 |
| Update provision preview | `azd provision --preview --no-prompt` in `maf-ora-central` / `centralus` | Passed: preview generated for existing RG, backend/frontend Container Apps, ACA environment, ACR, PostgreSQL, App Insights, Key Vault, Log Analytics | 2026-06-10T15:55:40-05:00 |
| Update Bicep build | `az bicep build --file infra/azure-apphosted/iac/main.bicep --stdout` | Passed | 2026-06-10T15:55:40-05:00 |
| Update package validation | `azd package --no-prompt` | Passed: backend and frontend packaged/tagged for `maf-ora-central` | 2026-06-10T15:55:40-05:00 |
| Update local deterministic gate | `make manual-matrix && make test && make eval-backend && ./scripts/skills/design-review-skill.sh` | Passed: manual matrix 10/10, backend tests 30/30, evals 10/10, rubric, Playwright E2E 5/5 | 2026-06-10T15:55:40-05:00 |
| Update Docker E2E | `PLAYWRIGHT_BASE_URL=http://localhost:5173 make test-e2e` after `docker compose up --build -d backend frontend` | Passed: Docker frontend served Manual Test Matrix panel and Playwright E2E 5/5 | 2026-06-10T15:55:40-05:00 |
| Existing hosted smoke | `infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"` | Passed: backend health, frontend health, ORD-1001 no-HITL output, ORD-1009 HITL request | 2026-06-10T15:55:40-05:00 |

**Validated by:** azure-validate skill
**Validation timestamp:** 2026-06-10T15:55:40-05:00
**Validation outcome:** Passed for the current update. Management-group policy definition details remain unreadable with current permissions, but Azure provisioning preview, Bicep build, package validation, local deterministic gates, Docker E2E, and existing hosted smoke checks succeeded for the deployed `centralus` target.

### Current Foundry Models + MAF telemetry update

The current code/IaC update is deployed to the `maf-ora-central` environment.
Local, Azure validation, hosted parity, and App Insights proof are recorded
below.

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|-----------|
| Bicep build | `az bicep build --file infra/azure-apphosted/iac/main.bicep --stdout` | Passed | 2026-06-10T16:58:28-05:00 |
| Backend lint/tests | `make test` | Passed: ruff clean; pytest 44/44 | 2026-06-10T16:58:28-05:00 |
| Eval harness | `make eval-backend` | Passed: 10/10 eval cases | 2026-06-10T16:58:28-05:00 |
| Playwright E2E | `make test-e2e` | Passed: 5/5 tests | 2026-06-10T16:58:28-05:00 |
| Design review gate | `./scripts/skills/design-review-skill.sh` | Passed: scope warning for pre-existing broad change set; format/lint/tests/evals/rubric/E2E passed | 2026-06-10T16:58:28-05:00 |
| Diff hygiene | `git --no-pager diff --check` | Passed | 2026-06-10T16:58:28-05:00 |
| Foundry Azure validation | `az bicep build --file infra/azure-apphosted/iac/main.bicep --stdout && azd provision --preview --no-prompt && azd package --no-prompt` | Passed after setting embeddings SKU to `GlobalStandard` for `centralus` | 2026-06-10T22:26:00Z |
| Foundry provision | `azd provision --no-prompt` | Passed: Azure AI Services account, Foundry project, chat deployment, embeddings deployment, Container Apps env/config, and Bicep-owned Foundry RBAC provisioned | 2026-06-10T23:20:00Z |
| Foundry deploy | `azd deploy --no-prompt` | Passed after explicit ACR registry binding recovery; IaC now declares Container App registry bindings | 2026-06-10T23:25:00Z |
| Foundry smoke | `EXPECT_TRIAGE_MODE=foundry_models infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"` | Passed: backend/frontend health, ORD-1001 no-HITL output, ORD-1009 HITL request, triage mode `foundry_models` | 2026-06-10T23:26:00Z |
| Hosted manual matrix | `MANUAL_MATRIX_ARGS="--request-timeout 120 --timeout 90 --case-delay 15" API_URL="$API_URL" make manual-matrix` | Passed: ORD-1001 through ORD-1010 all PASS with low-capacity Foundry throttling | 2026-06-10T23:34:00Z |
| Hosted Playwright parity | `PLAYWRIGHT_EXPECT_TIMEOUT_MS=60000 PLAYWRIGHT_TEST_TIMEOUT_MS=120000 PLAYWRIGHT_CASE_DELAY_MS=15000 PLAYWRIGHT_BASE_URL="$WEB_URL" make test-e2e` | Passed: 5/5 tests with low-capacity Foundry throttling | 2026-06-10T23:39:00Z |
| App Insights ingestion | `az monitor log-analytics query --workspace <customerId> --analytics-query '<workflow telemetry query>'` | Passed: recent workflow telemetry found in `AppDependencies` (194) and `AppTraces` (981) | 2026-06-10T23:36:00Z |
| HITL trace-correlation validation | `azd provision --preview --no-prompt && az bicep build --file infra/azure-apphosted/iac/main.bicep --stdout && azd package --no-prompt` | Passed: preview/build/package validated for `maf-ora-central` | 2026-06-11T00:37:00Z |
| HITL telemetry deployment | `azd provision --no-prompt && azd deploy --no-prompt` | Passed: backend/frontend deployed after frontend Nginx Azure-hostname fix | 2026-06-11T01:00:00Z |
| Final hosted smoke | `EXPECT_TRIAGE_MODE=foundry_models infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"` | Passed: backend/frontend health, ORD-1001 no-HITL, ORD-1009 HITL, Foundry triage mode | 2026-06-11T01:00:00Z |
| Final Container Apps revisions | `az containerapp revision list ...` | Passed: backend `maf-ora-central-backend-azv4nl--azd-1781139477` and frontend `maf-ora-central-frontend-azv4nl--azd-1781139493` healthy with 100% traffic | 2026-06-11T01:00:00Z |
| Final App Insights KQL | `az monitor log-analytics query --workspace e5b16f93-6d8e-4e5c-938e-70499e9dc8f7 --analytics-query '<telemetry validation KQL>'` | Passed: `AppRequests=45`, `AppDependencies=247`, `AppTraces=205`, `AppExceptions=0`; HITL confirm thread wait/request/resume/response/resolution spans share OperationId `7cfa69e7c6fd930836651a2e2d8e63f8`; `NoneTypeWarnings=0` after 2026-06-11T01:00:00Z | 2026-06-11T01:10:00Z |

## Role Assignment Verification

- Status: Verified for generated IaC.
- Identities checked: backend Container App system-assigned managed identity; frontend Container App system-assigned managed identity.
- Roles confirmed: `AcrPull` (`7f951dda-4ed3-4680-a7ca-43fe172d538d`) scoped to the generated Azure Container Registry for each Container App identity.
- Foundry roles confirmed: backend identity has `Cognitive Services OpenAI User` on the Foundry account and `Foundry User` on the Foundry project; project managed identity has `Foundry User` on the Foundry account.
- Issues: no generated runtime data-plane access currently depends on Key Vault or other Azure services; PostgreSQL uses connection string via Container Apps secret for first cutover. No broad `Owner`, `Contributor`, or `Reader` assignments are generated.

## Azure Policy Validation

- Status: Verified by subscription-scope validation and what-if.
- Subscription-scope policy assignments were retrieved successfully.
- Management-group assignments include `MCAPSGovDenyPolicies`, `MCAPSGovAuditPolicies`, `MCAPSGovDeployPolicies`, and `Block Azure RM Resource Creation`.
- Attempting to inspect the `Block Azure RM Resource Creation` assignment/definition directly with Azure CLI failed with `AuthorizationFailed` for `Microsoft.Authorization/policyAssignments/read` at the management-group scope.
- `azd provision --preview --no-prompt`, `az deployment sub validate`, and `az deployment sub what-if` succeeded for the planned resources. No deny-policy failure surfaced during validation.

---

## Deployment Proof

| Check | Command Run | Result | Timestamp |
|-------|-------------|--------|-----------|
| Initial provision attempt | `azd provision --no-prompt` in `maf-order-resolution-validate` / `eastus2` | Failed: Key Vault template rejected explicit `enablePurgeProtection: false`; PostgreSQL Flexible Server returned `LocationIsOfferRestricted` for `eastus2` | 2026-06-10T13:49:41-05:00 |
| Template fix | Removed explicit Key Vault purge-protection false setting and made Key Vault name suffix-preserving | Passed local Bicep validation | 2026-06-10T13:49:41-05:00 |
| Central US validation | `az deployment sub validate --location centralus ... environmentName=maf-ora-central` | Passed | 2026-06-10T13:49:41-05:00 |
| Provision | `azd provision --no-prompt` in `maf-ora-central` / `centralus` | Passed: resource group, ACR, Log Analytics, Key Vault, App Insights, Container Apps Environment, PostgreSQL, backend ACA, frontend ACA | 2026-06-10T13:49:41-05:00 |
| Pre-deploy RBAC | `az role assignment list --scope <acr-id> --assignee-object-id <principal-id>` | Passed: backend and frontend managed identities both have `AcrPull` on ACR | 2026-06-10T13:49:41-05:00 |
| First app deploy | `azd deploy --no-prompt` | Failed: Container Apps registry link missing despite `AcrPull` role assignment | 2026-06-10T13:49:41-05:00 |
| Registry link recovery | `az containerapp registry set --server maforacentralacrazv4nl.azurecr.io --identity system` for backend and frontend | Passed | 2026-06-10T13:49:41-05:00 |
| App deploy retry | `azd deploy --no-prompt` | Passed | 2026-06-10T13:49:41-05:00 |
| Endpoint discovery | `azd show` | Passed: backend/frontend endpoints returned | 2026-06-10T13:49:41-05:00 |
| Hosted smoke | `infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"` | Passed: backend health, frontend health, ORD-1001 no-HITL output, ORD-1009 HITL request | 2026-06-10T13:49:41-05:00 |
| Live RBAC | `az role assignment list` for backend/frontend identities scoped to ACR | Passed: both identities have `AcrPull` | 2026-06-10T13:49:41-05:00 |
| Update provision | `azd provision --no-prompt` in `maf-ora-central` / `centralus` | Passed: no infrastructure changes to provision | 2026-06-10T15:59:20-05:00 |
| Update live RBAC | `az role assignment list --scope <acr-id> --assignee-object-id <principal-id>` | Passed: backend and frontend managed identities both have `AcrPull` on ACR | 2026-06-10T15:59:20-05:00 |
| Update app deploy | `azd deploy --no-prompt` | Passed: backend/frontend images published and active revisions updated | 2026-06-10T15:59:20-05:00 |
| Update hosted smoke | `infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"` | Passed: backend health, frontend health, ORD-1001 no-HITL output, ORD-1009 HITL request | 2026-06-10T15:59:20-05:00 |
| Update hosted bundle | `curl "$WEB_URL/assets/index-DF8_ZLmk.js" | grep ...` | Passed: hosted frontend contains `Manual Test Matrix`, `Run all`, and `Load prompt` markers | 2026-06-10T15:59:20-05:00 |
| Update hosted manual matrix | `API_URL="$API_URL" make manual-matrix` | Passed: ORD-1001 through ORD-1010 all PASS | 2026-06-10T15:59:20-05:00 |
| Update hosted Playwright parity | `PLAYWRIGHT_BASE_URL="$WEB_URL" make test-e2e` | Passed: hosted Playwright E2E 5/5, including Manual Test Matrix panel | 2026-06-10T15:59:20-05:00 |

**Backend URL:** https://maf-ora-central-backend-azv4nl.icyglacier-d757678f.centralus.azurecontainerapps.io/

**Frontend URL:** https://maf-ora-central-frontend-azv4nl.icyglacier-d757678f.centralus.azurecontainerapps.io/

**Resource group:** `rg-maf-ora-central`

**Azure portal:** https://portal.azure.com/#@/resource/subscriptions/4f18d577-3506-4a11-85e5-a83b14727a84/resourceGroups/rg-maf-ora-central/overview

---

## 9. Files to Generate / Modify

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | This plan | ✅ |
| `azure.yaml` | AZD configuration | ✅ |
| `infra/azure-apphosted/iac/main.bicep` | Azure app-hosted infrastructure | ✅ |
| `infra/azure-apphosted/iac/modules/*.bicep` | Reusable infra modules | ✅ |
| `infra/azure-apphosted/runtime/*.sh` | Smoke/startup scripts | ✅ |
| `.github/workflows/*.yml` | CI/CD | ✅ |
| `backend/Dockerfile` | Backend container hardening | ✅ |
| `frontend/Dockerfile` | Frontend container hardening | ✅ |
| docs/README files | Operator guidance | ✅ |

---

## 10. Next Steps

Current phase: HITL trace-correlation telemetry update is locally validated,
deployed to `maf-ora-central`, smoke-tested, and App Insights KQL verified.
Earlier Azure app-hosted deployment proof is retained above as historical
evidence for the existing `centralus` environment.

1. Compatibility shims have been removed after Azure app-hosted parity and CI/CD stayed green; continue using only canonical backend namespaces.
2. Continue using `azure-telemetry-validation` after future hosted deployments to verify App Insights request, dependency, HITL correlation, warning, and exception data.
