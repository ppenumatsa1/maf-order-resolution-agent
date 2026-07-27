# Project Structure

```text
backend/
  app/
    api/v1/          HTTP and SSE contracts
    core/            configuration, database, telemetry, composition
    infrastructure/  persistence and external adapters
    maf/             prompts, agents, tools, executors, runner, workflows
    modules/order_resolution/
frontend/            React UI
infra/azure-apphosted/
                    Container Apps deployment package
scripts/             validation, parity, and Azure helper scripts
docs/design/         architecture and contract documentation
```

The backend FastAPI application owns the only MAF runtime. The Azure package
adds infrastructure and model/evaluation resources; it does not add another
workflow host.
