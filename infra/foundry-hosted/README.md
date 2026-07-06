# Foundry-Hosted Scaffold

This scaffold prepares a dedicated deployment/runtime path for Foundry-hosted workflow execution through structured `invocations`, with an optional additive Responses protocol surface.

## Layout

- `iac/main.bicep`: starter shared resources and extension points for Foundry hosting.
- `iac/modules/*`: private networking modules (VNet, private DNS, private endpoints).
- `iac/parameters.dev.json`: sample dev parameters.
- `runtime/.env.example`: provider/env wiring for Foundry mode and hosted invocations endpoint.
- `runtime/entrypoint.sh`: backend startup entrypoint for this path.
- `runtime/smoke-test.sh`: expected-not-yet-implemented validation.

## Private networking mode (phase 1 scaffold)

The IaC now supports an optional private networking mode for Foundry-hosted
deployments. This mode is disabled by default to preserve the current behavior.

Set `enablePrivateNetworking=true` in `iac/parameters.dev.json` to create:

- A VNet with two subnets:
  - `agent-subnet` delegated to `Microsoft.App/environments`
  - `pe-subnet` for private endpoints
- Private DNS zones and VNet links for:
  - `privatelink.blob.core.windows.net`
  - `privatelink.azconfig.io`
  - `privatelink.services.ai.azure.com`
  - `privatelink.cognitiveservices.azure.com`
  - `privatelink.openai.azure.com`
- Private endpoints for:
  - storage account (blob)
  - app configuration
  - existing Foundry account (when `existingFoundryAccountResourceId` is set)

Notes:

- Foundry account private endpoint creation is opt-in through
  `existingFoundryAccountResourceId`.
- This phase is network-foundation only; tools-behind-vnet and full ingress
  hardening are deferred.

## How to test (end-to-end)

### 1) Infrastructure template compile checks

Run Bicep build for all touched templates:

```bash
az bicep build --file infra/foundry-hosted/iac/main.bicep
az bicep build --file infra/foundry-hosted/iac/modules/vnet.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-dns.bicep
az bicep build --file infra/foundry-hosted/iac/modules/private-endpoint.bicep
```

Expected result:

- All templates compile.
- Current non-blocking warnings may still appear:
  - `no-hardcoded-env-urls` for private DNS zone constants.
  - `BCP081` for App Configuration preview resource typing.

### 2) Azure what-if checks (baseline vs private mode)

Create a test resource group once:

```bash
az group create --name rg-maf-foundry-vnet-test --location eastus
```

Run default mode (`enablePrivateNetworking=false`):

```bash
az deployment group what-if \
  --resource-group rg-maf-foundry-vnet-test \
  --template-file infra/foundry-hosted/iac/main.bicep \
  --parameters @infra/foundry-hosted/iac/parameters.dev.json \
  --no-pretty-print -o json > /tmp/foundry-public-whatif.json

jq -r '.status, (.changes|length), ([.changes[] | select(.changeType=="Create")] | length)' /tmp/foundry-public-whatif.json
```

Run private mode (`enablePrivateNetworking=true`):

```bash
az deployment group what-if \
  --resource-group rg-maf-foundry-vnet-test \
  --template-file infra/foundry-hosted/iac/main.bicep \
  --parameters @infra/foundry-hosted/iac/parameters.dev.json enablePrivateNetworking=true \
  --no-pretty-print -o json > /tmp/foundry-private-whatif.json

jq -r '.status, (.changes|length), ([.changes[] | select(.changeType=="Create")] | length)' /tmp/foundry-private-whatif.json
```

Interpretation:

- Default mode should only plan shared resources (storage + app config).
- Private mode should additionally plan VNet, subnet-linked private DNS zones,
  VNet links, and private endpoints for storage/app config.
- Foundry account private endpoint is only created when
  `existingFoundryAccountResourceId` is supplied.

### 3) Repository regression gates

Run required local checks from repository root:

```bash
make test
make eval-backend
make test-e2e
./scripts/skills/design-review-skill.sh
```

Expected result:

- All checks pass.
- Known warning set can include FastAPI lifecycle deprecation and experimental
  upstream library warnings.

## Validation record (2026-07-06)

Executed on branch: `feature/foundry-private-network-vnet`

Infrastructure checks:

- Bicep build: PASS for `main.bicep` and all new modules.
- What-if (default mode): `status=Succeeded`, `changes=2`, `creates=2`.
- What-if (private mode): `status=Succeeded`, `changes=17`, `creates=17`.

Repository quality gates:

- `make test`: PASS (`85 passed`).
- `make eval-backend`: PASS (`10/10`, `100%`).
- `make test-e2e`: PASS (`7/7`).
- `./scripts/skills/design-review-skill.sh`: PASS.

Artifacts produced during validation:

- `/tmp/foundry-public-whatif.json`
- `/tmp/foundry-private-whatif.json`

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
