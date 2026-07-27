# MAF Order Resolution Agent

Customer-support workflow demonstrating sequential MAF execution, durable
PostgreSQL state, deterministic human-in-the-loop (HITL) approvals, and a React
SSE timeline.

## Runtime model

FastAPI is the only application host for the MAF workflow, locally and in the
Azure Container Apps target. Foundry is limited to model inference and
report-only evaluation; it is not an application host.

The Azure deployment is active in `rg-maf-ora-azure` in North Central US. East
US is excluded because of an Azure PostgreSQL offer restriction. The frontend
uses the same-origin `/api` proxy; the FastAPI backend remains the sole MAF host.

## Quick start

```bash
make bootstrap
make up
```

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/api/health

Model inference is configured with:

- `FOUNDRY_PROJECTS_ENDPOINT`
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`
- `FOUNDRY_EMBEDDINGS_DEPLOYMENT_NAME`

When model configuration is absent, the existing deterministic triage summary
is used within the same MAF workflow.

## Contracts

- Low-risk cases complete automatically.
- High-risk cases pause for HITL and resume after an approval decision.
- Native SSE event types remain stable: `workflow.stage`, `tool.call`,
  `checkpoint.created`, `hitl.request`, `hitl.response`, and
  `workflow.output`.
- The rich SSE route is additive.

Baseline scenarios: `ORD-1001` should not require HITL; `ORD-1009` should.

## Validation

```bash
make test
make eval-backend
make eval-foundry   # report-only; requires Foundry configuration
make test-e2e
./scripts/skills/design-review-skill.sh
```

## Documentation

- [Architecture](docs/design/architecture.md)
- [User flow and API contracts](docs/design/userflow.md)
- [HITL rules](docs/design/hitl-approval-conditions.md)
- [Engineering operating model](docs/design/engineering-operating-model.md)
- [Azure app-hosted package](infra/azure-apphosted/README.md)
- [Deployment plan](.azure/deployment-plan.md)
