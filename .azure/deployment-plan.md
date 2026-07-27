# Azure Deployment Plan

## Status

**Deployed and validated.** Local tests, deterministic evaluation, container
E2E, design-review, Bicep compilation, and the `azd provision --preview` plan
passed. `azd provision` and `azd deploy` created the target below; smoke,
hosted UI parity, report-only evaluation, and Application Insights correlation
validation also passed.

## Scope

Deploy the existing application as one Azure Container Apps package:

- React frontend Container App;
- FastAPI application Container App, which is the sole MAF workflow host;
- Azure Database for PostgreSQL Flexible Server for durable workflow state;
- ACR, Log Analytics, and Application Insights;
- Azure AI Foundry model deployments for application inference and report-only
  evaluation.

Foundry's only roles are model inference and report-only evaluation. Do not add
a Foundry application runtime or an alternate orchestration path.

## Target

| Setting | Value |
| --- | --- |
| Resource group | `rg-maf-ora-azure` |
| AZD environment | `maf-ora-azure` |
| Region | `North Central US` (`northcentralus`) |
| Deployment package | `infra/azure-apphosted/iac` |
| Frontend | `https://maf-frontend-puzsry.kindpebble-e634081a.northcentralus.azurecontainerapps.io` |
| Backend API | `https://maf-backend-puzsry.kindpebble-e634081a.northcentralus.azurecontainerapps.io` |

North Central US is the target because this subscription has an Azure
PostgreSQL offer restriction in East US. Do not substitute East US without a
fresh PostgreSQL availability check.

## Runtime and contracts

- `backend/app/main.py` serves the FastAPI API and runs the MAF workflow.
- The frontend consumes the existing API and native SSE event types:
  `workflow.stage`, `tool.call`, `checkpoint.created`, `hitl.request`,
  `hitl.response`, and `workflow.output`.
- PostgreSQL stores workflow runs, events, sessions, checkpoints, and
  approvals. HITL remains deterministic and resumable.
- The backend uses managed identity for Azure PostgreSQL and Foundry model
  access. Model configuration is `FOUNDRY_PROJECTS_ENDPOINT`,
  `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and
  `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`.
- Missing model configuration may use the existing deterministic triage summary;
  it must not create a second orchestration path.
- `make eval-foundry` is a non-blocking, report-only evaluation of FastAPI
  workflow captures. `make eval-backend` remains the deterministic contract
  gate.

## Preparation

Create an environment that produces the target resource group:

```bash
azd env new maf-ora-azure
azd env set AZURE_LOCATION northcentralus
azd env set POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME '<admin-upn-or-group-name>'
azd env set POSTGRES_ENTRA_ADMIN_PRINCIPAL_ID '<admin-or-group-object-id>'
azd env set POSTGRES_BOOTSTRAP_ALLOWED_IP '<azd-runner-public-ipv4>'
```

`POSTGRES_BOOTSTRAP_ALLOWED_IP` is required by the post-provision Entra grant
hook. Keep credentials and MCP secrets out of source and environment exports.

## Validation required before deployment

This plan becomes **Validated** only after the current code and IaC have fresh
validation evidence.

1. `make test`
2. `make eval-backend`
3. `make test-e2e`
4. `make docker-test`
5. `./scripts/skills/design-review-skill.sh`
6. Bicep/AZD validation for `infra/azure-apphosted/iac`
7. `iac-review`, then `azure-validation`

Only after those checks pass may an authorized deployment use `azd provision`
and `azd deploy`. After deployment, run the app-hosted smoke test, endpoint
parity as applicable, `make eval-foundry`, and telemetry validation before
recording release evidence.

## Acceptance criteria

- The resource group is `rg-maf-ora-azure` in North Central US.
- The FastAPI Container App remains the only MAF application host.
- Foundry use is limited to model inference and report-only evaluation.
- Existing HTTP, HITL, native SSE, and persistence contracts remain unchanged.
- Validation and deployment evidence is recorded only after it is produced.

## Delivered evidence

- `infra/azure-apphosted/runtime/smoke-test.sh` passed with
  `EXPECT_TRIAGE_MODE=foundry_models`.
- Hosted `make test-e2e` passed all seven UI scenarios through the frontend
  same-origin proxy.
- The report-only evaluation completed with 2/2 results:
  `eval_22c4c2907a2f41d5b5bee16b29c3c8e1` /
  `evalrun_0bb58b54d5a2478d8e16ad8a7bf900c6`.
- Application Insights contains a correlated HITL approval run for thread
  `c45816a3-755e-43c0-8b06-f937c07c1873`: `workflow.run`,
  `workflow.hitl_waiting`, `workflow.hitl_request`,
  `workflow.hitl_resume`, and `workflow.hitl_response` share operation
  `03634dec325b1a2cbe699f54c57dc3c0`. The validation query found no workflow
  exceptions or `Invalid type NoneType for attribute` traces.
