# MAF Order Resolution Agent

## Goal

Build a verifiable order-resolution workflow that:
- automates low-risk customer support actions,
- pauses for human approval on risky decisions,
- preserves full timeline/audit history for operators.

## Use case

Customer support scenarios like delayed delivery, damaged item, and policy-based compensation:
1. Triage customer issue.
2. Retrieve policy evidence.
3. Decide action (auto-complete or HITL checkpoint).
4. Stream workflow events to UI and persist run history.

## Verifiability

Run the required validation chain:

```bash
make test
make eval-backend
make test-e2e
```

For cross-endpoint parity (local + Azure + Foundry), use:

```bash
make parity-all
```

Core baseline checks:
- `ORD-1001` (low amount) -> typically no HITL.
- `ORD-1009` (high amount) -> HITL expected.

## Journey status

| Stage | Status | Runtime path |
|---|---|---|
| Local MAF | Implemented | `WORKFLOW_MODE=maf_sdk` |
| Azure app-hosted | Implemented | Same runtime behavior hosted on ACA/Postgres/App Insights |
| Foundry hosted agent | In progress | Hosted `invocations` path is deployed/testable; full parity iteration continues |

## No-restart Foundry testing ideas

| Idea | Restart needed | Notes |
|---|---|---|
| Backend env var only (`FOUNDRY_HOSTED_INVOCATIONS_URL`) | Yes | Stable for fixed endpoint, but slower for iterative tests. |
| Runtime URL override in diagnostic API request (implemented) | No | Best local iteration path for hosted endpoint testing without UI restarts. |
| Per-endpoint presets file (`dev-foundry-endpoints.json`) | No | Good next step if you frequently rotate among many agents/projects. |

## Run locally

### 1) Start services

```bash
make bootstrap
make run-backend
make run-frontend
```

Frontend: `http://localhost:5173`
Backend: `http://localhost:8000`

### 2) Environment variables

Use `backend/.env` (copy from `backend/.env.example`) and set:

#### Workflow Studio (single UI)

```bash
WORKFLOW_MODE=maf_sdk
STORE_PROVIDER=postgres
RAG_PROVIDER=pgvector
MEMORY_PROVIDER=postgres
```

#### Foundry-hosted endpoint wiring

```bash
# required when WORKFLOW_MODE=foundry_hosted
FOUNDRY_HOSTED_INVOCATIONS_URL=<foundry_invocations_endpoint>

# optional if endpoint requires auth
FOUNDRY_HOSTED_API_KEY=<token>
FOUNDRY_HOSTED_TIMEOUT_SECONDS=30
```

Auth behavior:
- If **API key/token field is left blank**, backend auto-acquires an Entra bearer token for `services.ai.azure.com` endpoints (requires `az login`).
- If auto token fails, set `FOUNDRY_HOSTED_API_KEY` in backend environment configuration.

### 3) Use Workflow Studio

- **Workflow Studio** uses the configured backend API base and no longer exposes
  backend URL presets or request-time Foundry credential overrides in the UI.
- Runtime status uses backend health metadata
  (`environment • workflow_mode • provider/mode`) so it is obvious which runtime
  the configured backend is serving.
- For non-UI hosted endpoint diagnostics, use backend `POST /api/foundry/invoke`;
  Foundry endpoint and authentication are read from backend environment
  configuration only.

## Deploy and test in Azure/Foundry

| Step | Command |
|---|---|
| Deploy app services | `azd deploy` |
| Deploy hosted agent | `azd deploy order-resolution-hosted --no-prompt` |
| Check hosted agent | `azd ai agent show order-resolution-hosted --output json` |
| Invoke hosted agent | `azd ai agent invoke order-resolution-hosted '{"message":"health check"}' --no-prompt` |

## Key docs

- Backend details: `backend/README.md`
- HITL rules: `docs/design/hitl-approval-conditions.md`
- Local -> Azure -> Foundry decisions: `docs/design/local-azure-foundry-decisions.md`
