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
        rag/
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
    foundry/main.py
    tests/
    .foundry/
      datasets/
      evaluators/
      suites/
    agent.yaml
    eval.yaml
  frontend/
    src/
    package.json
  infra/
    foundry-hosted/
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
- `backend/foundry/main.py`: Foundry-hosted Responses adapter that invokes the shared service/workflow path.
