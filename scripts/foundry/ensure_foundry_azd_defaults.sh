#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}/infra/foundry-hosted"

get_env_value() {
  local key="$1"
  local value
  if ! value="$(azd env get-value "$key" 2>/dev/null)"; then
    return 0
  fi
  printf '%s\n' "$value"
}

set_if_missing() {
  local key="$1"
  local value="$2"
  local existing
  existing="$(get_env_value "$key")"
  if [[ -z "$existing" ]]; then
    azd env set "$key" "$value" >/dev/null
    echo "defaulted $key=$value"
  fi
}

set_if_missing FOUNDRY_ACCOUNT_NAME "${FOUNDRY_ACCOUNT_NAME:-maffndaibfscpfhjr7sp4}"
set_if_missing CONTAINER_REGISTRY_NAME "${CONTAINER_REGISTRY_NAME:-maffndacrbfscpfhjr7sp4}"
set_if_missing FOUNDRY_TRACE_READER_PRINCIPAL_ID "${FOUNDRY_TRACE_READER_PRINCIPAL_ID:-$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)}"
set_if_missing FOUNDRY_PROJECT_NAME "${FOUNDRY_PROJECT_NAME:-order-resolution-public-managed-dev2}"
set_if_missing HOSTED_AGENT_NAME "${HOSTED_AGENT_NAME:-order-resolution-hosted}"
set_if_missing FOUNDRY_TRACE_EVALUATION_RECORD_CONTENT "${FOUNDRY_TRACE_EVALUATION_RECORD_CONTENT:-true}"
set_if_missing RUNTIME_DATABASE_URL "${RUNTIME_DATABASE_URL:-}"
azd env set AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING false >/dev/null
set_if_missing POSTGRES_SERVER_NAME "${POSTGRES_SERVER_NAME:-maffndpgbfscpfhjr7sp4cu}"
set_if_missing POSTGRES_ADMIN_USERNAME "${POSTGRES_ADMIN_USERNAME:-pgadmin}"
set_if_missing POSTGRES_ADMIN_PASSWORD "${POSTGRES_ADMIN_PASSWORD:-}"
set_if_missing POSTGRES_DATABASE_NAME "${POSTGRES_DATABASE_NAME:-maf_workflow}"
set_if_missing POSTGRES_LOCATION "${POSTGRES_LOCATION:-centralus}"

postgres_server_name="$(get_env_value POSTGRES_SERVER_NAME)"
if az postgres flexible-server show \
  --resource-group "$(get_env_value AZURE_RESOURCE_GROUP)" \
  --name "$postgres_server_name" >/dev/null 2>&1; then
  azd env set CREATE_POSTGRES_SERVER false >/dev/null
  echo "preserved existing PostgreSQL server: $postgres_server_name"
else
  set_if_missing CREATE_POSTGRES_SERVER "${CREATE_POSTGRES_SERVER:-true}"
fi

foundry_project_name="$(get_env_value FOUNDRY_PROJECT_NAME)"
agent_endpoint="$(get_env_value AGENT_ORDER_RESOLUTION_HOSTED_ENDPOINT)"
if [[ -n "$agent_endpoint" && "$agent_endpoint" != *"/projects/${foundry_project_name}/"* ]]; then
  azd env set AGENT_ORDER_RESOLUTION_HOSTED_ENDPOINT "" >/dev/null
  azd env set AGENT_ORDER_RESOLUTION_HOSTED_RESPONSES_ENDPOINT "" >/dev/null
  azd env set AGENT_ORDER_RESOLUTION_HOSTED_VERSION "" >/dev/null
  echo "cleared stale hosted-agent deployment metadata"
fi

set_if_missing foundryProjectName "$(get_env_value FOUNDRY_PROJECT_NAME)"
set_if_missing hostedAgentName "$(get_env_value HOSTED_AGENT_NAME)"

# Keep legacy telemetry env aliases populated because agent.yaml references both names.
appinsights_connection_string="$(get_env_value APPLICATIONINSIGHTS_CONNECTION_STRING)"
if [[ -n "$appinsights_connection_string" ]]; then
  set_if_missing APPINSIGHTS_CONNECTION_STRING "$appinsights_connection_string"
fi
set_if_missing OTEL_SERVICE_NAMESPACE "${OTEL_SERVICE_NAMESPACE:-maf-order-resolution}"
# agent.yaml references this key; default to empty to avoid unresolved variable placeholders.
set_if_missing OTEL_EXPORTER_OTLP_TRACES_ENDPOINT "${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:-}"
