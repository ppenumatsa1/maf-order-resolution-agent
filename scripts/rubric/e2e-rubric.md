# E2E Demo Rubric

## Scoring

- 0 = Fail
- 1 = Partial
- 2 = Pass

## Criteria

1. Sequential Orchestration

- Evidence: timeline shows `triage`, `policy`, `resolution` in order.
- Score:
  - 0: out-of-order or missing stages
  - 1: order mostly correct but one missing stage payload
  - 2: all stages ordered and complete

2. Tool + MCP Integration

- Evidence: at least one `tool.call` event includes local tool details and MCP result source.
- Score:
  - 0: no tool.call
  - 1: tool.call exists but missing MCP/local split
  - 2: full local+MCP metadata visible

3. HITL Gate and Resume

- Evidence: `hitl.request` emitted, approval/rejection accepted, workflow continues to terminal state.
- Score:
  - 0: no HITL when expected or no resume
  - 1: HITL works but flaky terminal state
  - 2: deterministic pause and resume

4. Checkpoint Durability

- Evidence: checkpoint file created for HITL flows in `backend/data/checkpoints`.
- Score:
  - 0: none created
  - 1: created but missing required state fields
  - 2: created with thread, status, and state payload

5. Output Quality

- Evidence: final output includes action and status and references order id.
- Score:
  - 0: malformed output
  - 1: output present but missing key field
  - 2: complete output contract

6. Observability Baseline

- Evidence: service starts with OTEL provider, spans created for workflow and agent stages.
- Score:
  - 0: no spans/signals
  - 1: partial spans only
  - 2: workflow + stage spans present

## Pass Threshold

- Minimum 10/12 on automated runs.
- Any score 0 in criteria 1, 3, or 4 is automatic fail.
