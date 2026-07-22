# Implementation Phases

## Phase 1 (Completed)

- Backend orchestration scaffold complete.
- SSE event model complete.
- HITL + checkpoint + memory complete.
- Evals baseline complete.
- Design docs complete.

## Phase 2

- Private Foundry hosted parity with VNet/private endpoint networking, PostgreSQL runtime configuration, App Insights telemetry, and HITL trace correlation.
- Keep `WORKFLOW_MODE=maf_sdk`, `STORE_PROVIDER=postgres`, `RAG_PROVIDER=pgvector`, and `MEMORY_PROVIDER=postgres` for local/hosted parity.
- Keep HITL rules deterministic and preserve frontend/API event contracts.

## Phase 3

- Compatibility shims have been removed now that local and private-hosted parity is green.
- Add a MAF middleware seam for telemetry/correlation, event enrichment/redaction, streamed model usage observation, session/run context, and explicit failure-event behavior.
- Add an additive AG-UI-compatible rich event stream for future CopilotKit-style React consumption while preserving the legacy SSE stream.
- Foundry-hosted runtime is Responses-native as the hosted contract.
- Keep hosted/runtime namespaces limited to the current package layout; do not reintroduce legacy `backend/app/foundry/*` adapter namespaces.
- Keep Azure AI Search deferred until Foundry-hosted retrieval architecture is proven.

## Later phases

- Move toward a multi-agent monorepo shape when a second agent exists: a top-level README plus self-contained agent folders, each owning code, infra/IaC, CI/CD, SRE/runbooks, and docs.
- Keep Foundry-hosted parity gates (conversation/history parity, HITL resume parity, traces, and rollback validation) aligned with the single Responses-native workflow path.
- Implement Azure AI Search only if the post-Foundry retrieval architecture still needs it.
- Harden auth/security, add richer evaluation metrics, and expand CI gating.

## Project Milestone History (Quick Pickup)

| Milestone                               | Project history summary                                                                                                                                                                  |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M0: Product intent defined              | Demo objective finalized: sequential multi-agent order-resolution flow with deterministic HITL safety, checkpoint/resume, memory continuity, SSE timeline, telemetry, and eval coverage. |
| M1: Local workflow foundation complete  | Local runtime path became the default (`WORKFLOW_MODE=maf_sdk`), with durable Postgres-backed run/event/checkpoint/approval history and stable frontend/API event contracts.             |
| M2: Private Foundry-hosted parity      | Hosting and persistence moved to the private Foundry lane while preserving local behavior and contracts to minimize migration risk.                                                     |
| M3: Architecture hardening              | Compatibility shims removed; middleware and rich-stream seams added without breaking legacy SSE; backend/package boundaries standardized.                                                |
| M4: Foundry-hosted runtime              | Responses-native hosted entrypoint is the current hosted path; stable workflow/event contracts remain unchanged.                                                                            |
| M5: Safe operational policy             | Postgres projection remains the source of truth for UI/test contracts; deterministic HITL and replay rules stay enforced.                                                                   |

## Current Chapter (What To Assume Today)

- User-facing contracts stay stable: event names, HITL semantics, pagination/read models, and workflow history APIs.
- Foundry hosting is Responses-native; keep rollback discipline and parity gates for behavior, HITL, and telemetry.
- Treat traces as observability only; do not use traces as workflow state or approval source of truth.

Delivery ownership and gate authority are documented in `docs/design/engineering-operating-model.md`.
