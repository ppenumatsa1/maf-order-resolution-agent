# Backend - MAF Sequential Multi-Agent Demo

## Journey Status (Local MAF -> Azure app-hosted -> Foundry-hosted)

| Stage | Status | Backend behavior today |
|---|---|---|
| Local MAF | Implemented | `WORKFLOW_MODE=maf_sdk` is fully wired and is the active runtime path. |
| Azure app-hosted | Prepared | Azure IaC and container wiring are present; first cutover uses `STORE_PROVIDER=postgres` with Azure PostgreSQL via `DATABASE_URL`. |
| Foundry-hosted | Scaffolded | `WORKFLOW_MODE=foundry_hosted` is accepted config, but `app.maf.factory.create_workflow` raises `NotImplementedError`. |

This means the backend currently runs the Local MAF path end-to-end. Azure app-hosted deployment preserves that runtime path and moves the hosting/database/secrets layer to Azure. The app-hosted IaC also provisions Azure AI Foundry/Azure AI Services project and model deployments and passes non-secret deployment metadata through `FOUNDRY_PROJECTS_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`.

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

Store provider switching values for Azure/Foundry are defined but not runtime-enabled yet. Current runtime support requires `STORE_PROVIDER=postgres`, including the first Azure app-hosted deployment.
RAG providers now support:

- `RAG_PROVIDER=pgvector` (default, fully wired local pgvector-compatible retrieval)
- `RAG_PROVIDER=azure_ai_search` (safe placeholder provider stub)
- `RAG_PROVIDER=foundry_vector` (safe placeholder provider stub)
- `RAG_PROVIDER=foundry_iq` (safe placeholder provider stub)
Memory provider switching is available now:

- `MEMORY_PROVIDER=postgres` (default, persisted in Postgres)
- `MEMORY_PROVIDER=foundry_memory` (in-process placeholder stub for Foundry memory integration)

Model client selection:

- Set `FOUNDRY_PROJECTS_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT_NAME` to use
  the Microsoft Foundry Models project endpoint client for triage agents.
- `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME` is the canonical embeddings deployment
  name emitted by Azure app-hosted IaC for downstream RAG/vector integration.
- `FOUNDRY_PROJECT_ENDPOINT`, `MAF_MODEL`, `FOUNDRY_MODEL`, and `MAF_PROVIDER`
  remain compatibility aliases for existing developer environments; new
  configuration should use the canonical variables above.
- If Foundry config is absent, local and CI runs keep the deterministic triage
  fallback. This fallback replaces only the LLM triage summary, not the MAF
  workflow path.

HITL remains deterministic and model-independent. The LLM can summarize triage,
but approval decisions are still made from issue classification, order amount,
and policy text by the backend HITL rules.

Telemetry:

- `APPLICATIONINSIGHTS_CONNECTION_STRING` enables Azure Monitor/Application
  Insights trace export.
- `ENABLE_TELEMETRY` disables all local telemetry setup when set to `false`.
- `ENABLE_INSTRUMENTATION` controls MAF/OpenTelemetry instrumentation when
  telemetry is enabled.
- `OTEL_RECORD_CONTENT=false` is the default and suppresses prompt, response,
  payload, and tool content from span attributes.
- MAF workflow telemetry observes streamed executor I/O events:
  `executor_invoked`, `executor_completed`, and `output`.

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
- Legacy shim paths have been removed. Use only canonical modules under `app/api/v1`, `app/core`, `app/modules/order_resolution`, `app/infrastructure`, and `app/maf`.

## Event Contract (SSE)

The frontend and tests rely on these emitted event types remaining stable:

- `workflow.stage`
- `tool.call`
- `checkpoint.created`
- `hitl.request`
- `hitl.response`
- `workflow.output`

The legacy stream remains available at `GET /api/chat/stream/{thread_id}`. An additive rich event stream is available at `GET /api/chat/stream/{thread_id}/rich`; it emits `workflow.rich` SSE events with AG-UI-compatible lifecycle, step, tool, text, HITL/custom, and raw event projections while preserving the native event payload.

## Notes

- This implementation uses a MAF SDK sequential workflow by default and uses `SequentialBuilder` participant chaining.
- Provider switches are controlled with `STORE_PROVIDER`, `RAG_PROVIDER`, and `MEMORY_PROVIDER`.
- Hosted-path artifacts are in `../infra/azure-apphosted` and `../infra/foundry-hosted`; Azure app-hosted uses AZD + Bicep + Azure Container Apps.
- MCP calls support auth headers through env vars (`MCP_API_KEY`, `MCP_BEARER_TOKEN`).
- Read-only model/MCP calls use bounded retries (`READ_RETRY_ATTEMPTS`, `READ_RETRY_DELAY_SECONDS`).
- MAF middleware centralizes event enrichment with `workflow_run_id` and `session_id`, streamed MAF usage/event observation, and explicit `workflow.failed` emission for real workflow failures.
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
