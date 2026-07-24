# Schema, I/O, and Telemetry

## Chat Run Request

```json
{
  "message": "Order ORD-1009 is delayed by 5 days.",
  "thread_id": "optional",
  "session_id": "optional",
  "customer_id": "cust-demo"
}
```

## SSE Event Envelope

```json
{
  "id": "uuid",
  "type": "workflow.stage | tool.call | hitl.request | hitl.response | checkpoint.created | workflow.output",
  "thread_id": "uuid",
  "timestamp": "2026-06-08T00:00:00Z",
  "payload": {}
}
```

## Rich Event Envelope

The legacy SSE stream is unchanged at `/api/chat/stream/{thread_id}`. A parallel rich stream is available at `/api/chat/stream/{thread_id}/rich` for AG-UI-compatible clients:

```json
{
  "type": "workflow.rich",
  "version": "ag-ui-compatible.v1",
  "id": "native-event-id:rich:1",
  "thread_id": "uuid",
  "timestamp": "2026-06-08T00:00:00Z",
  "source": "maf-order-resolution",
  "native_event": {},
  "events": []
}
```

Native workflow events remain the source of truth. The rich stream maps stages to step lifecycle events, tool calls to tool lifecycle/result events, terminal outputs to assistant text and run-finished events, HITL/checkpoints to custom events, failures to run-error events, and unknown native events to raw events. Each SSE frame contains one rich envelope with one or more AG-UI-compatible events; clients that need native AG-UI framing should flatten `events` in order. The stream emits `RUN_STARTED` in the first rich envelope for each subscription.

In the private ACA lane, the browser reaches both streams through the frontend's
same-origin `/api` proxy. The internal Responses wrapper tails the persisted
workflow-event projection for both native and rich streams; it does not rename
or replace native event types, and browser configuration contains no backend or
Foundry endpoint.

## HITL Response Request

```json
{
  "checkpoint_id": "uuid",
  "decision": "approve",
  "reviewer": "ops-analyst",
  "comments": "optional"
}
```

## Telemetry Conventions

- Business spans:
  - `workflow.run`
  - `workflow.hitl_waiting`
  - `workflow.hitl_resume`
  - `workflow.resolution_submit`
- Event spans retain the emitted event name with dots replaced by underscores, for example `workflow.hitl_request` and `workflow.workflow_output`.
- OTEL resource attributes:
  - `service.name`: `maf-customer-resolution`
  - `deployment.environment`: `local|dev|prod`

## App Insights Wiring

Telemetry is enabled by default (`ENABLE_TELEMETRY=true`) and MAF instrumentation is enabled by default (`ENABLE_INSTRUMENTATION=true`). Local processes can set `APPLICATIONINSIGHTS_CONNECTION_STRING` to export through Azure Monitor Application Insights. Hosted private agents receive the same canonical variable from the Foundry project's supported `ApplicationInsights` connection; `backend/agent.yaml` does not map connection-string aliases or reconstruct split fields. Local OTLP tracing remains available through `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.

The internal FastAPI wrapper accepts either the canonical or full
`APPINSIGHTS_CONNECTION_STRING` alias, preferring the region-aware full value.
FastAPI instrumentation excludes health probes and chat SSE transport requests
so App Insights keeps workflow, model, checkpoint, and HITL correlation signal
without Container Apps probe noise.

MAF workflow stream events are observed from `workflow.run(..., stream=True)` for `executor_invoked`, `executor_completed`, and terminal `output` events. Full event payload/content is not recorded unless `OTEL_RECORD_CONTENT=true`.

MAF middleware enriches emitted workflow events with `workflow_run_id` and `session_id`, records streamed MAF event/usage hooks, and emits `workflow.failed` for real workflow failures before re-raising the original exception.

Hosted invocation spans emit `gen_ai.operation.name`,
`gen_ai.agent.name`, and `gen_ai.conversation.id`. Conversation-level Foundry
evaluation additionally requires `gen_ai.input.messages` and
`gen_ai.output.messages`; those content attributes are emitted only when the
private validation agent is deployed with
`FOUNDRY_TRACE_EVALUATION_RECORD_CONTENT=true` **and** the individual request
contains the pass-through header
`x-client-trace-evaluation-record-content: true`. The hosted E2E script marks
only its validation requests, so later ordinary hosted traffic remains
redacted. Global
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` and `OTEL_RECORD_CONTENT`
remain disabled.

FastAPI request instrumentation is applied after app creation so hosted API calls are expected in `AppRequests`. Workflow, MAF, and Foundry model spans are exported as dependencies.

HITL pause/resume crosses HTTP requests, so the checkpoint state stores a sanitized `telemetry_trace_context`. The approval path restores that context before creating `workflow.hitl_resume`, which keeps the HITL response and final output correlated with the original `workflow.hitl_waiting` operation in Application Insights.

Private hosted E2E records low-risk, high-risk approval/resume, and damaged-item
approval/resume conversation IDs in
`backend/.foundry/results/hosted-e2e-evidence.json`. Foundry evaluation judges
those exact traces, and `scripts/foundry/verify_telemetry.sh` requires all three
conversation IDs to appear in Application Insights with no correlated
exceptions. The release artifact also includes
`foundry-report.json` and `telemetry-verification.json`.
