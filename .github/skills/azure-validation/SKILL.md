---
name: azure-validation
description: Validate a deployable or deployed Azure app-hosted workflow without deploying resources.
---

# Azure Validation Skill

Use this skill after IaC review and before deployment. Validate readiness and live behavior without running deployment commands that mutate Azure resources.

## Required inputs

- `.azure/deployment-plan.md` exists and proves the intended Azure target, resource model, and current status.
- Existing AZD/Bicep/package files are present for the app components being validated.
- If live resources already exist, the active Azure subscription and environment are known.

## Local validation

Run non-mutating checks only:

```bash
azd provision --preview
az bicep build --file infra/main.bicep
```

Then run package validation using repository commands that already exist, such as backend/frontend builds or tests. Do not add new tools solely for validation.

## Deployment-plan gate

- Confirm `.azure/deployment-plan.md` contains evidence that the app is prepared for Azure deployment.
- Confirm status is ready for validation or already provisioned; do not mark deployment-ready unless validation commands and smoke checks pass.
- Record any missing resource, identity, SKU, or region assumption as a blocker.

## Smoke and behavior checks

- Run the repository smoke script when present; it must validate health and workflow behavior without changing infrastructure.
- For live Container Apps, verify app health endpoint, ingress URL, revision readiness, and recent logs.
- Validate live `/health` or equivalent endpoint over HTTPS.
- Validate `ORD-1001` completes without `hitl.request`.
- Validate `ORD-1009` emits `hitl.request` and can follow the expected HITL path.
- Confirm RBAC where resources exist: Container Apps managed identity can pull from ACR, read Key Vault secrets, and access PostgreSQL/observability dependencies as designed.

## Pass/fail behavior

- Pass only when preview, Bicep build, package validation, smoke checks, health checks, workflow cases, and applicable RBAC checks succeed.
- If passing, update `.azure/deployment-plan.md` status to `Validated` only when explicitly requested by the user or task.
- If blocked, report the exact failing command, missing resource, or permission gap and do not deploy.
