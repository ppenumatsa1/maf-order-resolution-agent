# Public Foundry Deployment Plan

> **Status:** Validated

## Target

- Subscription: `4f18d577-3506-4a11-85e5-a83b14727a84`
- Resource group: `rg-maf-ora-foundry-public-dev2`
- azd environment: `foundry-public-dev2`
- Project: `order-resolution-public-managed-dev2`
- Agent: `order-resolution-hosted`

## Scope

`infra/foundry-hosted/iac/main.bicep` creates a public Foundry project with
Microsoft-managed agent state, public PostgreSQL, external frontend and internal
backend Container Apps, and Bicep-managed Foundry and trace-reader role
assignments. It references the existing Foundry account, ACR, App Insights, and
Log Analytics workspace. The project has a supported project-scoped
`ApplicationInsights` connection for trace evaluation. Foundry supplies the
managed session, file, and vector-store services; PostgreSQL is the only
application-owned persistence service and stores workflow audit/checkpoint state.

Local FastAPI/SSE/UI validation remains separate from hosted validation. The
public frontend preserves the API/SSE browser contract through a same-origin
proxy to the internal FastAPI wrapper, which invokes the Foundry Responses
agent. The release command is:

```bash
AZURE_SUBSCRIPTION_ID="<subscription-id>" \
RUNTIME_DATABASE_URL="postgresql://...?...sslmode=require" \
POSTGRES_ADMIN_PASSWORD="<postgres-admin-password>" \
make foundry-release
```

## Validation evidence

- Bicep compilation passed for the managed-state template.
- `azd provision --preview --no-prompt` validates the public Foundry project,
  Container Apps, shared PostgreSQL, and observability configuration without
  mutating resources.
- `az deployment group validate` completed for the public deployment template.
- PostgreSQL remains in `centralus` because the subscription rejects Flexible
  Server creation in `eastus2`; the Foundry account remains in `eastus2`.

Deployment, hosted smoke/E2E, Foundry eval, and telemetry evidence must be
recorded in `docs/design/issues-changes-fixes.md`.
