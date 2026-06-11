---
name: backend-boundary-review
description: Review backend changes for canonical module ownership, shim import safety, HITL coverage, and API/event contract stability.
---

# Backend Boundary Review Skill

Use this skill when reviewing backend changes for repository boundary compliance.

## Canonical ownership

- `backend/app/api/v1/routers/*` owns HTTP/SSE routes only.
- `backend/app/api/v1/schemas/*` owns API request/response contracts.
- `backend/app/modules/order_resolution/*` owns service/domain seams, policies, HITL, ports, and event projection.
- `backend/app/core/*` owns config, database, telemetry, and runtime composition.
- `backend/app/infrastructure/*` owns adapters, repositories, events, RAG, and MCP integrations.
- `backend/app/maf/*` owns MAF runtime, workflows, tools, clients, and prompts.

## Review guardrails

- Reject new canonical code that imports legacy compatibility shim paths.
- Tolerate existing compatibility shims only when they are unchanged or being safely removed.
- Keep API and emitted event contracts stable unless the task explicitly requests a contract change.
- Do not remove or rename event types without updating frontend consumers, tests, and docs.
- Require tests and eval cases for HITL behavior changes.
- Require updates to `docs/design/hitl-approval-conditions.md` when HITL decision logic changes.

## Required checks

1. Inspect touched backend files for misplaced HTTP, schema, domain, core, infrastructure, or MAF runtime responsibilities.
2. Search changed imports for legacy shim paths and block newly introduced usage.
3. For HITL logic changes, verify matching updates in backend tests and/or `backend/evals/cases.jsonl`.
4. For API/event contract changes, verify the frontend, tests, and documentation were intentionally updated.

## Pass/fail behavior

- Pass when changes preserve canonical boundaries and required contract/HITL updates are present.
- Fail when new code crosses boundaries, imports legacy shims, or changes HITL/API/event behavior without matching tests, evals, and docs.
