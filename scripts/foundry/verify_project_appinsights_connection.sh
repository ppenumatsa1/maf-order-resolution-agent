#!/usr/bin/env bash
set -euo pipefail

require_env_value() {
  local key="$1"
  local value
  value="$(azd env get-value "$key")"
  if [[ -z "$value" ]]; then
    echo "Missing required azd environment value: $key" >&2
    exit 1
  fi
  printf '%s\n' "$value"
}

command -v az >/dev/null 2>&1 || {
  echo "Missing required binary: az" >&2
  exit 1
}
command -v azd >/dev/null 2>&1 || {
  echo "Missing required binary: azd" >&2
  exit 1
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDRY_DIR="${FOUNDRY_DIR:-$ROOT_DIR/infra/foundry-hosted}"
if [[ ! -f "$FOUNDRY_DIR/azure.yaml" ]]; then
  echo "Unable to locate Foundry AZD project at $FOUNDRY_DIR" >&2
  exit 1
fi
cd "$FOUNDRY_DIR"

resource_group="$(require_env_value AZURE_RESOURCE_GROUP)"
subscription_id="$(require_env_value AZURE_SUBSCRIPTION_ID)"
account_name="$(require_env_value FOUNDRY_ACCOUNT_NAME)"
project_name="$(require_env_value FOUNDRY_PROJECT_NAME)"
appinsights_resource_id="$(require_env_value APPINSIGHTS_RESOURCE_ID)"

connection_url="https://management.azure.com/subscriptions/${subscription_id}/resourceGroups/${resource_group}/providers/Microsoft.CognitiveServices/accounts/${account_name}/projects/${project_name}/connections/ApplicationInsights?api-version=2025-04-01-preview"
connection_category="$(az rest --method get --url "$connection_url" --query properties.category -o tsv)"
connection_target="$(az rest --method get --url "$connection_url" --query properties.target -o tsv)"
connection_resource_id="$(az rest --method get --url "$connection_url" --query properties.metadata.ResourceId -o tsv)"

if [[ "$connection_category" != "AppInsights" ]] ||
  [[ "$connection_target" != "$appinsights_resource_id" ]] ||
  [[ "$connection_resource_id" != "$appinsights_resource_id" ]]; then
  echo "Foundry project ApplicationInsights connection does not target the configured App Insights resource." >&2
  exit 1
fi

echo "Verified Foundry project ApplicationInsights connection: ${account_name}/${project_name}"
