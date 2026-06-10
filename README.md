# MAF Multi-Agent Orchestration Demo

Simple command flow to run the full POC with Docker and Make.

## Project Goal

Build a verifiable multi-agent order-resolution system that can automate routine support decisions, pause for human approval on risky actions, and preserve full workflow history for operational transparency and auditability.

## Business Use Case

Customer support teams handle issues like delayed delivery, damaged items, and wrong-item scenarios. This project provides:

- deterministic triage -> policy -> resolution workflow execution,
- human-in-the-loop gating for high-risk decisions,
- persisted conversation/checkpoint/timeline history,
- UI visibility for operators to inspect and resume workflows safely.

## Verifiability

System correctness is validated through three layers:

- backend tests for low-risk and HITL workflows,
- eval harness for expected HITL/no-HITL outcomes,
- Playwright E2E tests for end-user workflow behavior.

Validation commands:

```bash
make test
make eval-backend
make test-e2e
```

High-level architecture reference:

- `docs/architecture.md`

## Journey Status (Local MAF -> Azure app-hosted -> Foundry-hosted)

Current implementation status:

| Stage               | Status      | Current reality in code                                                                                                 |
| ------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------- |
| Local MAF (default) | Implemented | `WORKFLOW_MODE=maf_sdk` runs the sequential workflow with SSE events, checkpointing, HITL, and Postgres persistence.    |
| Azure app-hosted    | Scaffolded  | Config accepts `STORE_PROVIDER=azure_postgres|app_db`, but runtime currently enforces `STORE_PROVIDER=postgres`.        |
| Foundry-hosted      | Scaffolded  | Config accepts `WORKFLOW_MODE=foundry_hosted`, but workflow factory raises not implemented.                             |

Provider status:

- RAG:
  - `pgvector`: implemented (local pgvector-compatible retrieval persisted in Postgres).
  - `azure_ai_search`, `foundry_vector`, `foundry_iq`: placeholder providers returning empty evidence.
- Memory:
  - `postgres`: implemented, durable.
  - `foundry_memory`: in-process placeholder, not durable across process restarts.

## Fast Start (Recommended)

### 1) Start all servers

```bash
make up
```

This starts:

- backend on http://localhost:8000
- frontend on http://localhost:5173
- mock MCP server on http://localhost:8011

### 2) View app

Open http://localhost:5173

### 3) Run tests

```bash
make test
make docker-test
```

### 4) Stop all servers

```bash
make down
```

## Most Useful Commands

```bash
make help        # all targets
make up          # build + start all services in background
make ps          # list running containers
make logs        # stream logs
make down        # stop all services
make test        # lint + backend tests (local)
make test-e2e    # playwright tests (local)
make docker-test # playwright tests in docker compose profile
./scripts/skills/design-review-skill.sh # deterministic review + test gate
```

## Local (Non-Docker) Flow

If `.venv` is missing, no problem. Use:

```bash
make bootstrap
make run-backend
make run-frontend
```

`make bootstrap` creates `backend/.venv` and installs backend/frontend/playwright dependencies.

## Azure/Foundry Scaffolding

Deployment scaffolding for future hosted paths is available under:

- `infra/azure-apphosted/`
- `infra/foundry-hosted/`

Each path includes starter IaC, runtime `.env` samples, an entrypoint script, and a smoke-test script.
These are additive and do not change local `make up` / `make test` workflows.

## Backend Package Boundaries

The backend now follows the clean agent-style package layout while preserving compatibility shims:

- `backend/app/api/v1/routers/*`: stable FastAPI route contracts.
- `backend/app/api/v1/schemas/*`: API request/response contracts.
- `backend/app/modules/order_resolution/*`: API-facing service, HITL policy logic, workflow context/event models, ports, and read-model projection.
- `backend/app/core/*`: config, database, telemetry, and composition root.
- `backend/app/infrastructure/*`: repository-pattern/adapters namespace for persistence, events, RAG, MCP, and external integrations.
- `backend/app/maf/*`: MAF workflow runtime namespace, tools, clients, agents, and prompts scaffolding.
- Legacy `backend/app/api/*`, `backend/app/models.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/workflows/*`, and `backend/tools/*` paths remain compatibility shims.

## Notes

- Workflow state is persisted in Postgres (`postgres-data` Docker volume), including:
  - conversation messages
  - workflow runs and event timeline
  - checkpoints and HITL approvals
- Restarting backend/frontend does not lose workflow history as long as the Postgres volume is kept.
- `make down` stops containers but keeps the Postgres volume; use `docker compose down -v` only when you want to wipe persisted state.
- Workflow and provider mode are configured via:
  - `WORKFLOW_MODE=maf_sdk`
  - `STORE_PROVIDER=postgres|azure_postgres|app_db`
  - `RAG_PROVIDER=pgvector|azure_ai_search|foundry_vector|foundry_iq`
  - `MEMORY_PROVIDER=postgres|foundry_memory`
- Read-only model/MCP paths are retried with bounded attempts (`READ_RETRY_ATTEMPTS`, `READ_RETRY_DELAY_SECONDS`).
- Business write actions are guarded by deterministic idempotency keys (`workflow_run_id:step_name:business_id`).
- Local pgvector-compatible policy retrieval is enabled by default. `tool.call` payloads now include `policy_evidence_ids` for retrieved policy chunks.
- Store provider switching is scaffolded but not runtime-enabled yet; current supported runtime value remains `STORE_PROVIDER=postgres`.
- RAG provider options:
  - `pgvector` (default, fully wired local pgvector-compatible retrieval)
  - `azure_ai_search` (safe placeholder stub)
  - `foundry_vector` (safe placeholder stub)
  - `foundry_iq` (safe placeholder stub)
- Memory provider switching is available through `MEMORY_PROVIDER`:
  - `postgres` (default, persisted in Postgres)
  - `foundry_memory` (placeholder in-process stub for Foundry integration)
- API supports workflow/session history pagination:
  - `/api/workflows` accepts `page`, `page_size`, and `pageSize` (legacy alias).
  - `/api/workflows/{thread_id}/events` and `/api/sessions/{session_id}/messages` use cursor pagination (`limit`, `cursor`).

## Human Approval Trigger Rules (HITL)

For test design, use the exact trigger matrix documented here:

- `docs/design/hitl-approval-conditions.md`

Quick summary:

- Approval is required when refund/risk amount is `>= 100`.
- Approval is required for damaged-item flows.
- Approval is required when a policy string includes `manual_review`.
- Otherwise, the workflow completes without approval.

## Design Docs

- `docs/architecture.md`
- `docs/design/prd.md`
- `docs/design/techstack.md`
- `docs/design/projectstructure.md`
- `docs/design/schema-io-telemetry.md`
- `docs/design/userflow.md`
- `docs/design/implementation-phases.md`
- `docs/design/hitl-approval-conditions.md`
