# Agents Guide

This file describes expected behavior for coding agents working in this repository.

## Project Context

- Backend: FastAPI + deterministic and MAF SDK workflow paths.
- Frontend: React + Vite, consumes SSE workflow events.
- Workflow checkpointing: file-based storage under `backend/data/checkpoints`.

## Agent Change Policy

1. Keep changes minimal and focused on user request.
2. Preserve API compatibility unless explicitly asked to break it.
3. If HITL logic changes, update docs and tests in the same change set.
4. Never remove coverage for:

- low-risk no-HITL flow
- high-risk HITL flow and resume flow

## Required Verification Before Completing Work

Run and report:

- `make test`
- `make eval-backend`
- `make test-e2e`

If a suite cannot run because of missing runtime dependencies (for example browser binaries), report the blocker and the exact command needed to unblock.

## HITL Testing Baseline

Use these baseline scenarios:

- `ORD-1009` delayed -> expect `hitl.request`
- `ORD-1001` late delivery -> expect no `hitl.request`
- damaged item message -> expect `hitl.request`

Reference details:

- `docs/design/hitl-approval-conditions.md`
