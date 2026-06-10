# Azure App-Hosted Scaffold

This scaffold provides starter infrastructure and runtime wiring for hosting the current backend in Azure while keeping workflow behavior parity.

## Layout

- `iac/main.bicep`: starter Azure infrastructure template.
- `iac/parameters.dev.json`: sample parameters for dev deployments.
- `runtime/.env.example`: provider/env wiring for app-hosted mode.
- `runtime/entrypoint.sh`: backend runtime entrypoint for this path.
- `runtime/smoke-test.sh`: post-start smoke checks.

## Runtime wiring

The default sample keeps deterministic/MAF SDK execution and only changes providers to Azure-ready placeholders:

- `WORKFLOW_MODE=maf_sdk`
- `STORE_PROVIDER=azure_postgres`
- `RAG_PROVIDER=azure_ai_search`
- `MEMORY_PROVIDER=postgres`

## Smoke-test expectation

`runtime/smoke-test.sh` expects:

1. `/health` returns `200`.
2. Low-risk `ORD-1001` request returns `workflow.output` and no `hitl.request`.
