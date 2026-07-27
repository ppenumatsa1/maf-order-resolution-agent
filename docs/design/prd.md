# PRD - Customer Order Resolution Demo

## Objective

Deliver a demo-ready, sequential MAF workflow for customer order resolution.

## Core features

- Triage, policy, and resolution stages.
- Local tools and optional MCP integration.
- Deterministic HITL approval, checkpointing, and resume.
- Durable workflow, message, and approval history in PostgreSQL.
- Native SSE timeline with an additive rich stream.
- Configurable telemetry and deterministic evaluation.
- Optional Foundry model inference and report-only evaluation.

## Non-goals

- A second orchestration path.
- Any Foundry application-hosting capability.
- Production authentication and authorization.

## Acceptance criteria

1. The workflow runs all three stages in order.
2. Low-risk cases complete without HITL.
3. High-risk cases pause and resume after approval or rejection.
4. Native SSE event names remain stable.
5. The evaluation harness reports contract outcomes.
