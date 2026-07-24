#!/usr/bin/env bash
set -euo pipefail

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDRY_DIR="${ROOT_DIR}/infra/foundry-hosted"

require_bin az
require_bin azd
require_bin jq

[[ -f "${FOUNDRY_DIR}/azure.yaml" ]] || {
  echo "Missing private AZD project: ${FOUNDRY_DIR}/azure.yaml"
  exit 1
}
[[ -f "${ROOT_DIR}/backend/Dockerfile" && -f "${ROOT_DIR}/frontend/Dockerfile" ]] || {
  echo "Backend and frontend container definitions are required."
  exit 1
}
[[ -f "${ROOT_DIR}/backend/agent.yaml" && -f "${ROOT_DIR}/backend/foundry/main.py" ]] || {
  echo "Hosted-agent source is incomplete."
  exit 1
}

cd "${FOUNDRY_DIR}"

get_env_value() {
  azd env get-value "$1" 2>/dev/null || true
}

require_env_value() {
  local key="$1"
  local value
  value="$(get_env_value "$key")"
  if [[ -z "$value" ]]; then
    echo "AZD environment value ${key} is required."
    exit 1
  fi
  printf '%s' "$value"
}

network_mode="$(require_env_value NETWORK_MODE)"
postgres_server="$(require_env_value POSTGRES_SERVER_NAME)"
runtime_database_url="$(require_env_value RUNTIME_DATABASE_URL)"
enable_container_apps="$(require_env_value ENABLE_CONTAINER_APPS)"
enable_postgres_private_endpoint="$(require_env_value ENABLE_POSTGRES_PRIVATE_ENDPOINT)"
resource_group="$(require_env_value AZURE_RESOURCE_GROUP)"

if [[ "$network_mode" != "private" ]]; then
  echo "NETWORK_MODE must be private."
  exit 1
fi
if [[ "$enable_container_apps" != "true" || "$enable_postgres_private_endpoint" != "true" ]]; then
  echo "Private release requires ENABLE_CONTAINER_APPS=true and ENABLE_POSTGRES_PRIVATE_ENDPOINT=true."
  exit 1
fi

runtime_host="$(
  python3 - "$runtime_database_url" <<'PY'
import sys
from urllib.parse import urlsplit

print((urlsplit(sys.argv[1]).hostname or "").lower())
PY
)"
expected_host="${postgres_server,,}.postgres.database.azure.com"
if [[ "$runtime_host" != "$expected_host" ]]; then
  echo "RUNTIME_DATABASE_URL must target the canonical PostgreSQL server ${expected_host}."
  exit 1
fi

if ! az account show --only-show-errors --output none; then
  echo "Azure CLI authentication is required for a local private release."
  exit 1
fi
if ! azd ext show azure.ai.agents --output json --no-prompt >/dev/null 2>&1; then
  echo "Required azd extension azure.ai.agents is not installed."
  exit 1
fi

echo "Private release preflight passed for resource group ${resource_group}; secrets were not displayed."
