# Local -> Azure -> Foundry Decisions

This document records the architecture decisions made across the three runtime stages.

## Decision summary

| Stage | Decision | Why |
|---|---|---|
| Local | Keep a single MAF workflow path (`WORKFLOW_MODE=maf_sdk`) with deterministic triage fallback only when Foundry model env vars are missing. | Preserves deterministic behavior for tests/dev while still enabling model-backed triage when configured. |
| Azure app-hosted | Move hosting and persistence to Azure (ACA + Azure PostgreSQL + App Insights), but keep backend contracts and workflow behavior identical to local. | Reduces migration risk and keeps UI/API/eval contracts stable. |
| Foundry-hosted | Keep backend as the stable API/HITL/SSE gateway and move execution to Foundry hosted agent via structured `invocations`. | Preserves workflow/HITL/event contracts while enabling Foundry agent runtime components. |

## Contract decisions that stay fixed

1. Keep native event types stable:
   - `workflow.stage`
   - `tool.call`
   - `checkpoint.created`
   - `hitl.request`
   - `hitl.response`
   - `workflow.output`
2. Keep additive AG-UI-compatible rich SSE stream (`/api/chat/stream/{thread_id}/rich`) without removing legacy SSE yet.
3. Keep Postgres as durable run/event/audit store through Foundry-hosted parity.
4. Do not introduce a second deterministic orchestration path.

## Foundry implementation shape (selected)

### Backend package ownership

- `backend/app/maf/*`: existing MAF workflow runtime.
- `backend/app/foundry/*`: Foundry hosted invocation client, protocol models, and workflow adapter.
- `backend/foundry/*`: Foundry metadata (`agent.yaml`, `eval.yaml`, runtime entrypoint, `.foundry` cache).
- `infra/foundry-hosted/*`: Azure/Foundry IaC and runtime environment scaffolding.

### Protocol choice

- **Primary protocol: `invocations`** (selected).
- Rationale: structured payloads are required for `thread_id`, `workflow_run_id`, HITL checkpoint resume, and deterministic response handling.
- `responses` can be added later as a secondary conversational/demo surface.

### Event flow

1. Backend receives `/api/chat/run` or `/api/hitl/respond`.
2. Foundry-hosted workflow adapter invokes hosted agent endpoint (`FOUNDRY_HOSTED_INVOCATIONS_URL`).
3. Hosted agent emits native events via backend ingress `/api/foundry/events`.
4. Backend publishes events to existing event bus -> persistence projection -> SSE and rich SSE.

## Provider and component sequencing

1. First achieve Foundry-hosted execution parity.
2. Then evaluate replacing placeholders:
   - `foundry_memory`
   - `foundry_iq` / `foundry_vector`
3. Keep Azure AI Search deferred until post-Foundry retrieval architecture is confirmed.

## Foundry-native traces and state evaluation

- Foundry-native traces are an observability surface, not a replacement for the
  workflow read models required by the UI and tests. The hosted runtime must
  create OpenTelemetry spans and export them with the Foundry project telemetry
  configuration so invocations appear in Foundry Traces.
- Postgres remains the source of truth while parity is being proven for:
  conversation history, workflow event history, checkpoint/resume state,
  approval audit records, status filtering, pagination, and eval/E2E fixtures.
- Foundry-native memory/thread/checkpoint storage can be evaluated behind
  repository ports only after it proves equivalent durability, queryability,
  auditability, HITL pause/resume semantics, and local-test determinism.
- Any migration away from Postgres should use adapter-first implementation,
  dual-write or shadow-read validation, and a rollback path before switching
  provider configuration.

## Operational choices for speed

- Use quick validation (`make validate-quick`) + app-only deploy (`make deploy-app`) for app-only changes.
- Use full validation/deploy only for infra/runtime contract changes.

## Hosted deployment blocker resolution

- Central US Foundry project is not hosted-agent-enabled; deployment/validation moved to East US 2 (`mafs5ixpqx3hitri-project`).
- Container-image deployment path stayed unstable in this tenant due repeated image pull/provisioning failures.
- Selected fix: use **code deploy** with a dedicated hosted-agent project root (`backend/foundry`) and minimal runtime dependencies.
  - `azure.yaml` `order-resolution-hosted.project` -> `./backend/foundry`
  - `backend/foundry/agent.yaml` -> `invocations` protocol, `entry_point: main.py`, `runtime: python_3_13`
  - `backend/foundry/requirements.txt` contains only hosting runtime deps
- Outcome: hosted agent version `9` reached `active`, `azd ai agent invoke order-resolution-hosted` succeeds, and Foundry `session_create` now succeeds.
