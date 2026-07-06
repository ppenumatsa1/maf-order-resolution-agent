# Foundry-Hosted Scaffold

This scaffold prepares a dedicated deployment/runtime path for Foundry-hosted workflow execution through structured `invocations`, with an optional additive Responses protocol surface.

## Layout

- `iac/main.bicep`: starter shared resources and extension points for Foundry hosting.
- `iac/parameters.dev.json`: sample dev parameters.
- `runtime/.env.example`: provider/env wiring for Foundry mode and hosted invocations endpoint.
- `runtime/entrypoint.sh`: backend startup entrypoint for this path.
- `runtime/smoke-test.sh`: expected-not-yet-implemented validation.

## Runtime wiring

The backend-facing sample is aligned with current config literals and invocation
settings:

- `WORKFLOW_MODE=foundry_hosted`
- `STORE_PROVIDER=app_db`
- `RAG_PROVIDER=foundry_iq`
- `MEMORY_PROVIDER=foundry_memory`
- `FOUNDRY_HOSTED_INVOCATIONS_URL`
- `FOUNDRY_HOSTED_PROTOCOL=dual` for the cutover hosted package because
  `agent.yaml` declares both `invocations` and `responses`. Use `invocations`
  only for rollback builds that serve the invocation protocol alone.
- `FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=none` by default. Set it to
  `responses` only when comparing portal-visible synthetic Responses records;
  shadow requests are labeled with `metadata.synthetic=true`.

Hosted-agent-internal state and memory are configured separately from those
backend provider literals:

- `FOUNDRY_HOSTED_STATE_PROVIDER=stateless_context` is the safe default.
- `FOUNDRY_HOSTED_STATE_PROVIDER=foundry_native` is intentionally gated until a
  durable Foundry checkpoint/state API with HITL approval audit parity is proven.
- `FOUNDRY_HOSTED_MEMORY_PROVIDER=none` is the default.
- `FOUNDRY_HOSTED_MEMORY_PROVIDER=foundry` enables hosted-agent Memory Store
  evaluation only when the project endpoint and memory store name are supplied.

The hosted package keeps invocations as the backend-visible contract while
`dual` exposes the additive Responses route for native Foundry conversation and
trace validation. The Responses package is installed in the hosted runtime; use
`FOUNDRY_HOSTED_PROTOCOL=invocations` as the rollback setting.

Conversation shadow mode is separate from protocol hosting. With
`FOUNDRY_HOSTED_CONVERSATION_SHADOW_PROVIDER=responses`, Invocations user turns
are copied to the Responses endpoint with `operation=shadow_conversation`,
`source_protocol=invocations`, and `synthetic=true` metadata. These records are
for comparison only and must not be treated as active workflow executions.

## Current smoke-test expectation

`runtime/smoke-test.sh` validates current phase behavior:

1. `/health` returns `200`.
2. Workflow execution returns a non-`200` when the hosted endpoint is unavailable or not deployed yet.
