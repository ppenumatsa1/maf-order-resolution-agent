---
name: azure-deployment
description: Execute already validated Azure deployments and verify live endpoints.
---

# Azure Deployment Skill

Use this skill only for deployments that already passed Azure validation. Do not use it to design, prepare, or validate an unvalidated app.

## Hard gates

- Require `.azure/deployment-plan.md` to exist with status `Validated`.
- Run pre-deploy checks before any mutation: active subscription, AZD environment, required variables, Docker availability when needed, and clean authentication to Azure.
- Do not perform destructive cleanup, resource deletion, environment reset, or database drop unless the user explicitly confirms that exact destructive action.

## Deployment sequence

Run provisioning and application deployment separately so Container Apps, ACR, and RBAC failures are isolated:

```bash
azd provision
azd deploy
```

After `azd provision`, confirm expected resources exist and managed identities/RBAC assignments are present before deploying containers.

## Known recovery

If Container Apps deployment fails because the app is not bound to ACR through its managed identity, recover with the explicit registry binding and rerun deploy:

```bash
az containerapp registry set \
  --name <container-app-name> \
  --resource-group <resource-group> \
  --server <acr-login-server> \
  --identity system
azd deploy
```

Use this recovery only for the known registry binding issue; do not mask unrelated deployment failures.

## Post-deploy verification

- Run smoke tests against the live HTTPS endpoint.
- Verify health endpoint, Container Apps revision readiness, and recent logs.
- Validate RBAC live: ACR image pull, Key Vault secret reads, PostgreSQL connectivity, and observability ingestion where applicable.
- Validate `ORD-1001` completes without `hitl.request`.
- Validate `ORD-1009` emits `hitl.request` and completes the expected approval/resume path.
- Report fully qualified HTTPS endpoints for frontend, backend/API, health, and any documented smoke target.

## Output

Report deployed environment, resource group, Container Apps names, image tags when available, smoke results, RBAC results, and fully qualified HTTPS endpoints. If deployment fails, report the exact command, error, recovery attempted, and next safe action.
