---
name: azure-validation
description: Validate a deployable or deployed public Foundry-hosted workflow without deploying resources.
---

# Azure Validation Skill

Use this skill after IaC review and before deployment. Validate readiness and live behavior without running deployment commands that mutate Azure resources.

## Required inputs

- `infra/foundry-hosted/azure.yaml` and public Foundry Bicep files identify the
  intended Azure target and resource model.
- If live resources already exist, the active Azure subscription and environment are known.

## Local validation

Run non-mutating checks only:

```bash
cd infra/foundry-hosted && azd provision --preview
az bicep build --file infra/foundry-hosted/iac/main.bicep
```

Then run package validation using repository commands that already exist, such as backend/frontend builds or tests. Do not add new tools solely for validation.

## Smoke and behavior checks

- Validate the public Foundry Responses endpoint with `make foundry-smoke`.
- Run `scripts/foundry/hosted_e2e.sh` for conversation, approval, rejection, and
  duplicate-response behavior.
- Run local Playwright against the local FastAPI/SSE UI:

```bash
PLAYWRIGHT_BASE_URL="$WEB_URL" make test-e2e
```

  This must prove the local frontend is wired to the local API, including
  Workflow History loading JSON successfully.
- Confirm project and Foundry account identities have Bicep-managed storage,
  Cosmos, and Search roles.

## Pass/fail behavior

- Pass only when preview, Bicep build, package validation, Foundry smoke/E2E,
  local UI checks, workflow cases, and applicable RBAC checks succeed.
- If blocked, report the exact failing command, missing resource, or permission gap and do not deploy.
