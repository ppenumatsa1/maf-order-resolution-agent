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

- `workflow.start`, `workflow.complete`
- `agent.triage`, `agent.policy`, `agent.resolution`
- OTEL resource attributes:
  - `service.name`: `maf-customer-resolution`
  - `deployment.environment`: `local|dev|prod`

## App Insights Wiring

Set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` to your collector or Azure Monitor endpoint and route traces from backend spans.
