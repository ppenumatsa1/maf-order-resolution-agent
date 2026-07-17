# PRD - Customer Order Resolution Multi-Agent Demo

## Objective

Build a demo-ready multi-agent orchestration using Microsoft Agent Framework-aligned patterns with sequential workflow execution and production-style capabilities.

## Core Features

- Sequential multi-agent orchestration (triage -> policy -> resolution).
- Tools integration (local deterministic tools).
- MCP integration (remote when configured, local fallback otherwise).
- Human-in-the-loop (HITL) approval before sensitive actions.
- Memory/session state for multi-turn continuity.
- Checkpointing and resume for durable pauses.
- Observability with OTEL and App Insights-ready exporters.
- Evals with baseline dataset and report.
- AGUI-style streaming events over SSE.
- FastAPI backend consumed by React + Vite UI.

## Non-Goals (v1)

- Production auth/RBAC.
- Full cloud deployment automation.
- Parallel/branching orchestrations.

## Acceptance Criteria

1. User request triggers all 3 agent stages in order.
2. At least one tool call and one MCP call event are emitted.
3. HITL request is emitted for high-risk actions and can be approved/rejected.
4. Workflow resumes from checkpoint and produces final output.
5. Follow-up messages within the same thread use prior memory.
6. OTEL traces are created and configurable for App Insights export.
7. Eval harness produces report with pass/fail metrics.

## Delivery contract

Implementation authority and release evidence requirements are defined in `docs/design/engineering-operating-model.md`.
