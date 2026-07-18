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
   - Foundry-hosted lane (private-first): [infra/foundry-hosted/README.md](infra/foundry-hosted/README.md)
   - Azure app-hosted lane: [infra/azure-apphosted/README.md](infra/azure-apphosted/README.md)
6. **Validation + operations/SRE**
   - Scripts and validation commands: [scripts/README.md](scripts/README.md)
   - Operational run history and RCA log: [docs/design/issues-changes-fixes.md](docs/design/issues-changes-fixes.md)

## Journey Status

| Stage                | Status      | Runtime path                                                                                                 |
| -------------------- | ----------- | ------------------------------------------------------------------------------------------------------------ |
| Local MAF            | Implemented | Shared MAF workflow (`backend/app/maf/workflows/order_resolution.py`)                                       |
| Azure app-hosted     | Implemented | Same workflow behavior on ACA + Postgres + App Insights                                                      |
| Foundry hosted agent | Implemented (public/private) | Shared workflow hosted at `backend/foundry/main.py` with Responses protocol conversation turns              |

MAF internals are split for maintainability into `backend/app/maf/prompts`,
`agents`, `tools`, `executors`, `runner`, and `workflows`.

## Latest Foundry trace status (2026-07-18)

- **Private Foundry is validated end-to-end**: deploy + smoke (`ORD-1001`, `ORD-1009`) + hosted E2E + App Insights trace/dependency evidence.
- **Public Foundry remains implemented and available** for parity and comparison scenarios.
- Recent private telemetry confirmation and run evidence are tracked in:
  - [docs/design/issues-changes-fixes.md](docs/design/issues-changes-fixes.md)

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
RAG_PROVIDER=pgvector
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

POC parity is intentionally fast while still covering all three targets (local + Azure + Foundry):

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

## Deploy to Foundry (Hosted Agent)

Deploy hosted agent package:

```bash
azd deploy order-resolution-hosted --no-prompt
```

Verify and invoke:

```bash
azd ai agent show order-resolution-hosted --output json
azd ai agent invoke order-resolution-hosted "Resolve delayed order ORD-1001" --protocol responses --conversation-id c1 --no-prompt
azd ai agent invoke order-resolution-hosted "Why was that resolution selected?" --protocol responses --conversation-id c1 --no-prompt
```

For high-risk requests, continue the same conversation with `Approve` or `Reject`.

## Environment Model Configuration

For app-hosted model client mode (maf_sdk + foundry_models), model/deployment config is read from backend environment:

- FOUNDRY_PROJECTS_ENDPOINT
- FOUNDRY_MODEL_DEPLOYMENT_NAME
- FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME

Current default examples in checked-in templates use gpt-4.1-mini for chat deployment.

## Foundry-Hosted Wiring

The hosted agent package is rooted at `backend/` and uses:

- `backend/agent.yaml` (`protocol: responses`, `version: 2.0.0`)
- `backend/foundry/main.py` (thin Responses host around the shared workflow)
- `backend/.foundry/agent-metadata.yaml` and `backend/eval.yaml` for hosted eval metadata
- `infra/foundry-hosted/azure.yaml` service project path (`./agent`) generated from `backend/` via `scripts/foundry/sync_hosted_source.sh`

## Troubleshooting

- If parity fails with 429 session_quota_exceeded from Foundry, reduce test concurrency, add case delays, or clear/raise session quota.
- If hosted responses fail, verify `backend/agent.yaml` protocol and pass `--protocol responses` on `azd ai agent invoke`.

## Documentation Map

### Product and design

- PRD: [docs/design/prd.md](docs/design/prd.md)
- User flow: [docs/design/userflow.md](docs/design/userflow.md)
- System architecture: [docs/design/architecture.md](docs/design/architecture.md)
- HITL rules and baseline scenarios: [docs/design/hitl-approval-conditions.md](docs/design/hitl-approval-conditions.md)
- API/event/telemetry schema: [docs/design/schema-io-telemetry.md](docs/design/schema-io-telemetry.md)

### Delivery, implementation, and decisions

- Engineering operating model (intent -> skills -> implementation -> evidence): [docs/design/engineering-operating-model.md](docs/design/engineering-operating-model.md)
- Runtime decisions (Local -> Azure -> Foundry): [docs/design/local-azure-foundry-decisions.md](docs/design/local-azure-foundry-decisions.md)
- Project phases and milestone history: [docs/design/implementation-phases.md](docs/design/implementation-phases.md)
- Repo structure: [docs/design/projectstructure.md](docs/design/projectstructure.md)
- Tech stack: [docs/design/techstack.md](docs/design/techstack.md)
- Backend operational details: [backend/README.md](backend/README.md)

### IaC, deployment, and SRE operations

- Infra overview: [infra/README.md](infra/README.md)
- Foundry-hosted IaC/deployment: [infra/foundry-hosted/README.md](infra/foundry-hosted/README.md)
- Azure app-hosted IaC/deployment: [infra/azure-apphosted/README.md](infra/azure-apphosted/README.md)
- Scripts, parity, and E2E usage: [scripts/README.md](scripts/README.md)
- Incident/RCA and execution log: [docs/design/issues-changes-fixes.md](docs/design/issues-changes-fixes.md)
