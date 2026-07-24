# Architecture: Order Resolution Workflow

## Purpose

This document describes the business architecture for the order-resolution use case, including runtime components, key data flows, and verifiability checkpoints.

## Business Problem

Support teams need to resolve delivery and product issues quickly while keeping risky actions (refunds, sensitive resolutions) under explicit human control. The system must:

- automate common low-risk cases,
- escalate or gate high-risk actions with HITL,
- preserve conversation and workflow history for auditability,
- provide a transparent UI timeline for operators.

## Project Goal

Deliver a verifiable multi-agent workflow for customer order issue resolution that is:

- operationally transparent (SSE timeline, workflow history),
- business-safe (deterministic HITL triggers and approvals),
- durable (Postgres-backed persistence for runs/events/messages/checkpoints),
- extensible (single MAF workflow path and Foundry-hosted Responses-native private-VNet entrypoint).

## High-Level Runtime Architecture

The private web topology has one public application ingress and private
application data planes:

```text
Browser
  -> external frontend Container App
  -> same-origin /api and SSE proxy
  -> internal FastAPI Container App
  -> managed identity + private DNS
  -> private Foundry Responses hosted MAF agent
  -> private PostgreSQL workflow state
```

The Container Apps environment is VNet-integrated on a dedicated infrastructure
subnet. It must not reuse the Foundry agent-host subnet. The frontend is the
only external-ingress app; the backend, Foundry, ACR, and PostgreSQL remain
private. In wrapper mode the internal backend invokes the hosted Responses
conversation and replays its persisted PostgreSQL workflow events through the
unchanged native SSE contract. Azure Monitor retains managed ingestion for
correlated telemetry.

```mermaid
flowchart LR
     U[Support Agent or Operator]
     UI[React Workflow Studio]
     API[FastAPI Backend]
     ORCH[MAF Sequential Workflow]
     HITL[HITL Approval Handler]
     MCP[MCP and Local Tools]
     DB[(Postgres Persistence)]

    U --> UI
     UI -->|POST chat run| API
    API --> ORCH
    ORCH --> MCP
     ORCH -->|checkpoint and hitl request| API
     API -->|SSE event stream by thread| UI
     UI -->|POST hitl respond| API
    API --> HITL
    HITL --> ORCH

     API -->|read and write| DB
    ORCH -->|events, messages, checkpoints| DB
     UI -->|GET workflows list| API
     UI -->|GET workflow details by thread| API
```

ASCII fallback (if Mermaid rendering is unavailable):

```text
+---------------------------+
| Support Agent / Operator  |
+-------------+-------------+
              |
              v
+---------------------------+       GET workflows / details
| React Workflow Studio UI  |------------------------------+
+-------------+-------------+                              |
              | POST chat run                             |
              v                                           |
+---------------------------+       read/write            |
| FastAPI Backend           |<-------------------->+----------------------+
+------+--------------------+                     | Postgres Persistence |
       |                                          | runs/events/messages |
       | start workflow                           | checkpoints/approvals|
       v                                          +----------------------+
+---------------------------+
| MAF Sequential Workflow   |
| Triage -> Policy ->       |
| Resolution                |
+------+---------------+----+
       |               |
       | tool calls    | checkpoint + hitl.request
       v               v
+----------------+   +---------------------------+
| MCP/Local      |   | Human Approval Panel      |
| Tools          |   | Approve / Reject          |
+----------------+   +-------------+-------------+
                                 |
                                 | POST hitl respond
                                 v
                      +---------------------------+
                      | HITL Approval Handler     |
                      +-------------+-------------+
                                    |
                                    v
                      +---------------------------+
                      | Resume Workflow Execution |
                      +---------------------------+

Live updates: FastAPI Backend -> SSE event stream by thread -> UI timeline
```

## Runtime mapping (Local API + Foundry hosted entrypoint)

There is one business workflow implementation (`OrderResolutionWorkflow`) and one
service entrypoint (`OrderResolutionService`). FastAPI and Foundry-hosted paths both
invoke this same service/workflow behavior.

```mermaid
flowchart TD
    A[FastAPI /api/chat/run] --> SVC[OrderResolutionService]
    B[Foundry Responses host\nbackend/foundry/main.py] --> SVC
    SVC --> RUN[OrderResolutionMafRunner]
    RUN --> WF[OrderResolutionWorkflow]
    WF --> EX[Triage + Policy + Resolution + HITL executors]
    EX --> TOOLS[fetch_order_status / fetch_policy / submit_resolution]
    WF --> EVT[workflow.stage/tool.call/checkpoint.created/hitl.request/hitl.response/workflow.output]
    EVT --> BUS[EventBus + projector]
    BUS --> DB[(workflow_runs/workflow_events/checkpoints/approvals)]
    BUS --> SSE[SSE timelines to UI]
```

### Shared vs distinct

- **Shared:** business tools, HITL semantics, stable event contracts, persistence projections.
- **Distinct wrappers:** FastAPI route layer vs Foundry Responses protocol wrapper in `backend/foundry/main.py`.
- **Private browser dispatch:** `RUNTIME_TARGET=responses_wrapper` makes the
  internal FastAPI app dispatch idempotently to Foundry Responses and replay
  persisted PostgreSQL events over the stable SSE surface. It does not change
  native event names or HITL policy.

## Core Business Flow

1. User submits an order issue from the UI.
2. Backend starts a sequential workflow: triage, policy retrieval/analysis, resolution decision.
3. If the decision is low risk, workflow completes automatically and emits output.
4. If risk threshold is met, workflow emits `checkpoint.created` + `hitl.request` and pauses.
5. Reviewer approves/rejects in UI.
6. Workflow resumes from checkpoint:

- approve -> completes with final output,
- reject -> emits escalated output/state.

7. UI timeline and history endpoints display full execution trace.

Detailed behavior and trigger conditions are aligned with `docs/design/userflow.md` and `docs/design/hitl-approval-conditions.md`.

## Persistence and Auditability

Durable state is stored in Postgres so runs survive backend restarts:

- `workflow_runs`: query-friendly summary per thread,
- `workflow_events`: append-only execution timeline,
- `conversation_messages`: persisted transcript/context,
- `checkpoints`: HITL pause/resume state,
- `approvals`: reviewer decisions and audit trail.

This enables deterministic replay of what happened, why it happened, and who approved/rejected critical actions.

## Verifiability Model

The architecture is verifiable at three levels:

1. Functional tests:

- backend tests cover low-risk and high-risk/HITL flows.

2. Evaluation harness:

- eval cases validate expected HITL/no-HITL outcomes across baseline scenarios.

3. End-to-end UX checks:

- Playwright tests verify timeline visibility, HITL approval/rejection paths, and terminal states.

Required commands:

- `make test`
- `make eval-backend`
- `make test-e2e`

## Future Hosting Evolution

The same business flow runs across:

1. local MAF runtime (implemented),
2. Foundry-hosted Responses-native runtime (private VNet lane retained).

Architecture keeps API and event contracts stable to simplify this progression while maintaining business traceability.

Process/governance authority for delivery and verification is documented in `docs/design/engineering-operating-model.md`.
