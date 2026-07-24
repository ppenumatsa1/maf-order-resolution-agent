#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDRY_DIR="${ROOT_DIR}/infra/foundry-hosted"

: "${AZD_ENVIRONMENT_NAME:?AZD_ENVIRONMENT_NAME is required}"
: "${TARGET_RESOURCE_GROUP:?TARGET_RESOURCE_GROUP is required}"
: "${TARGET_FOUNDRY_PROJECT:?TARGET_FOUNDRY_PROJECT is required}"
: "${TARGET_POSTGRES_DATABASE:?TARGET_POSTGRES_DATABASE is required}"
: "${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID is required}"

for binary in az azd python3; do
  command -v "$binary" >/dev/null 2>&1 || {
    echo "Missing required binary: $binary"
    exit 1
  }
done

cd "$FOUNDRY_DIR"
azd env select "$AZD_ENVIRONMENT_NAME" --no-prompt

get_env_value() {
  azd env get-value "$1" 2>/dev/null || true
}

require_env_value() {
  local key="$1"
  local value
  value="$(get_env_value "$key")"
  [[ -n "$value" ]] || {
    echo "AZD environment value $key is required."
    exit 1
  }
  printf '%s' "$value"
}

require_exact_value() {
  local key="$1"
  local expected="$2"
  local actual
  actual="$(require_env_value "$key")"
  [[ "$actual" == "$expected" ]] || {
    echo "AZD environment value $key does not match the private deployment target."
    exit 1
  }
}

require_exact_value AZURE_RESOURCE_GROUP "$TARGET_RESOURCE_GROUP"
require_exact_value FOUNDRY_PROJECT_NAME "$TARGET_FOUNDRY_PROJECT"
require_exact_value POSTGRES_DATABASE_NAME "$TARGET_POSTGRES_DATABASE"
require_exact_value NETWORK_MODE private
require_exact_value ENABLE_CONTAINER_APPS true
require_exact_value ENABLE_POSTGRES_PRIVATE_ENDPOINT true

actual_subscription_id="$(az account show --query id --output tsv)"
[[ "$actual_subscription_id" == "$AZURE_SUBSCRIPTION_ID" ]] || {
  echo "Azure CLI is not scoped to the configured private deployment subscription."
  exit 1
}

postgres_server_name="$(require_env_value POSTGRES_SERVER_NAME)"
postgres_fqdn="$(
  az postgres flexible-server show \
    --resource-group "$TARGET_RESOURCE_GROUP" \
    --name "$postgres_server_name" \
    --query fullyQualifiedDomainName \
    --output tsv
)"
expected_postgres_fqdn="${postgres_server_name,,}.postgres.database.azure.com"
[[ "$postgres_fqdn" == "$expected_postgres_fqdn" ]] || {
  echo "The selected PostgreSQL server does not resolve to its canonical FQDN."
  exit 1
}

az postgres flexible-server db show \
  --resource-group "$TARGET_RESOURCE_GROUP" \
  --server-name "$postgres_server_name" \
  --database-name "$TARGET_POSTGRES_DATABASE" \
  --output none

runtime_database_url="$(require_env_value RUNTIME_DATABASE_URL)"
runtime_database_host="$(
  RUNTIME_DATABASE_URL="$runtime_database_url" python3 - <<'PY'
import os
from urllib.parse import urlsplit

print((urlsplit(os.environ["RUNTIME_DATABASE_URL"]).hostname or "").lower())
PY
)"
[[ "$runtime_database_host" == "$expected_postgres_fqdn" ]] || {
  echo "RUNTIME_DATABASE_URL does not target the canonical PostgreSQL server."
  exit 1
}

project_id="$(require_env_value FOUNDRY_PROJECT_ID)"
project_id_lower="${project_id,,}"
expected_resource_group_segment="/resourcegroups/${TARGET_RESOURCE_GROUP,,}/"
expected_project_segment="/projects/${TARGET_FOUNDRY_PROJECT,,}"
[[ "$project_id_lower" == *"$expected_resource_group_segment"* &&
   "$project_id_lower" == *"$expected_project_segment" ]] || {
  echo "FOUNDRY_PROJECT_ID is not scoped to the selected private project."
  exit 1
}

if [[ "$(require_env_value CREATE_POSTGRES_SERVER)" == "true" ]]; then
  [[ -n "$(require_env_value POSTGRES_ADMIN_PASSWORD)" ]] || {
    echo "The private environment requires its existing PostgreSQL administrator secret."
    exit 1
  }
fi

echo "Validated selected private deployment environment without displaying secret values."
