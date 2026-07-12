---
name: agent-framework-foundry-py
description: Maintain this order-resolution service's Microsoft Agent Framework workflow with agent-framework-foundry and FoundryChatClient. Use for Foundry model configuration, SequentialBuilder orchestration, MAF middleware and streamed event telemetry, resumable checkpoint-backed HITL approval flows, and MAF workflow tests.
---

# Microsoft Agent Framework Foundry Workflows for Order Resolution

Use this repository-owned skill for the application's MAF workflow path. It applies to
`agent-framework` and `agent-framework-foundry`; it does not cover the absent
`agent-framework-azure-ai` package or `AzureAIAgentsProvider`.

## Runtime and ownership

- `backend/app/maf/clients.py` owns `FoundryModelsConfig` and creates
  `agent_framework.foundry.FoundryChatClient` with `DefaultAzureCredential`.
  Resolve Foundry configuration through the existing `FOUNDRY_PROJECTS_ENDPOINT` and
  `FOUNDRY_MODEL_DEPLOYMENT_NAME` contract; do not introduce a second provider path.
- `backend/app/maf/workflows/order_resolution.py` owns the MAF orchestration. Keep its
  one `SequentialBuilder` workflow with the triage, policy, and resolution agents.
  Intermediate stages communicate through the sequence; the workflow's final output is
  consumed from the streamed run.
- Keep HTTP/SSE concerns in `backend/app/api/v1/routers/*`, API schemas in
  `backend/app/api/v1/schemas/*`, application/domain seams and event projection in
  `backend/app/modules/order_resolution/*`, composition in `backend/app/core/*`, and
  persistence adapters in `backend/app/infrastructure/*`.

## Foundry and workflow patterns

- Create agents from `FoundryChatClient.as_agent(...)`. Keep each agent's instructions,
  options, and middleware scoped to that agent.
- Build the ordered orchestration with `SequentialBuilder`, stream `workflow.run(...)`,
  and observe `executor_invoked`, `executor_completed`, and `output` events. Do not
  replace the MAF workflow with a deterministic orchestration path. When Foundry model
  configuration is absent, only the existing deterministic triage summary is permitted.
- Keep cross-cutting behavior in `backend/app/maf/middleware.py`: correlate
  `workflow_run_id`, `session_id`, and `thread_id`; safely enrich events; record model
  usage; and emit a correlated failure event before re-raising.
- Preserve native SSE event names (`workflow.stage`, `tool.call`, `checkpoint.created`,
  `hitl.request`, `hitl.response`, and `workflow.output`). Rich/AG-UI events are
  additive projections, never replacements.

## Checkpoint-backed HITL

- Use the existing explicit request/response boundary: create and persist a checkpoint,
  emit `checkpoint.created` and `hitl.request`, then resume through
  `handle_hitl_response(...)` using that checkpoint ID. Do not complete an approval
  implicitly or bypass the response path.
- Preserve the checkpoint's trace context when resuming, record the reviewer decision,
  and keep checkpoint resolution idempotent.
- Keep side-effecting resolution submission behind the existing idempotency store. Retry
  only model and read operations; do not blindly retry writes.
- If HITL decision conditions change, update
  `docs/design/hitl-approval-conditions.md` and the low-risk, high-risk/resume, and
  damaged-item coverage in `backend/tests/test_workflow.py` and/or
  `backend/evals/cases.jsonl`.

## Current Microsoft documentation

Use Microsoft Learn's current Agent Framework documentation before changing SDK APIs:

| Need | Lookup |
|---|---|
| Foundry model client and `FoundryChatClient` | `microsoft_docs_search(query="Microsoft Agent Framework Python FoundryChatClient")` |
| Sequential orchestration and streaming | `microsoft_docs_search(query="Microsoft Agent Framework Python SequentialBuilder workflow streaming")` |
| Human-in-the-loop workflow requests and resume | `microsoft_docs_search(query="Microsoft Agent Framework Python sequential human in the loop request info")` |
| Middleware and telemetry APIs | `microsoft_docs_search(query="Microsoft Agent Framework Python middleware telemetry")` |

