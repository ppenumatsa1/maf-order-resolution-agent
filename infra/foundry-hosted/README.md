# Foundry-Hosted Scaffold

This scaffold prepares a dedicated deployment/runtime path for upcoming Foundry-hosted workflow execution.

## Layout

- `iac/main.bicep`: starter shared resources and extension points for Foundry hosting.
- `iac/parameters.dev.json`: sample dev parameters.
- `runtime/.env.example`: provider/env wiring for Foundry mode.
- `runtime/entrypoint.sh`: backend startup entrypoint for this path.
- `runtime/smoke-test.sh`: expected-not-yet-implemented validation.

## Runtime wiring

The sample is aligned with current config literals:

- `WORKFLOW_MODE=foundry_hosted`
- `STORE_PROVIDER=app_db`
- `RAG_PROVIDER=foundry_iq`
- `MEMORY_PROVIDER=foundry_memory`

## Current smoke-test expectation

`runtime/smoke-test.sh` validates current phase behavior:

1. `/health` returns `200`.
2. Workflow execution responds with a `500` containing the known `not implemented` detail for `foundry_hosted`.
