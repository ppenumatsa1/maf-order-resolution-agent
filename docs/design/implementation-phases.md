# Implementation Phases

## Phase 1 (Completed)

- Backend orchestration scaffold complete.
- SSE event model complete.
- HITL + checkpoint + memory complete.
- Evals baseline complete.
- Design docs complete.

## Phase 2

- Azure app-hosted parity with Container Apps, Azure PostgreSQL, Foundry model-client configuration, App Insights telemetry, and HITL trace correlation.
- Keep `WORKFLOW_MODE=maf_sdk`, `STORE_PROVIDER=postgres`, `RAG_PROVIDER=pgvector`, and `MEMORY_PROVIDER=postgres` for parity.
- Keep HITL rules deterministic and preserve frontend/API event contracts.

## Phase 3

- Compatibility shims have been removed now that Azure app-hosted parity is green.
- Add a MAF middleware seam for telemetry/correlation, event enrichment/redaction, streamed model usage observation, session/run context, and explicit failure-event behavior.
- Add an additive AG-UI-compatible rich event stream for future CopilotKit-style React consumption while preserving the legacy SSE stream.
- Foundry-hosted runtime uses `invocations` as the stable backend contract while adding `responses` as the cutover target surface (`FOUNDRY_HOSTED_PROTOCOL=dual` during shadow/canary).
- Create canonical Foundry backend namespaces:
  - `backend/app/foundry/*` for hosted invocation/runtime adapters.
  - `backend/foundry/*` for `agent.yaml`, `eval.yaml`, runtime metadata, and `.foundry` cache.
- Keep Azure AI Search deferred until Foundry-hosted retrieval architecture is proven.

## Later phases

- Move toward a multi-agent monorepo shape when a second agent exists: a top-level README plus self-contained agent folders, each owning code, infra/IaC, CI/CD, SRE/runbooks, and docs.
- Complete Foundry-hosted cutover gates (conversation/history parity, HITL resume parity, memory/state gating, traces, and rollback validation) before switching active protocol to `responses`.
- Implement Azure AI Search only if the post-Foundry retrieval architecture still needs it.
- Harden auth/security, add richer evaluation metrics, and expand CI gating.

## Project Milestone History (Quick Pickup)

| Milestone                               | Project history summary                                                                                                                                                                  |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M0: Product intent defined              | Demo objective finalized: sequential multi-agent order-resolution flow with deterministic HITL safety, checkpoint/resume, memory continuity, SSE timeline, telemetry, and eval coverage. |
| M1: Local workflow foundation complete  | Local runtime path became the default (`WORKFLOW_MODE=maf_sdk`), with durable Postgres-backed run/event/checkpoint/approval history and stable frontend/API event contracts.             |
| M2: Azure app-hosted parity             | Hosting and persistence moved to Azure infrastructure while preserving local behavior and contracts to minimize migration risk.                                                          |
| M3: Architecture hardening              | Compatibility shims removed; middleware and rich-stream seams added without breaking legacy SSE; backend/package boundaries standardized.                                                |
| M4: Foundry-hosted transition (current) | Backend remains the stable API/HITL/SSE gateway while hosted execution moves to Foundry; `invocations` remains stable and `responses` is introduced as additive cutover surface.         |
| M5: Safe cutover policy (in progress)   | Postgres projection remains the source of truth for UI/test contracts during transition; hosted-native state/memory providers stay gated until restart/resume/audit parity is proven.    |

## Current Chapter (What To Assume Today)

- User-facing contracts stay stable: event names, HITL semantics, pagination/read models, and workflow history APIs.
- Foundry migration is additive-first: run dual protocol during cutover, keep rollback path, and switch defaults only after parity gates pass.
- Treat traces as observability only; do not use traces as workflow state or approval source of truth.
