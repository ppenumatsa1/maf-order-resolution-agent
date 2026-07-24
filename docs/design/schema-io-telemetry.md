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

The native SSE stream remains stable at `/api/chat/stream/{thread_id}`. A
parallel rich stream is available at `/api/chat/stream/{thread_id}/rich` for
AG-UI-compatible clients:

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

Telemetry is enabled by default (`ENABLE_TELEMETRY=true`) and MAF instrumentation is enabled by default (`ENABLE_INSTRUMENTATION=true`). Set `APPLICATIONINSIGHTS_CONNECTION_STRING` to export through Azure Monitor Application Insights. Local OTLP tracing remains available through `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`.

MAF workflow stream events are observed from `workflow.run(..., stream=True)` for `executor_invoked`, `executor_completed`, and terminal `output` events. Full event payload/content is not recorded unless `OTEL_RECORD_CONTENT=true`.

MAF middleware enriches emitted workflow events with `workflow_run_id` and `session_id`, records streamed MAF event/usage hooks, and emits `workflow.failed` for real workflow failures before re-raising the original exception.

FastAPI request instrumentation is applied after app creation. Public-lane
health (`/health`, `/api/health`) and chat SSE request paths are excluded so
Container Apps probes and long-lived stream requests do not obscure workflow
signal in `AppRequests`. Workflow, MAF, Foundry model, invocation, and HITL
spans are exported as dependencies; Foundry agent-server `/readiness` remains
observable.

HITL pause/resume crosses HTTP requests, so the checkpoint state stores a sanitized `telemetry_trace_context`. The approval path restores that context before creating `workflow.hitl_resume`, which keeps the HITL response and final output correlated with the original `workflow.hitl_waiting` operation in Application Insights.

Post-deploy Application Insights verification is captured in `.github/skills/azure-telemetry-validation/SKILL.md`. The routine runs hosted ORD-1001/ORD-1009 flows and validates `AppRequests`, `AppDependencies`, `AppTraces`, and `AppExceptions` with KQL.

For operational investigation, query business dependencies first rather than
the portal's newest-first Search list:

```kusto
AppDependencies
| where TimeGenerated > ago(6h)
| where Name startswith "workflow."
| extend thread_id = tostring(Properties["workflow.thread_id"])
| project TimeGenerated, Name, thread_id, OperationId
| order by TimeGenerated desc
```

Open an end-to-end transaction for a returned `OperationId` to inspect the
correlated Foundry, workflow, model, and HITL hierarchy.
