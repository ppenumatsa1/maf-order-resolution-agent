# Local -> Azure -> Foundry Decisions

This document records the architecture decisions made across the three runtime stages.

## Decision summary

| Stage            | Decision                                                                                                                                                                                                                         | Why                                                                                                                                 |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Local            | Keep a single MAF workflow path (`WORKFLOW_MODE=maf_sdk`) with deterministic triage fallback only when Foundry model env vars are missing.                                                                                       | Preserves deterministic behavior for tests/dev while still enabling model-backed triage when configured.                            |
| Azure app-hosted | Move hosting and persistence to Azure (ACA + Azure PostgreSQL + App Insights), but keep backend contracts and workflow behavior identical to local.                                                                              | Reduces migration risk and keeps UI/API/eval contracts stable.                                                                      |
| Foundry-hosted   | Keep backend as the stable API/HITL/SSE gateway while moving execution to Foundry Hosted Agent. Use `invocations` for the current stable backend contract and add `responses` as the native conversation/traces cutover surface. | Preserves workflow/HITL/event contracts while enabling Foundry-native conversation history, sessions, and traces for hosted agents. |

## Contract decisions that stay fixed

1. Keep native event types stable:
   - `workflow.stage`
   - `tool.call`
   - `checkpoint.created`
   - `hitl.request`
   - `hitl.response`
   - `workflow.output`
2. Keep additive AG-UI-compatible rich SSE stream (`/api/chat/stream/{thread_id}/rich`) without removing legacy SSE yet.
3. Keep Postgres as durable backend run/event/audit store for local and Azure
   app-hosted workflows. Foundry-hosted execution may use hosted-native state
   internally, but backend still projects emitted events into Postgres for UI
   history and HITL API contracts.
4. Do not introduce a second deterministic orchestration path.

## Foundry implementation shape (selected)

### Backend package ownership

- `backend/app/maf/*`: existing MAF workflow runtime.
- `backend/app/foundry/*`: Foundry hosted invocation client, protocol models, and workflow adapter.
- `backend/foundry/*`: Foundry metadata (`agent.yaml`, `eval.yaml`, runtime entrypoint, `.foundry` cache).
- `infra/foundry-hosted/*`: Azure/Foundry IaC and runtime environment scaffolding.

### Protocol choice

- **Current stable protocol: `invocations`**.
  - Rationale: structured payloads are required for `thread_id`,
    `workflow_run_id`, HITL checkpoint resume, deterministic response handling,
    and backend/UI contract stability.
- **Cutover protocol: `responses` alongside `invocations`**.
  - Rationale: Foundry Hosted Agent Responses provides the native conversation
    and response-history surface expected by Foundry portal traces/sessions.
  - During cutover, use `FOUNDRY_HOSTED_PROTOCOL=dual` to shadow Responses while
    Invocations remains user-visible.
  - Switch to `FOUNDRY_HOSTED_PROTOCOL=responses` only after conversation,
    memory, HITL checkpoint, traces, and rollback gates pass.

### Event flow

1. Backend receives `/api/chat/run` or `/api/hitl/respond`.
2. Foundry-hosted workflow adapter invokes the active hosted protocol endpoint:
   `FOUNDRY_HOSTED_INVOCATIONS_URL` during current/rollback mode, or the
   Responses endpoint during canary cutover.
3. Hosted agent emits or returns canonical workflow events for backend
   projection.
4. Backend publishes events to existing event bus -> persistence projection -> SSE and rich SSE.

## Provider and component sequencing

1. First achieve Foundry-hosted execution parity.
2. Then evaluate replacing placeholders:
   - `foundry_memory`
   - `foundry_iq` / `foundry_vector`
3. Keep Azure AI Search deferred until post-Foundry retrieval architecture is confirmed.

## Foundry-native traces and hosted-agent state evaluation

- Foundry-native traces are an observability surface, not a replacement for the
  workflow read models required by the UI and tests. The hosted runtime must
  create OpenTelemetry spans and export them with the Foundry project telemetry
  configuration so invocations appear in Foundry Traces.
- Postgres remains the source of truth for local and Azure app-hosted backend
  workflow read models: workflow event history, approval API state, status
  filtering, pagination, and eval/E2E fixtures.
- Foundry-native memory/thread/checkpoint storage is scoped to the
  Foundry-hosted agent package only. The hosted agent may use native state for
  its own session, checkpoint, conversation, and memory recovery, while local
  and Azure app-hosted workflows continue to use Postgres.
- During cutover, the backend continues to persist emitted hosted-agent events
  to Postgres for stable UI/API history. This projection can be removed for the
  Foundry-hosted path only after the Responses/native read path proves parity.
- Hosted-agent native state is gated by provider settings:
  - `FOUNDRY_HOSTED_STATE_PROVIDER=stateless_context` is the safe default.
  - `FOUNDRY_HOSTED_STATE_PROVIDER=dual` is reserved for shadow validation.
  - `FOUNDRY_HOSTED_STATE_PROVIDER=foundry_native` must fail fast until a
    durable Foundry checkpoint/state API with HITL approval audit parity is
    proven.
  - `FOUNDRY_HOSTED_MEMORY_PROVIDER=foundry` enables Foundry Memory Store
    preview for hosted-agent long-term memory only.
- The current capability finding is that Foundry Memory Store preview is
  suitable for opt-in hosted-agent long-term memory. No transactional checkpoint
  storage API has been proven for HITL audit/resume parity, so the hosted-agent
  checkpoint path must keep explicit resume context until parity is
  demonstrated.

### Hosted-agent storage compatibility matrix

| Surface                           | Current finding                                                                                                                                                                           | Decision                                                                                                                                                        |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hosted protocol                   | Invocations is stable for custom JSON and backend/HITL contract compatibility. Responses is the Foundry-native conversation/history protocol.                                             | Add Responses alongside Invocations. Use `dual` shadow mode before any active cutover.                                                                          |
| Hosted conversation/session state | Invocations can carry thread/session identifiers but does not provide platform-managed conversation history. Responses provides native conversation/response history.                     | Keep Invocations as current/rollback path; use Responses for conversation cutover after parity tests.                                                           |
| Hosted long-term memory           | Foundry Memory Store is preview and can accept conversation items through `AIProjectClient.beta.memory_stores.begin_update_memories` when project and memory-store settings are supplied. | Keep `FOUNDRY_HOSTED_MEMORY_PROVIDER=none` by default; use `foundry` only for opt-in hosted-agent memory.                                                       |
| Hosted HITL checkpoint state      | No durable checkpoint/state API with approval audit parity has been proven for checkpoint lookup, reviewer/comments/status, resolved timestamps, and restart recovery.                    | Keep explicit resume context; make `foundry_native` fail fast until parity is proven.                                                                           |
| Workflow state                    | Current hosted workflow state is explicit context plus process-local checkpoint cache. This is not enough for final native cutover.                                                       | Define a hosted-only durable state schema; switch only after restart/resume and query parity pass.                                                              |
| HITL approval audit               | Postgres currently owns reviewer, comments, status, requested/resolved timestamps, and idempotent resolve.                                                                                | Keep Postgres projection during cutover; do not remove hosted Postgres dependency until an equivalent hosted audit store passes parity.                         |
| Backend UI history/read model     | Frontend and Playwright rely on stable backend workflow history, detail, latest output, events, and pending approval APIs.                                                                | Keep Postgres projection unchanged during cutover and for all local/Azure app-hosted flows. Remove only the Foundry-hosted dependency after native read parity. |
| Telemetry/traces                  | Foundry/App Insights traces are useful for observability but are not queryable workflow state. Responses plus OTel/App Insights configuration is required for useful portal traces.       | Keep traces additive, correlate with workflow IDs, and never use traces as checkpoint or approval source of truth.                                              |

### Protocol capability matrix

| Capability                | Invocations (current/rollback)                                                                         | Responses (cutover target)                                                                                      | Cutover decision                                                                                                                |
| ------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Endpoint shape            | `/protocols/invocations`; arbitrary JSON request/response.                                             | `/protocols/openai/responses`; OpenAI-compatible Responses schema.                                              | Keep Invocations for stable backend payloads and add Responses for native Foundry conversation surfaces.                        |
| Hosted Python runtime     | `InvocationAgentServerHost` from `azure-ai-agentserver-invocations`.                                   | `ResponsesAgentServerHost` from `azure-ai-agentserver-responses`, or framework hosting adapter when compatible. | Add Responses in a separate phase; verify package compatibility before deploying.                                               |
| `agent.yaml`              | Current `protocol: invocations`.                                                                       | Add `protocol: responses`.                                                                                      | Hosted agents can expose more than one protocol; use dual protocol during shadow/canary.                                        |
| Conversation history      | Caller/backend-managed only; no platform-managed conversation history or Thread logs.                  | Platform-managed conversation/response history with response IDs and conversation/thread visibility.            | Use Responses for native Foundry conversations; keep backend event projection during cutover.                                   |
| Streaming/lifecycle       | Raw custom response or SSE controlled by the app.                                                      | Foundry/OpenAI response lifecycle and streaming events.                                                         | Preserve stable backend SSE contracts until Responses adapter proves parity.                                                    |
| HITL resume               | Works today through structured `operation=resume_hitl` payload and explicit context.                   | No native HITL checkpoint/audit API proven.                                                                     | Keep HITL resume on current explicit context until parity is proven.                                                            |
| Portal traces/thread logs | OTel spans can export to App Insights, but Foundry Thread logs are not available for Invocations runs. | Native conversation/thread artifacts are the expected portal-visible surface.                                   | Empty Traces/Thread logs for Invocations-only version is expected; add Responses and App Insights config for portal validation. |

### HITL checkpoint and workflow-state parity matrix

| Requirement                   | Current Postgres path                                              | Foundry native / Responses                                                                                                                  | MAF Durable Extension                                                     | Decision                                                                     |
| ----------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Checkpoint ID lookup          | Full support through checkpoint tables/repositories.               | No documented Foundry-native checkpoint lookup API with this schema.                                                                        | Buildable through durable orchestration instance IDs plus app mapping.    | Do not enable `foundry_native` until lookup parity exists.                   |
| Thread/conversation query     | Full workflow history/status filtering through backend projection. | Responses has conversation history; Invocations has session list only and no workflow status model.                                         | Buildable with orchestration query APIs.                                  | Backend projection remains during cutover.                                   |
| Reviewer/comments/status      | Full audit fields and transitions.                                 | No native approval audit fields.                                                                                                            | Buildable via external event payload/custom state.                        | Keep explicit hosted audit schema; do not rely on Foundry traces or memory.  |
| Requested/resolved timestamps | Full support through requested/resolved or updated timestamps.     | No native HITL lifecycle timestamps.                                                                                                        | Buildable from orchestration metadata/history plus custom state.          | Required before removing hosted Postgres dependency.                         |
| Restart recovery              | Full support through durable database state.                       | Session `$HOME`/files may persist across idle/resume, but this is session-scoped and not sufficient as a global queryable checkpoint store. | Full durable restart recovery.                                            | Need durable hosted audit/state adapter or Durable Extension before cutover. |
| Idempotent resolve            | Atomic single-transition update.                                   | Application responsibility; no platform guard.                                                                                              | Requires application-level guard before raising/handling external events. | Must be reimplemented and tested before switch.                              |

Recommended HITL path:

1. Keep `FOUNDRY_HOSTED_STATE_PROVIDER=stateless_context` for current hosted
   agent runs.
2. Add Responses for conversation/traces first; do not treat Responses as a
   checkpoint/audit store.
3. For final hosted-agent Postgres removal, choose and prove one durable HITL
   state strategy:
   - a hosted-agent-only durable audit adapter with the same fields and
     idempotent semantics as the current Postgres path, or
   - a MAF Durable Extension path with explicit reviewer/comment/status/timestamp
     state and idempotency guards.

### Trace capability matrix

| Trace surface            | Current status                                                                                                                                                                                                                                                                                                                  | Required cutover action                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Backend FastAPI spans    | App code has Azure Monitor/OpenTelemetry setup and workflow/HITL spans.                                                                                                                                                                                                                                                         | Keep unchanged for local/Azure app-hosted Postgres flows.                                                            |
| Hosted Invocations spans | Hosted code configures Azure Monitor when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set and emits `foundry_hosted.invocation` with `workflow.thread_id`, `workflow.status`, `workflow.event_count`, `workflow.order_id`, `workflow.action`, `workflow.requires_hitl`, and HITL checkpoint/decision attributes when applicable. | Inject the Foundry-project-linked App Insights connection string at hosted deploy time.                              |
| Hosted Responses spans   | Dual/Responses handlers emit `foundry_hosted.response`; conversation shadow posts emit `foundry_hosted.responses_shadow` with `foundry.synthetic=true`, `foundry.source_protocol=invocations`, and `foundry.source_operation`.                                                                                                  | Use these spans to separate synthetic shadow records from active Responses canary records.                           |
| Foundry portal traces    | Empty for Invocations-only runs is expected when Responses/thread artifacts and/or linked App Insights ingestion are missing.                                                                                                                                                                                                   | Validate after adding Responses, setting `OTEL_SERVICE_NAME=maf-foundry-hosted-agent`, and configuring App Insights. |
| Content recording        | Disabled by default through `AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED=false` and backend `OTEL_RECORD_CONTENT=false`.                                                                                                                                                                                                     | Keep disabled by default; enable only for temporary debug with privacy review.                                       |
| Correlation              | Backend/hosted spans carry workflow/thread/checkpoint attributes.                                                                                                                                                                                                                                                               | Preserve trace context across HITL pause/resume and map Foundry response IDs to backend run/thread IDs.              |

Live trace validation remains a deployment gate, not a local-only gate. It
requires `API_URL`, `WEB_URL` when UI parity is in scope, and
`AZURE_LOG_ANALYTICS_WORKSPACE_ID`; then run the `azure-telemetry-validation`
skill's hosted stimulus and KQL checks against the Foundry-project-linked
Application Insights workspace.

### Cutover provider flags

- `FOUNDRY_HOSTED_PROTOCOL=invocations` keeps the current invocation-only behavior.
- `FOUNDRY_HOSTED_PROTOCOL=dual` is the cutover hosted-package setting because
  `agent.yaml` declares both `invocations` and `responses`.
- `FOUNDRY_HOSTED_PROTOCOL=dual` shadows Responses while Invocations remains
  active.
- `FOUNDRY_HOSTED_PROTOCOL=responses` enables active Responses canary after
  parity gates.
- `FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=none|responses` controls whether
  Invocations user turns are copied to the Responses endpoint for portal
  conversation/trace comparison.
- Shadowed Responses are synthetic and must carry `metadata.synthetic=true`,
  `metadata.source_protocol=invocations`, and
  `metadata.operation=shadow_conversation`; active Responses canaries do not use
  those metadata values.
- `FOUNDRY_HOSTED_STATE_PROVIDER=stateless_context` remains the safe state
  default.
- Hosted checkpoint state now carries the local audit schema needed for parity:
  checkpoint/thread/order/action/amount, status, requested/resolved timestamps,
  reviewer, comments, decision, and telemetry trace context. Resolution is
  idempotent: once a checkpoint leaves `pending`, duplicate resolutions return
  the original audit record without mutating reviewer/comments/decision.
- `FOUNDRY_HOSTED_STATE_PROVIDER=dual` and `foundry_native` remain blocked until
  a durable Foundry-native checkpoint/state API can persist that same audit
  schema across hosted-worker restarts.
- `FOUNDRY_HOSTED_MEMORY_PROVIDER=foundry` remains opt-in because Memory Store
  is preview.
- Local and Azure app-hosted paths continue to use app-wide `STORE_PROVIDER` and
  `MEMORY_PROVIDER` with Postgres-backed defaults.

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

## Self-contained Foundry deployment path

- A dedicated Foundry azd project now exists at `infra/foundry-hosted/azure.yaml`.
- The Foundry path is designed for one-command deployment (`azd up`) that provisions its own networking and dependencies:
  - Foundry account/project + model deployments
  - dedicated VNET/subnets + private DNS + private endpoints
  - Storage + Cosmos + AI Search + project connections
  - ACR + App Insights + Log Analytics
- This isolates Foundry hosted-agent infrastructure from app-hosted Container Apps infrastructure and reduces operator ambiguity for private-network deployments.
