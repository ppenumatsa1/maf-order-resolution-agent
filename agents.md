# Agents Guide

This file describes expected behavior for coding agents working in this repository.

## Project Context

- Backend: FastAPI + MAF SDK workflow path (single primary workflow story).
- Frontend: React + Vite, consumes SSE workflow events.
- Workflow checkpointing: Postgres-backed checkpoint storage via repository-pattern adapters.
- Event streaming: legacy SSE remains the stable contract; additive rich events are exposed for AG-UI-compatible clients.
- Backend package boundaries:
  - `backend/app/api/v1/routers/*` owns HTTP/SSE routes.
  - `backend/app/api/v1/schemas/*` owns API contracts.
  - `backend/app/modules/order_resolution/*` owns the application service, internal workflow models, ports, and event projection.
  - `backend/app/core/*` owns config, database, telemetry, and composition.
  - `backend/app/infrastructure/*` is the repository-pattern/adapters namespace.
  - `backend/app/maf/*` owns the MAF runtime namespace.

## Agent Change Policy

1. Keep changes minimal and focused on user request.
2. Use one MAF-based workflow path; do not introduce or retain deterministic fallback orchestration. The deterministic triage fallback is permitted only when Foundry Models env vars are absent and must not bypass MAF execution.
3. If API/event contracts intentionally change, update frontend, tests, and docs in the same change set.
4. If HITL logic changes, update docs and tests in the same change set.
5. Follow sample-derived implementation guardrails:

- intermediate executors use `ctx.send_message(...)`
- terminal executors use `ctx.yield_output(...)`
- approval flow uses explicit request/response handling keyed by request id
- retries are allowed only for read/model operations; side-effecting writes must be idempotent
- per-agent kwargs/config must remain scoped to that agent
- executor invocation/completion/output signals must stay observable and correlated
- MAF telemetry should observe streamed `executor_invoked`, `executor_completed`, and `output` events
- MAF middleware should centralize cross-cutting runtime behavior such as correlation, redaction/enrichment, usage/event observation, and explicit failure events
- HITL telemetry must preserve checkpoint trace context so approval/resume spans stay correlated with the original workflow operation
- additive rich event streams must preserve the native event payload and must not replace or rename stable SSE event types

6. Never remove coverage for:

- low-risk no-HITL flow
- high-risk HITL flow and resume flow

## Required Verification Before Completing Work

Run and report:

- `make test`
- `make eval-backend`
- `make test-e2e`
- `./scripts/skills/design-review-skill.sh` (consolidated deterministic review/test gate)

If a suite cannot run because of missing runtime dependencies (for example browser binaries), report the blocker and the exact command needed to unblock.

## Repository Skills

Use focused skills instead of one broad agent pass:

- `design-review`: final deterministic local review/test gate.
- `docs-sync`: update affected docs after code, IaC, script, or behavior changes.
- `backend-boundary-review`: check API/application/core/infrastructure/MAF separation and shim import safety.
- `local-validation`: run local unit/integration/e2e gates.
- `quick-validation`: run fast validation for app-only redeployments.
- `iac-review`: review Azure/Foundry IaC and deployment assets without deploying.
- `azure-validation`: validate Azure readiness or live endpoints without deployment.
- `azure-deployment`: deploy only after Azure validation has passed.
- `azure-telemetry-validation`: run hosted workflow stimulus and KQL checks against Application Insights after deployment.
- `release-readiness`: orchestrate relevant focused skills for PR/release handoff.

Use `scripts/skills/deployment-mode-router.sh` to route quick-vs-full validation and app-only-vs-full deployment for release work.

Legacy shim paths have been removed. Do not add code that imports or recreates `app/models.py`, `app/config.py`, `app/db.py`, `app/state.py`, `app/workflow_run_repository.py`, `app/rag_repository.py`, `workflows/*`, `tools/*`, or root `app/api/*` router shims.

## HITL Testing Baseline

Use these baseline scenarios:

- `ORD-1009` delayed -> expect `hitl.request`
- `ORD-1001` late delivery -> expect no `hitl.request`
- damaged item message -> expect `hitl.request`

Reference details:

- `docs/design/hitl-approval-conditions.md`

## Documentation Update Contract

When architecture or execution policies change, update these instruction files in the same PR:

- `.github/copilot-instructions.md`
- `agents.md`
