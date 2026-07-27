# Azure App-Hosted Package

This is the only Azure deployment package. It deploys the React frontend and
FastAPI/MAF backend as Container Apps, with PostgreSQL, ACR, Log Analytics,
Application Insights, and Foundry model/evaluation resources.

FastAPI remains the sole application host. Foundry is limited to model
inference and report-only evaluation; do not add agent, Responses, manifest,
runner, or other application-hosting surfaces.

## Status and target

**Deployed.** Post-deployment smoke, hosted UI parity, and report-only
evaluation use the environment outputs described in `.azure/deployment-plan.md`.

| Setting | Value |
| --- | --- |
| Resource group | `rg-maf-ora-azure` |
| AZD environment | `maf-ora-azure` |
| Region | North Central US (`northcentralus`) |

North Central US is required because Azure PostgreSQL is offer-restricted in
East US for this target.

## Layout

- `iac/main.bicep`: subscription-scope AZD entry point.
- `iac/modules/`: Azure resource modules.
- `iac/main.parameters.json`: AZD parameter binding.
- `runtime/.env.example`: app-hosted runtime settings.
- `runtime/smoke-test.sh`: backend/frontend and ORD-1001/ORD-1009 checks.

## Runtime settings

The backend uses:

- `WORKFLOW_MODE=maf_sdk`
- `STORE_PROVIDER=postgres`
- `MEMORY_PROVIDER=postgres`
- Azure PostgreSQL managed-identity variables
- `FOUNDRY_PROJECTS_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and
  `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`
- Application Insights settings with `OTEL_RECORD_CONTENT=false`

When model configuration is unavailable, deterministic triage remains within
the same MAF workflow. HITL rules remain deterministic.

## Validate before any deployment

Follow `.azure/deployment-plan.md`. At minimum, run the local test, evaluation,
E2E, Docker, design-review, Bicep/AZD, IaC, and Azure readiness gates before
deployment. Do not change the deployment-plan status until current code and IaC
evidence exists.

After an authorized deployment, run:

```bash
infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"
```

Set `EXPECT_TRIAGE_MODE=foundry_models` only when verifying model inference.
