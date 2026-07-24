#!/usr/bin/env bash
set -euo pipefail

: "${AZD_ENVIRONMENT_NAME:?AZD_ENVIRONMENT_NAME is required}"
: "${TARGET_RESOURCE_GROUP:?TARGET_RESOURCE_GROUP is required}"
: "${TARGET_POSTGRES_DATABASE:?TARGET_POSTGRES_DATABASE is required}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FOUNDRY_DIR="${ROOT_DIR}/infra/foundry-hosted"

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

postgres_server_name="$(get_env_value POSTGRES_SERVER_NAME)"
postgres_admin_username="$(get_env_value POSTGRES_ADMIN_USERNAME)"
runtime_database_url="$(get_env_value RUNTIME_DATABASE_URL)"
foundry_project_id="$(get_env_value FOUNDRY_PROJECT_ID)"

[[ -n "$postgres_server_name" && -n "$postgres_admin_username" && -n "$runtime_database_url" && -n "$foundry_project_id" ]] || {
  echo "Private PostgreSQL repair requires PostgreSQL runtime settings and FOUNDRY_PROJECT_ID."
  exit 1
}

expected_host="${postgres_server_name,,}.postgres.database.azure.com"
foundry_account_name="$(
  FOUNDRY_PROJECT_ID="$foundry_project_id" python3 - <<'PY'
import os

parts = [part for part in os.environ["FOUNDRY_PROJECT_ID"].split("/") if part]
try:
    account_index = next(
        index for index, part in enumerate(parts[:-1]) if part.lower() == "accounts"
    )
except StopIteration:
    raise SystemExit("FOUNDRY_PROJECT_ID does not contain a Foundry account.")

print(parts[account_index + 1])
PY
)"
runtime_password="$(
  RUNTIME_DATABASE_URL="$runtime_database_url" \
  EXPECTED_HOST="$expected_host" \
  EXPECTED_USERNAME="$postgres_admin_username" \
  TARGET_POSTGRES_DATABASE="$TARGET_POSTGRES_DATABASE" \
  python3 - <<'PY'
import os
from urllib.parse import urlsplit

parsed = urlsplit(os.environ["RUNTIME_DATABASE_URL"])
expected_host = os.environ["EXPECTED_HOST"]
expected_username = os.environ["EXPECTED_USERNAME"]
expected_database = os.environ["TARGET_POSTGRES_DATABASE"]

if (
    parsed.scheme not in {"postgresql", "postgresql+psycopg"}
    or (parsed.hostname or "").lower() != expected_host
    or parsed.username != expected_username
    or parsed.path.lstrip("/") != expected_database
    or not parsed.password
):
    raise SystemExit("RUNTIME_DATABASE_URL does not match the canonical private PostgreSQL target.")

print(parsed.password)
PY
)"

az postgres flexible-server update \
  --resource-group "$TARGET_RESOURCE_GROUP" \
  --name "$postgres_server_name" \
  --admin-password "$runtime_password" \
  --only-show-errors \
  --output none

server_state="$(
  az postgres flexible-server show \
    --resource-group "$TARGET_RESOURCE_GROUP" \
    --name "$postgres_server_name" \
    --query state \
    --output tsv
)"
[[ "$server_state" == "Ready" ]] || {
  echo "PostgreSQL password repair completed but the canonical server is not ready."
  exit 1
}

foundry_location="$(
  az cognitiveservices account show \
    --resource-group "$TARGET_RESOURCE_GROUP" \
    --name "$foundry_account_name" \
    --query location \
    --output tsv
)"

az deployment group create \
  --resource-group "$TARGET_RESOURCE_GROUP" \
  --name "runtime-secret-sync-$(date +%s)" \
  --template-file "$FOUNDRY_DIR/iac/modules/foundry-project-runtime-secret-connection.bicep" \
  --parameters \
    accountName="$foundry_account_name" \
    projectName="$TARGET_FOUNDRY_PROJECT" \
    location="$foundry_location" \
    runtimeDatabaseUrl="$runtime_database_url" \
  --only-show-errors \
  --output none

echo "Synchronized the canonical PostgreSQL administrator credential and Foundry runtime connection."
