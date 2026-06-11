# Copilot Instructions

This repository implements a Microsoft Agent Framework (MAF SDK) customer order resolution workflow with HITL checkpoints.

## Primary Goals

- Keep one MAF-based business workflow path (no deterministic fallback path).
- Deterministic triage fallback is allowed only when Foundry Models env vars are
  absent; do not add a separate deterministic fallback orchestration path.
- Keep HITL behavior deterministic and testable.
- Keep API response contracts stable for frontend and Playwright tests.

## Workflow Guardrails

- Keep API, application service, MAF runtime, and infrastructure concerns separated:
  - `backend/app/api/v1/routers/*` owns HTTP/SSE routes.
  - `backend/app/api/v1/schemas/*` owns API contracts.
  - `backend/app/modules/order_resolution/*` owns service/domain seams, ports, workflow context/events, and projection logic.
  - `backend/app/core/*` owns config, database, telemetry, and runtime composition.
  - `backend/app/infrastructure/*` is the repository-pattern/adapters namespace.
  - `backend/app/maf/*` owns the MAF runtime namespace.
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
  - Observe MAF executor telemetry from streamed `executor_invoked`,
    `executor_completed`, and `output` events.
  - Preserve checkpoint trace context for HITL pause/resume telemetry so
    approval spans remain correlated with the original workflow operation.
  - Emit and persist correlated execution identifiers (`workflow_run_id`, `session_id`, `thread_id`, `event_id`).

## Local Validation Commands

- Backend lint + tests: `make test`
- Eval harness: `make eval-backend`
- Playwright E2E: `make test-e2e`
- Docker E2E profile: `make docker-test`
- Deterministic review/test gate: `./scripts/skills/design-review-skill.sh`

## Repository Skills

- Use `design-review` as the final deterministic local gate.
- Use `docs-sync` for documentation updates after code, IaC, script, or behavior changes.
- Use `backend-boundary-review` for API/modules/core/infrastructure/MAF separation and shim import safety.
- Use `local-validation` for local unit/integration/e2e checks.
- Use `iac-review` for Azure/Foundry IaC, Docker, AZD, RBAC, secret, smoke, and security review without deployment.
- Use `azure-validation` for Azure readiness/live endpoint checks without deployment.
- Use `azure-deployment` only after Azure validation passes.
- Use `azure-telemetry-validation` after hosted deployment to verify App Insights request, dependency, trace, HITL correlation, and exception data.
- Use `release-readiness` to orchestrate the focused skills for PR/release handoff.

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
