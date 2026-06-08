# User Flow

1. User enters an order issue in UI and submits.
2. UI starts SSE stream for the active thread.
3. Backend executes sequential stages:
   - Triage agent extracts order and issue type.
   - Policy agent calls tools and MCP lookup.
   - Resolution agent decides action and HITL requirement.
4. If HITL required:
   - Backend emits `checkpoint.created` and `hitl.request`.
   - UI shows approval panel.
5. Reviewer approves/rejects via UI.
6. Backend resumes from checkpoint and emits `workflow.output`.
7. UI appends final output and keeps thread available for follow-up turns.

## HITL Test Reference

For exact conditions that trigger human approval and ready-to-run test scenarios, see:

- `hitl-approval-conditions.md`
