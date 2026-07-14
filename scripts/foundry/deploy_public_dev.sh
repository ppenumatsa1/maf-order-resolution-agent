#!/usr/bin/env bash
set -euo pipefail

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin az
require_bin azd
require_bin make

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

FOUNDRY_AZD_ENV_NAME="${FOUNDRY_AZD_ENV_NAME:-foundry-public-dev}"
AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-maf-ora-foundry-public-dev}"
AZURE_LOCATION="${AZURE_LOCATION:-eastus2}"
FOUNDRY_AI_SEARCH_LOCATION="${FOUNDRY_AI_SEARCH_LOCATION:-eastus}"
FOUNDRY_PROJECT_NAME="${FOUNDRY_PROJECT_NAME:-order-resolution-public-dev}"
FOUNDRY_HOSTED_AGENT_NAME="${FOUNDRY_HOSTED_AGENT_NAME:-order-resolution-hosted}"
RUNTIME_DATABASE_URL="${RUNTIME_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -z "$AZURE_SUBSCRIPTION_ID" ]]; then
  echo "AZURE_SUBSCRIPTION_ID is required."
  exit 1
fi
AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(az account show --subscription "$AZURE_SUBSCRIPTION_ID" --query tenantId -o tsv)}"

if [[ -z "$RUNTIME_DATABASE_URL" ]]; then
  echo "RUNTIME_DATABASE_URL or DATABASE_URL is required."
  exit 1
fi

echo "Staging hosted agent project from backend/"
rm -rf infra/foundry-hosted/agent
mkdir -p infra/foundry-hosted/agent
cp -a backend/. infra/foundry-hosted/agent/
rm -rf infra/foundry-hosted/agent/.venv infra/foundry-hosted/agent/tests

echo "Selecting AZD environment: ${FOUNDRY_AZD_ENV_NAME}"
(
  cd infra/foundry-hosted
  azd env select "$FOUNDRY_AZD_ENV_NAME" || azd env new "$FOUNDRY_AZD_ENV_NAME"
  azd env set AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
  azd env set AZURE_RESOURCE_GROUP "$AZURE_RESOURCE_GROUP"
  azd env set AZURE_LOCATION "$AZURE_LOCATION"
  azd env set AZURE_TENANT_ID "$AZURE_TENANT_ID"
  azd env set AI_SEARCH_LOCATION "$FOUNDRY_AI_SEARCH_LOCATION"
  azd env set FOUNDRY_PROJECT_NAME "$FOUNDRY_PROJECT_NAME"
  azd env set HOSTED_AGENT_NAME "$FOUNDRY_HOSTED_AGENT_NAME"
  azd env set DATABASE_URL "$RUNTIME_DATABASE_URL"
  azd env set RUNTIME_DATABASE_URL "$RUNTIME_DATABASE_URL"
  azd env set APP_ENV "${APP_ENV:-foundry-public-dev}"
  azd env set STORE_PROVIDER "${STORE_PROVIDER:-postgres}"
  azd env set MEMORY_PROVIDER "${MEMORY_PROVIDER:-postgres}"
  azd env set RAG_PROVIDER "${RAG_PROVIDER:-pgvector}"
  azd env set ENABLE_TELEMETRY "${ENABLE_TELEMETRY:-true}"
  azd env set ENABLE_INSTRUMENTATION "${ENABLE_INSTRUMENTATION:-true}"
  azd env set OTEL_SERVICE_NAME "${OTEL_SERVICE_NAME:-maf-order-resolution-foundry-dev}"
  azd env set OTEL_RECORD_CONTENT "${OTEL_RECORD_CONTENT:-false}"
  azd env set AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING "${AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING:-true}"
  azd env set AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED "${AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED:-false}"
  azd env set FOUNDRY_PROJECTS_ENDPOINT "${FOUNDRY_PROJECTS_ENDPOINT:-}"
  azd env set FOUNDRY_MODEL_DEPLOYMENT_NAME "${FOUNDRY_MODEL_DEPLOYMENT_NAME:-}"
  azd env set NETWORK_MODE "public"
  azd env set CREATE_PRIVATE_DNS_VNET_LINKS "false"
  azd env set CREATE_PRIVATE_ENDPOINTS "false"
  azd env set CREATE_NAT_GATEWAY "false"
  azd env set CREATE_PRIVATE_RUNNER_ACCESS "false"
  azd env set CREATE_BASTION_HOST "false"
  azd env set CREATE_RUNNER_VM "false"
  azd env set ENABLE_STANDARD_AGENT_NETWORK_INJECTION "false"
  # Legacy lowercase keys are retained for compatibility with existing scripts/docs.
  azd env set aiSearchLocation "$FOUNDRY_AI_SEARCH_LOCATION"
  azd env set foundryProjectName "$FOUNDRY_PROJECT_NAME"
  azd env set hostedAgentName "$FOUNDRY_HOSTED_AGENT_NAME"
  azd env set networkMode "public"
  azd env set createPrivateDnsVnetLinks "false"
  azd env set createPrivateEndpoints "false"
  azd env set createNatGateway "false"
  azd env set createPrivateRunnerAccess "false"
  azd env set createBastionHost "false"
  azd env set createRunnerVm "false"
  azd env set enableStandardAgentNetworkInjection "false"
)

echo "Ensuring AZD infrastructure parameters for public mode"
NETWORK_MODE=public \
AI_SEARCH_LOCATION="$FOUNDRY_AI_SEARCH_LOCATION" \
FOUNDRY_PROJECT_NAME="$FOUNDRY_PROJECT_NAME" \
HOSTED_AGENT_NAME="$FOUNDRY_HOSTED_AGENT_NAME" \
./scripts/foundry/ensure_foundry_azd_defaults.sh

echo "Provisioning public Foundry environment"
make foundry-provision

echo "Resolving Foundry project resource ID for deploy target"
account_name="$(az cognitiveservices account list --resource-group "$AZURE_RESOURCE_GROUP" --query "[0].name" -o tsv)"
if [[ -z "$account_name" ]]; then
  echo "Unable to resolve Foundry account name in ${AZURE_RESOURCE_GROUP}"
  exit 1
fi
project_resource_id="/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP}/providers/Microsoft.CognitiveServices/accounts/${account_name}/projects/${FOUNDRY_PROJECT_NAME}"
if ! az resource show --ids "$project_resource_id" --query id -o tsv >/dev/null; then
  echo "Unable to resolve Foundry project resource ID for ${FOUNDRY_PROJECT_NAME} in ${AZURE_RESOURCE_GROUP}"
  exit 1
fi
project_endpoint="https://${account_name}.services.ai.azure.com/api/projects/${FOUNDRY_PROJECT_NAME}"
(
  cd infra/foundry-hosted
  azd env set AZURE_AI_PROJECT_ID "$project_resource_id"
  azd env set FOUNDRY_PROJECT_ID "$project_resource_id"
  azd env set FOUNDRY_PROJECT_ENDPOINT "$project_endpoint"
  azd env set AZURE_AI_PROJECT_ENDPOINT "$project_endpoint"
)

echo "Deploying hosted agent"
make foundry-deploy

echo "Public Foundry deploy completed for AZD environment: ${FOUNDRY_AZD_ENV_NAME}"
