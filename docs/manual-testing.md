# Manual Testing Guide

## Local full-stack workflow

```bash
make up
```

Open `http://localhost:5173`, submit a case, and verify the local FastAPI/SSE
timeline. Every run should include the expected `workflow.stage`, `tool.call`,
and terminal `workflow.output` events.

| Scenario | Prompt | Expected result |
| --- | --- | --- |
| Low risk | `Order ORD-1001 arrived late by 1 day.` | `completed`; no `hitl.request` |
| High value | `Order ORD-1009 is delayed by 5 days.` | `waiting_approval`, then `completed` after approval |
| Damaged reject | `Order ORD-1001 arrived damaged and broken.` | `waiting_approval`, then `escalated` after rejection |

For a broader local matrix:

```bash
make manual-matrix
```

Verify history through `GET /api/workflows/{thread_id}` and
`GET /api/workflows/{thread_id}/events`. The persisted tables are
`workflow_runs`, `workflow_events`, `conversation_messages`, `checkpoints`, and
`approvals`.

## Public Foundry hosted workflow

The hosted agent uses the Responses protocol rather than the FastAPI/SSE UI.
Run the authenticated release sequence:

```bash
make foundry-release
```

It covers ORD-1001, ORD-1009 approval, damaged-item rejection, and duplicate
HITL response behavior. Conversation evidence is written to
`backend/.foundry/results/hosted-e2e-evidence.json`.
