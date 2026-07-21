# MAF Order Resolution Agent

## Goal

Build a verifiable customer-support workflow that:

- auto-resolves low-risk cases,
- pauses for human approval on risky cases,
- preserves timeline and audit history end-to-end.

Primary scenarios include delayed delivery, damaged item, and policy-driven compensation decisions.

## Start Here (Self-Serve Onboarding Path)

If someone starts from this README, this path should let them understand and run the system end-to-end:

1. **Product + business intent**
   - PRD: [docs/design/prd.md](docs/design/prd.md)
   - User flow: [docs/design/userflow.md](docs/design/userflow.md)
2. **Architecture + contracts**
   - Architecture: [docs/design/architecture.md](docs/design/architecture.md)
   - HITL decision rules: [docs/design/hitl-approval-conditions.md](docs/design/hitl-approval-conditions.md)
   - API/event/telemetry schema: [docs/design/schema-io-telemetry.md](docs/design/schema-io-telemetry.md)
3. **Delivery model (how work is governed)**
   - Canonical contract: [docs/design/engineering-operating-model.md](docs/design/engineering-operating-model.md)
   - Repo instructions: [.github/copilot-instructions.md](.github/copilot-instructions.md), [agents.md](agents.md)
4. **Implementation + repo shape**
   - Backend runtime details: [backend/README.md](backend/README.md)
   - Project structure: [docs/design/projectstructure.md](docs/design/projectstructure.md)
   - Tech stack: [docs/design/techstack.md](docs/design/techstack.md)
5. **IaC + deployment lanes**
   - Infra overview: [infra/README.md](infra/README.md)
   - Azure app-hosted lane: [infra/azure-apphosted/README.md](infra/azure-apphosted/README.md)
6. **Validation + operations/SRE**
   - Scripts and validation commands: [scripts/README.md](scripts/README.md)
   - Operational run history and RCA log: [docs/design/issues-changes-fixes.md](docs/design/issues-changes-fixes.md)

## Journey Status

| Stage                | Status      | Runtime path                                                                                                 |
| -------------------- | ----------- | ------------------------------------------------------------------------------------------------------------ |
| Local MAF            | Implemented | Shared MAF workflow (`backend/app/maf/workflows/order_resolution.py`)                                       |
| Azure app-hosted     | Implemented | Same workflow behavior on ACA + Postgres + App Insights                                                      |

MAF internals are split for maintainability into `backend/app/maf/prompts`,
`agents`, `tools`, `executors`, `runner`, and `workflows`.

## Quick Start (Local)

1. Bootstrap dependencies.

```bash
make bootstrap
```

2. Configure backend environment.

- Copy backend env template and edit values in [backend/.env.example](backend/.env.example) and [backend/.env](backend/.env).
- Core local mode:

```bash
STORE_PROVIDER=postgres
MEMORY_PROVIDER=postgres
```

3. Start services.

```bash
make up
```

Or run backend/frontend separately:

```bash
make run-backend
make run-frontend
```

4. Open UI and health endpoints.

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health

## Required Validation Gates

Run these before considering a change complete:

```bash
make test
make eval-backend
make eval-foundry   # report-only Foundry evaluator run for hosted/runtime changes
make test-e2e
./scripts/skills/design-review-skill.sh
```

`make test` and `make eval-backend` now auto-start the local Docker `postgres`
service when `DATABASE_URL` points to localhost and PostgreSQL is not already running.

Cross-target parity gate (requires endpoint matrix env vars):

```bash
make parity-all
```

POC parity is intentionally fast while covering local and Azure app-hosted
targets:

- manual baseline cases: ORD-1001 and ORD-1009
- event contract checks: all contract cases
- UI smoke checks: low-risk complete, high-risk approve, high-risk reject

Baseline behavior checks:

- ORD-1001 should usually complete without HITL.
- ORD-1009 should require HITL.

## Deploy to Azure (App-Hosted Backend + Frontend)

1. Make sure azd environment is selected and configured.
2. Deploy app services:

```bash
azd deploy
```

3. Verify deployed health:

```bash
eval "$(azd env get-values)"
curl -fsS "$API_URL/health"
```

## Environment Model Configuration

For app-hosted model client mode (maf_sdk + foundry_models), model/deployment config is read from backend environment:

- FOUNDRY_PROJECTS_ENDPOINT
- FOUNDRY_MODEL_DEPLOYMENT_NAME
- FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME

Current default examples in checked-in templates use gpt-4.1-mini for chat deployment.

## Troubleshooting

- If Foundry model calls are throttled, reduce evaluation concurrency or select a
  model deployment with capacity.

## Documentation Map

### Product and design

- PRD: [docs/design/prd.md](docs/design/prd.md)
- User flow: [docs/design/userflow.md](docs/design/userflow.md)
- System architecture: [docs/design/architecture.md](docs/design/architecture.md)
- HITL rules and baseline scenarios: [docs/design/hitl-approval-conditions.md](docs/design/hitl-approval-conditions.md)
- API/event/telemetry schema: [docs/design/schema-io-telemetry.md](docs/design/schema-io-telemetry.md)

### Delivery, implementation, and decisions

- Engineering operating model (intent -> skills -> implementation -> evidence): [docs/design/engineering-operating-model.md](docs/design/engineering-operating-model.md)
- Project phases and milestone history: [docs/design/implementation-phases.md](docs/design/implementation-phases.md)
- Repo structure: [docs/design/projectstructure.md](docs/design/projectstructure.md)
- Tech stack: [docs/design/techstack.md](docs/design/techstack.md)
- Backend operational details: [backend/README.md](backend/README.md)

### IaC, deployment, and SRE operations

- Infra overview: [infra/README.md](infra/README.md)
- Azure app-hosted IaC/deployment: [infra/azure-apphosted/README.md](infra/azure-apphosted/README.md)
- Scripts, parity, and E2E usage: [scripts/README.md](scripts/README.md)
- Incident/RCA and execution log: [docs/design/issues-changes-fixes.md](docs/design/issues-changes-fixes.md)
