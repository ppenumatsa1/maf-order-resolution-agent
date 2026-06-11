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
- Decide Foundry-hosted runtime and retrieval architecture before implementing Azure AI Search. `azure_ai_search` remains a placeholder until that decision is made.

## Later phases

- Move toward a multi-agent monorepo shape when a second agent exists: a top-level README plus self-contained agent folders, each owning code, infra/IaC, CI/CD, SRE/runbooks, and docs.
- Implement Foundry-hosted runtime if selected.
- Implement Azure AI Search only if the post-Foundry retrieval architecture still needs it.
- Harden auth/security, add richer evaluation metrics, and expand CI gating.
