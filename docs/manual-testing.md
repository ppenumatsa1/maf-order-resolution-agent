# Manual Testing Guide

This guide provides end-to-end manual test examples for:

1. regular low-risk flow (no HITL)
2. high-risk flow with HITL pause and resume
3. failure and recovery behavior

Scenarios are aligned with the rubric in [scripts/rubric/e2e-rubric.md](scripts/rubric/e2e-rubric.md).

## Preconditions

1. Start the stack.

```bash
make up
```

2. Confirm backend and frontend are reachable.

- Backend health: [backend/app/main.py](backend/app/main.py)
- UI: [frontend/src/App.tsx](frontend/src/App.tsx)

3. Ensure Postgres is running and schema is initialized via [backend/app/core/database.py](backend/app/core/database.py).

4. Open the UI and keep browser devtools network tab visible for SSE validation.

## Common Checks for Every Scenario

For each run, verify these signals from timeline/API:

1. Sequential orchestration events in order:

- `workflow.stage` triage started/completed
- `workflow.stage` policy_retrieval started/completed
- `workflow.stage` resolution completed

2. At least one `tool.call` event includes local tool and MCP result metadata.

3. Final output includes action, status, and order id.

4. Workflow is queryable from:

- `GET /api/workflows`
- `GET /api/workflows/{thread_id}`
- `GET /api/workflows/{thread_id}/events`

5. Postgres persistence is visible in tables:

- `workflow_runs`
- `workflow_events`
- `conversation_messages`
- `checkpoints` (when applicable)
- `approvals` (when applicable)

## ORD-1001 to ORD-1010 Cross-Use-Case Matrix

Use this matrix as a repeatable parity suite after shim removal, while validating Azure app-hosted runtime, and later moving to Foundry-hosted runtime.

For a quick executable check, run the script-backed matrix against any backend URL:

```bash
make manual-matrix
API_URL="https://<backend-host>" make manual-matrix
MANUAL_MATRIX_ARGS="--request-timeout 120 --timeout 90 --case-delay 15" API_URL="https://<backend-host>" make manual-matrix
scripts/manual/run-manual-matrix.sh http://localhost:8000 --case ORD-1009
```

The runner uses [frontend/src/data/manualCases.json](../frontend/src/data/manualCases.json) and prints a PASS/FAIL table with observed status, HITL detection, thread id, and failure reasons. Use `MANUAL_MATRIX_ARGS` with `--case-delay` for low-capacity hosted Foundry deployments to avoid model throttling while preserving the same workflow behavior.

The Workflow Studio also includes a collapsed **Test Tools** panel with a **Manual Test Matrix** that uses the same fixture expectations:

1. Open the UI.
2. Expand **Show Manual Test Matrix** only for demos, smoke checks, or parity validation.
3. Use **Load prompt** to inspect or edit a scenario prompt in the composer.
4. Use **Run case** to execute one scenario through `/api/chat/run`.
5. Use **Run all** only when you want to generate a full local parity run.
6. Confirm each case shows PASS/FAIL, observed status, HITL result, evidence count, and generated thread id.
7. Use **View run** to re-open the generated workflow timeline, output, RAG evidence, and metadata.

The panel is an operator verification aid, not a separate backend test framework. The script runner remains the automation-friendly parity check for local and Azure URLs.

Current deterministic local-runtime caveat:

- Messages containing `1009` resolve to workflow order id `ord-1009` with amount `185.0`.
- All other order ids currently resolve to workflow order id `ord-1001` with amount `79.0`.
- Therefore, `ORD-1002` through `ORD-1008` and `ORD-1010` are still useful as prompt-level regression cases, but the current backend will persist/emit `ord-1001` for those runs until order lookup is generalized.

| Case | Prompt | Primary path | Decision to take | Expected signals |
| --- | --- | --- | --- | --- |
| ORD-1001 | `Order ORD-1001 arrived late by 1 day. What can you do?` | Happy path, no HITL | None | `policy_retrieval` runs; no `hitl.request`; final `workflow.output.status=completed`; emitted order id is `ord-1001`. |
| ORD-1002 | `Order ORD-1002 has the wrong item in the box.` | Wrong-item no-HITL path | None | `tool.call.policy_evidence_ids` exists; no `hitl.request`; final status `completed`; emitted order id is currently `ord-1001`. |
| ORD-1003 | `Order ORD-1003 is delayed and I want the policy explanation before any action.` | RAG evidence visibility | None | `workflow.stage` includes `policy_retrieval`; `tool.call.policy_retrieval.provider` and `query_id` are present; final status `completed`. |
| ORD-1004 | `Order ORD-1004 arrived damaged and broken.` | Damaged-item HITL | Approve | `checkpoint.created` then `hitl.request`; approval emits one `hitl.response`; final status `completed`. |
| ORD-1005 | `Order ORD-1005 arrived broken and the customer asks for a replacement.` | Damaged-item HITL rejection | Reject | `hitl.request` appears; rejection emits `workflow.output.status=escalated`; no duplicate terminal output. |
| ORD-1006 | `Order ORD-1006 was delayed but package condition is fine.` | Low-risk durability case | None | Complete the run, restart backend, then verify workflow details/events/messages are still queryable. |
| ORD-1007 | `Order ORD-1007 is late. Start this request in session manual-session-1007.` | Session history continuity | None | Use a fixed `session_id`; verify `/api/sessions/manual-session-1007/messages` returns the user and assistant messages. |
| ORD-1008 | `Order ORD-1008 arrived damaged. Please pause for supervisor review.` | Pause/resume checkpoint | Approve after delay | Wait on `waiting_approval`, refresh UI or reopen details, then approve; final status `completed`. |
| ORD-1009 | `Order ORD-1009 is delayed by 5 days. I need compensation.` | High-amount HITL | Approve | `amount=185.0`; `hitl.request` emitted; approval resumes to final `completed`; emitted order id is `ord-1009`. |
| ORD-1010 | `Order ORD-1010 has a normal late-delivery question and needs no refund escalation.` | Post-migration smoke case | None | No HITL; final status `completed`; use this as a smoke test after canonical layout/Azure/Foundry moves. |

For each row, capture:

1. input prompt and generated `thread_id`
2. full event sequence from `/api/workflows/{thread_id}/events`
3. final `workflow_runs.status`
4. any checkpoint/approval id
5. observed `tool.call.policy_retrieval.provider`, `query_id`, and `policy_evidence_ids`

## Azure App-Hosted Parity Smoke

After Azure deployment, run the hosted smoke script with the deployed backend and frontend URLs:

```bash
infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"
EXPECT_TRIAGE_MODE=foundry_models infra/azure-apphosted/runtime/smoke-test.sh "$API_URL" "$WEB_URL"
```

This validates:

1. backend `/health`
2. frontend `/health`
3. low-risk `ORD-1001` emits `workflow.output` without `hitl.request`
4. high-risk `ORD-1009` emits `hitl.request`
5. optional Foundry triage metadata when `EXPECT_TRIAGE_MODE=foundry_models` is set

Then use the ORD-1001 to ORD-1010 matrix above for manual parity before moving to Foundry-hosted runtime.

## Three-target parity gate (local + Azure + Foundry)

Use the parity runner when you need one comparable pass/fail view across all endpoints.

Required environment variables (can be loaded from `maf-ora-central` `.env` via `PARITY_ENV_FILE`):

```bash
PARITY_LOCAL_API_URL=http://localhost:8000
PARITY_LOCAL_WEB_URL=http://localhost:5173
PARITY_AZURE_API_URL=https://<azure-backend-host>
PARITY_AZURE_WEB_URL=https://<azure-web-host>
PARITY_FOUNDRY_API_URL=https://<foundry-backend-host>
PARITY_FOUNDRY_WEB_URL=https://<foundry-web-host>
```

Commands:

```bash
make parity-local
make parity-hosted
make parity-all
```

- `parity-local` and `parity-hosted` are quick subset checks.
- `parity-all` is the required full gate and enforces all three targets.
- Reports are generated under `scripts/parity/reports/` in JSON and markdown.

For hosted Playwright runs against low-capacity Foundry model deployments, keep local defaults fast but add quota-aware environment overrides:

```bash
PLAYWRIGHT_EXPECT_TIMEOUT_MS=60000 \
PLAYWRIGHT_TEST_TIMEOUT_MS=120000 \
PLAYWRIGHT_CASE_DELAY_MS=15000 \
PLAYWRIGHT_BASE_URL="$WEB_URL" \
make test-e2e
```

## Scenario 1: Regular Flow (No HITL)

Goal: Validate happy path without human approval.

### Input

Use a low-risk order issue (baseline):

- Order id: `ORD-1001`
- Message example: `Order ORD-1001 is delayed. Please check status and next steps.`

### Steps

1. Submit the message in UI.
2. Observe timeline events stream end to end.
3. Wait for terminal `workflow.output`.
4. Open workflow details view and confirm no pending approval state.

### Expected Results

1. No `hitl.request` event appears.
2. Status moves to `completed`.
3. `workflow.output` payload includes order id and resolution action.
4. Database checks:

- one row in `workflow_runs` for thread
- one or more rows in `workflow_events`
- conversation rows stored in `conversation_messages`
- no new pending row in `approvals`

## Scenario 2: HITL Exception Flow (Pause and Resume)

Goal: Validate high-risk flow with deterministic HITL gate.

### Input

Use a high-risk case (baseline):

- Order id: `ORD-1009`
- Message example: `Customer requests a full refund for ORD-1009 due to severe delay.`

### Steps

1. Submit message in UI.
2. Wait for `checkpoint.created` and `hitl.request` events.
3. Confirm workflow status becomes `waiting_approval`.
4. In approval panel, submit `approve`.
5. Observe `hitl.response` and resumed stages until terminal output.

### Expected Results

1. HITL pause happens exactly once for the request.
2. `checkpoint` record exists with required state fields:

- `thread_id`
- `status`
- state payload containing `run_id`, `session_id`, `customer_id`, `order_id`, `action`, `amount`

3. `approvals` row transitions from `pending` to `approved`.
4. Workflow resumes and reaches terminal state (`completed` or `escalated`, based on policy outcome).

## Scenario 3: HITL Rejection Path

Goal: Validate rejection branch and deterministic completion.

### Input

Use a damaged-item style request expected to trigger HITL:

- Message example: `Item arrived damaged. Customer asks for high-value refund and replacement.`

### Steps

1. Submit request and wait for `hitl.request`.
2. Submit `reject` in approval panel.
3. Observe `hitl.response` event and final output.

### Expected Results

1. Approval status becomes `rejected` in `approvals`.
2. Final output reflects rejection/escalation behavior.
3. No duplicate terminal events are emitted.

## Scenario 4: Duplicate HITL Response Idempotency

Goal: Ensure repeated approval/rejection submissions do not create duplicate outcomes.

### Steps

1. Trigger a HITL case.
2. Submit approval once.
3. Repeat the same approval request quickly (same checkpoint).
4. Inspect timeline and final run details.

### Expected Results

1. Only one effective state transition for the checkpoint.
2. No duplicate terminal `workflow.output` events.
3. `approvals` retains consistent final status.

## Scenario 5: Failure Path (Tool/MCP Failure)

Goal: Validate graceful failure handling and observability.

### Setup

Introduce a controlled integration failure, for example:

- point `MCP_SERVER_URL` to an invalid endpoint, or
- stop mock MCP service if running.

### Steps

1. Submit a request that requires policy retrieval/tooling.
2. Observe stage events and eventual failure outcome.
3. Open workflow details page/API.

### Expected Results

1. Workflow emits failure signal (`workflow.failed` and/or terminal failed status).
2. `workflow_runs.status` becomes `failed`.
3. Timeline preserves the events leading to failure.
4. Service remains responsive for new requests.

## Scenario 6: Restart Durability (Postgres Persistence)

Goal: Confirm runs/history survive backend restart.

### Steps

1. Complete one low-risk and one HITL flow.
2. Restart backend container/service.
3. Re-open workflows list and both workflow detail views.

### Expected Results

1. Previously completed runs are still listed.
2. Event timelines are still retrievable.
3. Conversation messages remain available for sessions.
4. Checkpoint and approval history remains intact.

## Optional SQL Spot Checks

Use these queries after any scenario (replace placeholders):

```sql
SELECT thread_id, status, current_stage, created_at, updated_at
FROM workflow_runs
WHERE thread_id = '<thread_id>';

SELECT type, timestamp
FROM workflow_events
WHERE thread_id = '<thread_id>'
ORDER BY timestamp, id;

SELECT role, content, created_at
FROM conversation_messages
WHERE thread_id = '<thread_id>'
ORDER BY id;

SELECT checkpoint_id, status, created_at, updated_at
FROM checkpoints
WHERE thread_id = '<thread_id>'
ORDER BY created_at DESC;

SELECT checkpoint_id, status, reviewer, requested_at, resolved_at
FROM approvals
WHERE thread_id = '<thread_id>'
ORDER BY requested_at DESC;
```

## Pass Guidance

Use the rubric in [scripts/rubric/e2e-rubric.md](scripts/rubric/e2e-rubric.md):

1. Target minimum `10/12`.
2. Any score `0` in sequential orchestration, HITL gate/resume, or checkpoint durability is a fail.
