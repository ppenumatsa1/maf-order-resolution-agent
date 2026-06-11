# Azure App-Hosted Deployment

This path prepares the current E2E-tested MAF order-resolution app for Azure app-hosted deployment with Azure Developer CLI, Bicep, Azure Container Apps, Azure PostgreSQL, Key Vault, ACR, Log Analytics, Application Insights, and Azure AI Foundry/Azure AI Services.

## Layout

- `iac/main.bicep`: AZD-compatible subscription-scope deployment entry point.
- `iac/main.parameters.json`: AZD parameter binding file.
- `iac/modules/*.bicep`: reusable Azure resource modules.
- `iac/parameters.dev.json`: sample parameters for direct Bicep experiments.
- `runtime/.env.example`: provider/env wiring for app-hosted mode.
- `runtime/entrypoint.sh`: backend runtime entrypoint for this path.
- `runtime/smoke-test.sh`: post-start smoke checks for backend/frontend and ORD-1001/ORD-1009 parity.

## Runtime wiring

The first Azure cutover keeps runtime behavior identical to the local MAF path:

- `WORKFLOW_MODE=maf_sdk`
- `STORE_PROVIDER=postgres`
- `RAG_PROVIDER=pgvector`
- `MEMORY_PROVIDER=postgres`
- `DATABASE_URL=...postgres.database.azure.com...?sslmode=require`
- `FOUNDRY_PROJECTS_ENDPOINT`
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`
- `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`
- `APPLICATIONINSIGHTS_CONNECTION_STRING`
- `ENABLE_TELEMETRY=true`
- `ENABLE_INSTRUMENTATION=true`
- `OTEL_RECORD_CONTENT=false`

`STORE_PROVIDER=azure_postgres` and `RAG_PROVIDER=azure_ai_search` remain future provider contracts, but they are not used for first Azure parity because provider switching and Azure AI Search retrieval are not fully wired yet.

The Bicep template also provisions a cost-conscious Foundry/Azure AI Services account (`AIServices`, `S0`), one project, a chat deployment, and an embeddings deployment. Model names, versions, deployment SKU names, deployment capacity, project name, and RAI policy name are Bicep parameters so deployments can be adjusted for target-region model availability and quota without changing the template.

The backend uses `DefaultAzureCredential` with the Container App managed
identity to call the Foundry Models project endpoint. If the Foundry env vars
are absent, the workflow keeps the same MAF path and uses deterministic triage
for local/CI parity. HITL approvals are never model-decided; deterministic
backend rules still gate checkpoints.

Application Insights export is configured through
`APPLICATIONINSIGHTS_CONNECTION_STRING`. MAF executor telemetry is based on
streamed workflow event observation (`executor_invoked`, `executor_completed`,
and `output`), with content redaction controlled by `OTEL_RECORD_CONTENT`.
FastAPI request telemetry is explicitly instrumented after app creation so
hosted API traffic should appear in `AppRequests`. Workflow, HITL, MAF
executor, and Foundry calls should appear in `AppDependencies`; HITL resume
uses checkpoint-persisted trace context to correlate approval spans with the
original waiting operation.

## Prepare

Create/select an AZD environment and set required values:

```bash
azd env new maf-order-resolution-dev
azd env set AZURE_LOCATION eastus2
azd env set POSTGRES_ADMIN_PASSWORD '<url-safe-strong-password>'
azd env set MCP_SERVER_URL ''
azd env set MCP_API_KEY ''
azd env set MCP_BEARER_TOKEN ''
```

Use a URL-safe PostgreSQL password because the current application receives a PostgreSQL URL. Avoid characters that require URL encoding until database URL construction is moved into application code.

The Bicep template intentionally omits Container Apps liveness/readiness probes during first provisioning. AZD provisions each Container App with a public placeholder image before `azd deploy` swaps in the real backend/frontend images; app-specific probes against ports 8000/5173 would fail against that placeholder revision. Runtime health is still validated by the backend/frontend `/health` endpoints and the hosted smoke script after deployment.

Key Vault is provisioned with RBAC and soft delete enabled for future secret externalization. The first cutover passes `DATABASE_URL` as a secure AZD/Bicep parameter into a Container Apps secret to avoid a first-provision identity/Key Vault circular dependency. Purge protection is not explicitly set in the POC/dev template; enable purge protection and move ACA secrets to Key Vault references for long-lived production environments.

The backend Container App system-assigned managed identity receives the built-in `Cognitive Services OpenAI User` role scoped to the generated Foundry/Azure AI Services account and `Foundry User` scoped to the generated project. The project managed identity receives `Foundry User` on the account. Local key authentication is disabled on the account, so backend model access should use managed identity.

## Validate before deploying

This repository follows:

```text
azure-prepare -> azure-validate -> azure-deploy
```

Do not run deployment commands directly during prepare. After the generated artifacts validate locally, `.azure/deployment-plan.md` is marked `Ready for Validation` and the Azure validation skill is invoked.

## Smoke-test expectation

`runtime/smoke-test.sh` expects:

1. `/health` returns `200`.
2. Low-risk `ORD-1001` request returns `workflow.output` and no `hitl.request`.
3. High-risk `ORD-1009` request emits `hitl.request`.
4. Optional `EXPECT_TRIAGE_MODE=foundry_models` validates that emitted triage
   stage metadata is using the Foundry model-client path.

Example after deployment:

```bash
EXPECT_TRIAGE_MODE=foundry_models infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"
```

After smoke checks, run the `azure-telemetry-validation` skill to query the
Application Insights workspace and confirm request rows, workflow/HITL
dependency spans, trace hygiene, and absence of new workflow exceptions.
