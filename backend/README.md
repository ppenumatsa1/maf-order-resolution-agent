# Backend - Shared MAF Order Resolution

The local FastAPI host and public Foundry hosted agent invoke the same MAF
business workflow. FastAPI owns the stable local API/SSE/UI contract; Foundry
uses the Responses protocol through `foundry/main.py` and `agent.yaml`.

## Local runtime

```bash
make up
```

Use `STORE_PROVIDER=postgres` for the workflow audit ledger. If Foundry model settings are absent, triage uses
the deterministic summary fallback without bypassing MAF orchestration.

## Public Foundry runtime

Deploy from the repository root with the authenticated release command:

```bash
AZURE_SUBSCRIPTION_ID="<subscription-id>" \
RUNTIME_DATABASE_URL="postgresql://...?...sslmode=require" \
POSTGRES_ADMIN_PASSWORD="<postgres-admin-password>" \
make foundry-release
```

`infra/foundry-hosted/azure.yaml` deploys a generated `agent/` package that is
refreshed from canonical `backend/` source before every deployment.
The public hosted project uses Microsoft-managed Foundry agent state; PostgreSQL
continues to own the workflow, checkpoint, approval, and audit records.
The release runs local gates, `azd up`, hosted smoke/E2E, Foundry evaluation,
and Application Insights validation.

## Contracts

- API routes and SSE: `app/api/v1/routers/*`
- API schemas: `app/api/v1/schemas/*`
- application service and domain seams: `app/modules/order_resolution/*`
- MAF runtime: `app/maf/*`
- persistence/adapters: `app/infrastructure/*`

Stable event types are `workflow.stage`, `tool.call`, `checkpoint.created`,
`hitl.request`, `hitl.response`, and `workflow.output`. The rich stream is
additive.

HITL pauses when amount/risk is at least `100`, an item is damaged, or policy
requires manual review. `ORD-1001` is low risk; `ORD-1009` requires approval.

## Evaluation and telemetry

- `make eval-backend` runs deterministic contract evaluation.
- `make eval-foundry` publishes Foundry evaluation evidence.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` enables Azure Monitor export.
- `OTEL_RECORD_CONTENT=false` is the default privacy posture.
