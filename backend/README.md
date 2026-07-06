# Backend - MAF Sequential Multi-Agent Demo

## Journey Status (Local MAF -> Azure app-hosted -> Foundry-hosted)

| Stage | Status | Backend behavior today |
|---|---|---|
| Local MAF | Implemented | `WORKFLOW_MODE=maf_sdk` is fully wired and is the active runtime path. |
| Azure app-hosted | Prepared | Azure IaC and container wiring are present; first cutover uses `STORE_PROVIDER=postgres` with Azure PostgreSQL via `DATABASE_URL`. |
| Foundry-hosted | In progress | `WORKFLOW_MODE=foundry_hosted` uses a hosted `invocations` workflow adapter and requires `FOUNDRY_HOSTED_INVOCATIONS_URL`; the cutover hosted package uses `FOUNDRY_HOSTED_PROTOCOL=dual` to expose both `invocations` and additive `responses` routes. Optional `FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=responses` labels shadow turns with `synthetic=true` metadata. |

The backend still keeps local MAF as the default runtime path. Azure app-hosted deployment preserves that runtime path and moves the hosting/database/secrets layer to Azure. The app-hosted IaC also provisions Azure AI Foundry/Azure AI Services project and model deployments and passes non-secret deployment metadata through `FOUNDRY_PROJECTS_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`, and `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`. The Foundry-hosted path is now wired for hosted invocations and event ingress but still requires hosted agent deployment for end-to-end execution.

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

## Foundry hosted agent: detailed command runbook

Use this when deploying/testing `order-resolution-hosted` in Foundry.

### 1) Validate azd + Foundry config

```bash
cd /home/praveen/projects/poc/maf/maf-order-resolution-agent
azd env get-values | grep -E "FOUNDRY_PROJECT_ENDPOINT|AZURE_RESOURCE_GROUP|AZURE_SUBSCRIPTION_ID"
azd ai agent doctor --no-prompt
```

Expected:

- `FOUNDRY_PROJECT_ENDPOINT` is set.
- `azd ai agent doctor` passes local/auth checks.

### 2) Deploy hosted agent (code deploy)

```bash
cd /home/praveen/projects/poc/maf/maf-order-resolution-agent
azd deploy order-resolution-hosted --no-prompt
```

Current deployment root is `backend/foundry` (see `azure.yaml` service `order-resolution-hosted`).

### 3) Check deployed version status

```bash
cd /home/praveen/projects/poc/maf/maf-order-resolution-agent
azd ai agent show order-resolution-hosted --output json
```

Wait for:

- `"status": "active"`
- `agent_endpoints.invocations` present

### 4) Invoke the hosted endpoint from CLI

```bash
cd /home/praveen/projects/poc/maf/maf-order-resolution-agent
azd ai agent invoke order-resolution-hosted '{"message":"health check"}' --no-prompt
```

Expected response shape (invocations protocol):

```json
{
  "thread_id": "...",
  "status": "completed",
  "events": [
    {
      "type": "workflow.output",
      "payload": { "status": "completed", "message": "..." }
    }
  ]
}
```

### 5) Verify session creation through Foundry API/MCP

```bash
# REST example
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  "https://<account>.services.ai.azure.com/api/projects/<project>/agents/order-resolution-hosted/sessions?api-version=v1"
```

Or use the Foundry MCP command `session_create` with:

- `projectEndpoint`: `https://<account>.services.ai.azure.com/api/projects/<project>`
- `agentName`: `order-resolution-hosted`

### 6) Monitor logs for a known session

```bash
cd /home/praveen/projects/poc/maf/maf-order-resolution-agent
azd ai agent monitor order-resolution-hosted --session-id <session-id> --type system --tail 200
azd ai agent monitor order-resolution-hosted --session-id <session-id> --type console --tail 200
```

### 7) Foundry Playground usage notes (important)

- This hosted agent is configured for **`invocations`** protocol.
- In Playground, prefer **Call agent** with JSON payload (`{"message":"..."}`).
- Chat mode targets responses-style behavior and can appear broken/mismatched for invocations-only agents.
- Hosted Playground tests are independent from the app UI (`frontend` + `backend` API) unless you explicitly wire backend `WORKFLOW_MODE=foundry_hosted` and endpoint settings.

### 8) Common failures and direct checks

`agent_version_not_ready` or version stuck in `creating`:

```bash
azd ai agent show order-resolution-hosted --output json
```

`agent_version_failed`:

```bash
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://<account>.services.ai.azure.com/api/projects/<project>/agents/order-resolution-hosted/versions/<version>?api-version=v1"
```

Inspect `.error.code` and `.error.message` from the version payload.

Hosted agents not detected by doctor:

```bash
azd deploy order-resolution-hosted --no-prompt
azd ai agent doctor --no-prompt
```

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
- Foundry-hosted invocation calls propagate W3C trace context (`traceparent`,
  `tracestate`) on outbound requests so Foundry-side services can correlate
  requests with backend spans.
- The hosted agent runtime also configures Azure Monitor tracing when
  `APPLICATIONINSIGHTS_CONNECTION_STRING` is available and sets
  `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING=true` by default. Keep content
  recording disabled unless explicitly needed because traces can include
  customer data.

## APIs

- `POST /api/chat/run` starts sequential workflow.
- `GET /api/chat/stream/{thread_id}` streams AGUI-like SSE events.
- `GET /api/chat/stream/{thread_id}/rich` streams AG-UI-compatible `workflow.rich` envelopes.
- `POST /api/hitl/respond` approves/rejects a pending checkpoint.
- `POST /api/foundry/invoke` proxies a direct hosted-agent invocations payload for non-UI diagnostics/automation using configured backend env (`FOUNDRY_HOSTED_INVOCATIONS_URL`, optional `FOUNDRY_HOSTED_API_KEY`). For `services.ai.azure.com` targets without an API key, backend auto-acquires an Entra bearer token (`az login` required). Hosted agent runtime protocol selection is controlled separately by `FOUNDRY_HOSTED_PROTOCOL=invocations|dual|responses`; use `dual` for the cutover hosted package and `invocations` for rollback.
- `FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=responses` is hosted-runtime-only shadow mode. It posts Invocations user turns to `FOUNDRY_HOSTED_RESPONSES_URL` (or derives `/responses` from an `/invocations` URL) with `metadata.synthetic=true`, `metadata.source_protocol=invocations`, and `metadata.operation=shadow_conversation` so those records are distinguishable from active Responses canary runs.
- `POST /api/foundry/events` ingests hosted-agent native events (token-protected via `FOUNDRY_EVENT_CALLBACK_TOKEN`).
- `GET /api/workflows` lists workflow runs (`page`, `page_size`, and legacy `pageSize` are supported).
- `GET /api/workflows/{thread_id}` returns workflow run details (including timeline events).
- `GET /api/workflows/{thread_id}/events` returns cursor-paginated events (`limit`, `cursor`).
- `GET /api/sessions/{session_id}/messages` returns cursor-paginated session messages (`limit`, `cursor`).
- `GET /health` and `GET /api/health` return service health plus runtime metadata used by Workflow Studio (`workflow_mode`, `runtime_provider`, `runtime_mode`, `environment`).

## Multi-target parity checks

Use `make parity-all` to run the single fast parity gate across local, Azure, and Foundry endpoints.

Fast parity includes:

- manual baseline cases `ORD-1001` and `ORD-1009`
- all event contract checks
- Playwright smoke subset (low-risk complete, high-risk approve, high-risk reject)

For one-off exhaustive verification, run:

- `python3 scripts/parity/run_parity_matrix.py --targets local azure foundry --profile full`

Parity runner configuration is environment-driven via `PARITY_<TARGET>_{API,WEB}_URL` variables and optional `PARITY_ENV_FILE`.

## Internal Boundaries

The backend follows the clean agent-style package layout while keeping the current deployable service shape:

- `app/api/v1/routers/*` owns public HTTP/SSE routes.
- `app/api/v1/schemas/*` owns API response/request contracts.
- `app/modules/order_resolution/*` owns the order-resolution service/domain seams, HITL policy logic, internal workflow models, ports, and event-to-read-model projection.
- `app/core/config.py`, `app/core/database.py`, `app/core/telemetry.py`, and `app/core/container.py` own core configuration, database, telemetry, and runtime composition.
- `app/infrastructure/persistence/*`, `app/infrastructure/events/*`, `app/infrastructure/rag/*`, and `app/infrastructure/mcp/*` are repository-pattern/adapters namespaces.
- `app/maf/*` owns the MAF workflow runtime namespace, tools, clients, agents, and prompts scaffolding.
- `app/foundry/*` owns Foundry-hosted invocation client and workflow adapter seams.
- Legacy shim paths have been removed. Use only canonical modules under `app/api/v1`, `app/core`, `app/modules/order_resolution`, `app/infrastructure`, `app/maf`, and `app/foundry`.

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
