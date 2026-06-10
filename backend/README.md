# Backend - MAF Sequential Multi-Agent Demo

## Journey Status (Local MAF -> Azure app-hosted -> Foundry-hosted)

| Stage | Status | Backend behavior today |
|---|---|---|
| Local MAF | Implemented | `WORKFLOW_MODE=maf_sdk` is fully wired and is the active runtime path. |
| Azure app-hosted | Scaffolded | `STORE_PROVIDER=azure_postgres|app_db` are accepted config values, but app startup rejects non-`postgres` store providers. |
| Foundry-hosted | Scaffolded | `WORKFLOW_MODE=foundry_hosted` is accepted config, but `workflows/factory.py` raises `NotImplementedError`. |

This means the backend currently runs the Local MAF path end-to-end; Azure/Foundry modes are scaffolding contracts for later phases.

## Run locally

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Configure workflow and provider mode:

```bash
export WORKFLOW_MODE=maf_sdk
export STORE_PROVIDER=postgres
export RAG_PROVIDER=pgvector
export MEMORY_PROVIDER=postgres
```

Store provider switching values for Azure/Foundry are defined but not runtime-enabled yet. Current runtime support requires `STORE_PROVIDER=postgres`.
RAG providers now support:

- `RAG_PROVIDER=pgvector` (default, fully wired local pgvector-compatible retrieval)
- `RAG_PROVIDER=azure_ai_search` (safe placeholder provider stub)
- `RAG_PROVIDER=foundry_vector` (safe placeholder provider stub)
- `RAG_PROVIDER=foundry_iq` (safe placeholder provider stub)
Memory provider switching is available now:

- `MEMORY_PROVIDER=postgres` (default, persisted in Postgres)
- `MEMORY_PROVIDER=foundry_memory` (in-process placeholder stub for Foundry memory integration)

## APIs

- `POST /api/chat/run` starts sequential workflow.
- `GET /api/chat/stream/{thread_id}` streams AGUI-like SSE events.
- `POST /api/hitl/respond` approves/rejects a pending checkpoint.
- `GET /api/workflows` lists workflow runs (`page`, `page_size`, and legacy `pageSize` are supported).
- `GET /api/workflows/{thread_id}` returns workflow run details (including timeline events).
- `GET /api/workflows/{thread_id}/events` returns cursor-paginated events (`limit`, `cursor`).
- `GET /api/sessions/{session_id}/messages` returns cursor-paginated session messages (`limit`, `cursor`).
- `GET /health` returns service health.

## Internal Boundaries

The backend follows the clean agent-style package layout while keeping the current deployable service shape:

- `app/api/v1/routers/*` owns public HTTP/SSE routes.
- `app/api/v1/schemas/*` owns API response/request contracts.
- `app/modules/order_resolution/*` owns the order-resolution service/domain seams, HITL policy logic, internal workflow models, ports, and event-to-read-model projection.
- `app/core/config.py`, `app/core/database.py`, `app/core/telemetry.py`, and `app/core/container.py` own core configuration, database, telemetry, and runtime composition.
- `app/infrastructure/persistence/*`, `app/infrastructure/events/*`, `app/infrastructure/rag/*`, and `app/infrastructure/mcp/*` are repository-pattern/adapters namespaces.
- `app/maf/*` owns the MAF workflow runtime namespace, tools, clients, agents, and prompts scaffolding.
- Existing `app/api/*`, `app/models.py`, `app/config.py`, `app/db.py`, `workflows/*`, `tools/*`, and `app/state.py` paths remain compatibility shims.

## Event Contract (SSE)

The frontend and tests rely on these emitted event types remaining stable:

- `workflow.stage`
- `tool.call`
- `checkpoint.created`
- `hitl.request`
- `hitl.response`
- `workflow.output`

## Notes

- This implementation uses a MAF SDK sequential workflow by default and uses `SequentialBuilder` participant chaining.
- Provider switches are controlled with `STORE_PROVIDER`, `RAG_PROVIDER`, and `MEMORY_PROVIDER`.
- Hosted-path scaffolds (IaC + runtime entrypoints) are in `../infra/azure-apphosted` and `../infra/foundry-hosted`.
- MCP calls support auth headers through env vars (`MCP_API_KEY`, `MCP_BEARER_TOKEN`).
- Read-only model/MCP calls use bounded retries (`READ_RETRY_ATTEMPTS`, `READ_RETRY_DELAY_SECONDS`).
- Local pgvector-compatible RAG retrieval is wired for policy lookup; retrieved chunk IDs are emitted in `tool.call.payload.policy_evidence_ids`.
- Business write submission uses deterministic idempotency keys: `workflow_run_id:step_name:business_id`.
- Duplicate approval submissions for the same checkpoint are treated idempotently (single `hitl.response` + single terminal `workflow.output`).

## HITL Trigger Conditions

The backend emits `hitl.request` when any of these are true:

- Refund/risk amount is `>= 100`.
- The issue is classified as `damaged_item`.
- A policy string contains `manual_review`.

Test-oriented examples:

- Input with `ORD-1009` triggers HITL because mapped order amount is `185.0`.
- Input with `ORD-1001` and a late-delivery message does not trigger HITL because amount is `79.0` and policy is low risk.

For the full matrix for the MAF workflow, see:

- `../docs/design/hitl-approval-conditions.md`
