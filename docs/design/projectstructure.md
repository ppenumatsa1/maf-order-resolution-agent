# Project Structure

```text
maf-order-resolution-agent/
  backend/
    app/
      api/v1/
        routers/
        schemas/
      core/
      infrastructure/
        events/
        mcp/
        persistence/
      maf/
        agents/
        executors/
        prompts/
        tools/
        workflows/
        clients.py
        factory.py
        middleware.py
        runner.py
      modules/order_resolution/
      main.py
    tests/
    .foundry/
      datasets/
      evaluators/
      suites/
    eval.yaml
  frontend/
    src/
    package.json
  infra/
    azure-apphosted/
  scripts/
    github/
    parity/
    playwright/
    skills/
  docs/design/
```

## Boundary ownership

- `backend/app/api/v1/*`: HTTP and SSE contracts.
- `backend/app/modules/order_resolution/*`: application service, domain models, ports, projections.
- `backend/app/maf/*`: MAF runtime internals (prompts, agents, executors, workflow, runner).
- `backend/app/infrastructure/*`: persistence and external adapters.
- `infra/azure-apphosted/`: the single Azure deployment package for Container
  Apps, PostgreSQL, observability, and Foundry model/evaluation resources.
