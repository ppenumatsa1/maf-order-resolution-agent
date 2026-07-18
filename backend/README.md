# Backend - Shared MAF Order Resolution

## Runtime status

| Stage | Status | Runtime behavior |
| --- | --- | --- |
| Local FastAPI host | Implemented | Runs the shared MAF workflow and exposes stable API/SSE/HITL contracts. |
| Azure app-hosted | Implemented | Same FastAPI host pattern on ACA/Postgres/App Insights. |
| Foundry hosted agent | Implemented | `backend/foundry/main.py` hosts the same workflow with Responses protocol (`backend/agent.yaml`). |

There is one business workflow path rooted at `backend/app/maf/workflows/order_resolution.py`,
with modular internals in `backend/app/maf/prompts/`, `agents/`, `tools/`, `executors/`,
and `runner.py`.

## Run locally

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Recommended local provider settings:

```bash
export STORE_PROVIDER=postgres
export RAG_PROVIDER=pgvector
export MEMORY_PROVIDER=postgres
```

Model client selection:

- Set `FOUNDRY_PROJECTS_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT_NAME` to use Foundry models for triage agents.
- If those values are absent, only the deterministic triage summary fallback is used (the workflow path itself remains MAF).

## Foundry hosted agent (Responses)

Deploy and run from repository root:

```bash
azd deploy order-resolution-hosted --no-prompt
azd ai agent show order-resolution-hosted --output json
azd ai agent invoke order-resolution-hosted "Resolve delayed order ORD-1001" --protocol responses --conversation-id c1 --no-prompt
azd ai agent invoke order-resolution-hosted "Why was that resolution selected?" --protocol responses --conversation-id c1 --no-prompt
```

The hosted deploy source is configured in `infra/foundry-hosted/azure.yaml` as `./agent`; `make foundry-deploy` automatically syncs `backend/` into that folder before `azd deploy`.

For high-risk turns that request approval, continue the same conversation with `Approve` or `Reject`.

Latest hosted-tracing status (2026-07-15):

- Public Foundry Conversations/Transactions are restored and visible.
- Hosted tracing/root-cause fix included removing `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING` from `backend/agent.yaml` to avoid stream-wrapper incompatibility on the hosted Foundry path.
- Private lane currently needs additional investigation for intermittent upstream `HTTP 500 server_error` during smoke/probe after deploy activation.

Telemetry:

- `APPLICATIONINSIGHTS_CONNECTION_STRING` enables Azure Monitor/Application Insights export.
- `ENABLE_TELEMETRY=false` disables telemetry.
- `ENABLE_INSTRUMENTATION` controls MAF/OpenTelemetry instrumentation when telemetry is enabled.
- `OTEL_RECORD_CONTENT=false` keeps prompt/payload content out of span attributes.

Evaluation:

- `make eval-backend` runs deterministic contract assertions against `backend/.foundry/datasets/order-resolution-hosted-cases.jsonl`.
- `make eval-foundry` runs report-only Foundry evaluators and writes `backend/.foundry/results/foundry-report.json`.

## APIs

- `POST /api/chat/run`
- `GET /api/chat/stream/{thread_id}`
- `GET /api/chat/stream/{thread_id}/rich`
- `POST /api/hitl/respond`
- `GET /api/workflows`
- `GET /api/workflows/{thread_id}`
- `GET /api/workflows/{thread_id}/events`
- `GET /api/sessions/{session_id}/messages`
- `GET /health` and `GET /api/health`

## Internal boundaries

- `app/api/v1/routers/*` owns HTTP/SSE routes.
- `app/api/v1/schemas/*` owns API contracts.
- `app/modules/order_resolution/*` owns service/domain seams, HITL policy logic, internal workflow models, ports, and projections.
- `app/core/*` owns config, database, telemetry, and composition.
- `app/infrastructure/*` is the repository-pattern/adapters namespace.
- `app/maf/*` owns the MAF runtime namespace.

Legacy shims and `app/foundry/*` adapter paths are removed.

Delivery ownership and verification gate authority are defined in `docs/design/engineering-operating-model.md`.

## Event contract (SSE)

Stable emitted event types:

- `workflow.stage`
- `tool.call`
- `checkpoint.created`
- `hitl.request`
- `hitl.response`
- `workflow.output`

The rich stream (`/api/chat/stream/{thread_id}/rich`) is additive and preserves native event payloads.

## HITL trigger conditions

The workflow emits `hitl.request` when any condition is true:

- amount/risk `>= 100`
- issue type `damaged_item`
- policy contains `manual_review`

Baselines:

- `ORD-1009` delayed: HITL expected.
- `ORD-1001` late delivery: no HITL expected.
