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

FastAPI request instrumentation is applied after app creation so hosted API calls are expected in `AppRequests`. Workflow, MAF, and Foundry model spans are exported as dependencies.

HITL pause/resume crosses HTTP requests, so the checkpoint state stores a sanitized `telemetry_trace_context`. The approval path restores that context before creating `workflow.hitl_resume`, which keeps the HITL response and final output correlated with the original `workflow.hitl_waiting` operation in Application Insights.

Post-deploy Application Insights verification is captured in `.github/skills/azure-telemetry-validation/SKILL.md`. The routine runs hosted ORD-1001/ORD-1009 flows and validates `AppRequests`, `AppDependencies`, `AppTraces`, and `AppExceptions` with KQL.
