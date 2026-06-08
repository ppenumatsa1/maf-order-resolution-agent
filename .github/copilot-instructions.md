# Copilot Instructions

This repository implements a deterministic/MAF-SDK customer order resolution workflow with HITL checkpoints.

## Primary Goals

- Preserve behavior parity between deterministic workflow and MAF SDK mode.
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

## Local Validation Commands

- Backend lint + tests: `make test`
- Eval harness: `make eval-backend`
- Playwright E2E: `make test-e2e`
- Docker E2E profile: `make docker-test`

## Deterministic Test Inputs

- `ORD-1009` -> high amount (`185.0`) -> typically HITL.
- `ORD-1001` -> low amount (`79.0`) -> no HITL unless damaged/manual review rule applies.

## Documentation Contract

When behavior changes, update these docs in the same PR:

- `README.md`
- `backend/README.md`
- `docs/design/userflow.md`
- `docs/design/hitl-approval-conditions.md`
