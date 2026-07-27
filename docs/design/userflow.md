# User Flow

## Current contract

The React UI submits requests to the FastAPI MAF application and consumes the
native SSE stream. The same application contract is used locally and by the
planned Container Apps deployment.

1. An operator submits an order issue with `POST /api/chat/run`.
2. The UI subscribes to `GET /api/chat/stream/{thread_id}`.
3. The MAF workflow performs triage, policy retrieval, and resolution.
4. A low-risk case emits `workflow.output`.
5. A risky case emits `checkpoint.created` and `hitl.request`.
6. The operator sends an approval or rejection to `POST /api/hitl/respond`.
7. The workflow resumes and emits `hitl.response` plus terminal
   `workflow.output`.

Repeated responses for the same checkpoint are idempotent and must not create
duplicate terminal events.

## Read and stream endpoints

- `GET /api/chat/stream/{thread_id}/rich` is an additive rich-event stream.
- `GET /api/workflows`
- `GET /api/workflows/{thread_id}`
- `GET /api/workflows/{thread_id}/events`
- `GET /api/sessions/{session_id}/messages`

## Stable events

- `workflow.stage`
- `tool.call`
- `checkpoint.created`
- `hitl.request`
- `hitl.response`
- `workflow.output`

The native stream remains the source of truth. The rich stream must not rename
or replace it.

## Baselines

- `ORD-1001` late delivery: no HITL expected.
- `ORD-1009` delayed/high amount: HITL expected.
- Damaged item: HITL expected.

See [HITL approval conditions](hitl-approval-conditions.md) for exact rules.
