# Backend - Shared MAF Order Resolution

The local FastAPI host and public Foundry hosted agent invoke the same MAF
business workflow. FastAPI owns the stable API/SSE/UI contract; Foundry uses the
Responses protocol through `foundry/main.py` and `agent.yaml`.

## Local runtime

```bash
make up
```

Use `STORE_PROVIDER=postgres` for the workflow audit ledger. If Foundry model settings are absent, triage uses
the deterministic summary fallback without bypassing MAF orchestration.
`backend/.env` defaults to `RUNTIME_TARGET=local_maf`. To test the wrapper
locally, explicitly set `RUNTIME_TARGET=responses_wrapper` and the current
`FOUNDRY_RESPONSES_ENDPOINT`; the hosted agent package never copies this local
file.

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

The hosted browser path is external frontend Container App -> same-origin
`/api` proxy -> internal FastAPI wrapper -> managed-identity Foundry Responses.
The wrapper creates and persists a Foundry `conv_...` ID before first dispatch,
then uses that ID for the initial turn and checkpoint-keyed HITL resume. It does
not expose Foundry credentials or a direct Foundry endpoint to the browser.
Because the hosted agent is a separate process, wrapper SSE tails persisted
PostgreSQL workflow events. The initial Responses request is non-streaming; the
UI polls the selected run until its durable projection is available.

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
- `make eval-foundry` judges conversations in hosted E2E evidence only after
  their configured minimum trace age (`90` seconds by default), mitigating
  trace-materialization races.
- The target obtains `FOUNDRY_PROJECTS_ENDPOINT`,
  `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and (when configured) `FOUNDRY_EVAL_MODEL`
  from the selected `infra/foundry-hosted` AZD environment without sourcing or
  displaying its `.env` file. Use `make eval-foundry-config` for a no-evaluation
  configuration check, or set `FOUNDRY_AZD_ENV_NAME` for a one-command,
  non-mutating environment selection.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` enables Azure Monitor export.
- `OTEL_RECORD_CONTENT=false` is the default privacy posture.
- FastAPI health (`/health`, `/api/health`) and chat SSE request spans are
  excluded from request telemetry in the public lane. Foundry readiness,
  invocation, workflow, model, and HITL telemetry remains enabled.
