# MAF Multi-Agent Orchestration Demo

Simple command flow to run the full POC with Docker and Make.

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
```

## Local (Non-Docker) Flow

If `.venv` is missing, no problem. Use:

```bash
make bootstrap
make run-backend
make run-frontend
```

`make bootstrap` creates `backend/.venv` and installs backend/frontend/playwright dependencies.

## Notes

- Workflow state is persisted in Postgres (`postgres-data` Docker volume), including:
  - conversation messages
  - workflow runs and event timeline
  - checkpoints and HITL approvals
- Restarting backend/frontend does not lose workflow history as long as the Postgres volume is kept.
- `make down` stops containers but keeps the Postgres volume; use `docker compose down -v` only when you want to wipe persisted state.
- MAF SDK workflow mode is available via `USE_MAF_SDK=true`.

## Human Approval Trigger Rules (HITL)

For test design, use the exact trigger matrix documented here:

- `docs/design/hitl-approval-conditions.md`

Quick summary:

- Approval is required when refund/risk amount is `>= 100`.
- Approval is required for damaged-item flows.
- Approval is required when a policy string includes `manual_review`.
- Otherwise, the workflow completes without approval.

## Design Docs

- `docs/design/prd.md`
- `docs/design/techstack.md`
- `docs/design/projectstructure.md`
- `docs/design/schema-io-telemetry.md`
- `docs/design/userflow.md`
- `docs/design/implementation-phases.md`
- `docs/design/hitl-approval-conditions.md`
