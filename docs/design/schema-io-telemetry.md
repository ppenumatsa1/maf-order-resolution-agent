# Schema, I/O, and Telemetry

## Chat run request

```json
{
  "message": "Order ORD-1009 is delayed by 5 days.",
  "thread_id": "optional",
  "session_id": "optional",
  "customer_id": "cust-demo"
}
```

## Native SSE envelope

```json
{
  "id": "uuid",
  "type": "workflow.stage | tool.call | hitl.request | hitl.response | checkpoint.created | workflow.output",
  "thread_id": "uuid",
  "timestamp": "2026-07-27T00:00:00Z",
  "payload": {}
}
```

The native stream at `/api/chat/stream/{thread_id}` is the stable source of
truth. `/api/chat/stream/{thread_id}/rich` is additive and retains the native
event payload.

## HITL response request

```json
{
  "checkpoint_id": "uuid",
  "decision": "approve",
  "reviewer": "ops-analyst",
  "comments": "optional"
}
```

## Telemetry

- Workflow and approval telemetry carries `workflow_run_id`, `session_id`,
  `thread_id`, and `event_id`.
- Checkpoint trace context preserves correlation across approval and resume.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` enables Application Insights export.
- `OTEL_RECORD_CONTENT=false` is the default content-safety posture.
- Model-inference dependencies may be exported to Application Insights; Foundry
  report evaluation is non-blocking evidence.
