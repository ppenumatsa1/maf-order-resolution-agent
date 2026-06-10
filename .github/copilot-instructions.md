# Copilot Instructions

This repository implements a Microsoft Agent Framework (MAF SDK) customer order resolution workflow with HITL checkpoints.

## Primary Goals

- Keep one MAF-based business workflow path (no deterministic fallback path).
- Keep HITL behavior deterministic and testable.
- Keep API response contracts stable for frontend and Playwright tests.

## Workflow Guardrails

- Any change to HITL decision logic must update:
  - `docs/design/hitl-approval-conditions.md`
  - tests in `backend/tests/test_workflow.py` and/or eval cases in `backend/evals/cases.jsonl`
- Do not remove or rename emitted event types without updating frontend/event consumers:
  - `workflow.stage`
  - `tool.call`
  - `checkpoint.created`
  - `hitl.request`
  - `hitl.response`
  - `workflow.output`
- Follow sample-derived MAF execution patterns:
  - Intermediate executors use `ctx.send_message(...)`; terminal executors use `ctx.yield_output(...)`.
  - Treat workflow runs as resumable across multiple `run(...)` calls.
  - Handle approvals via explicit request/response objects keyed by request id.
  - Do not blindly retry side-effecting tools; enforce idempotency keys for write operations.
  - Keep per-agent context/config scoped by agent identity.
  - Emit and persist correlated execution identifiers (`workflow_run_id`, `session_id`, `thread_id`, `event_id`).

## Local Validation Commands

- Backend lint + tests: `make test`
- Eval harness: `make eval-backend`
- Playwright E2E: `make test-e2e`
- Docker E2E profile: `make docker-test`
- Deterministic review/test gate: `./scripts/skills/design-review-skill.sh`

## Baseline Test Inputs

- `ORD-1009` -> high amount (`185.0`) -> typically HITL.
- `ORD-1001` -> low amount (`79.0`) -> no HITL unless damaged/manual review rule applies.

## Documentation Contract

When behavior changes, update these docs in the same PR:

- `README.md`
- `backend/README.md`
- `docs/design/userflow.md`
- `docs/design/hitl-approval-conditions.md`
- `.github/copilot-instructions.md`
- `agents.md`
