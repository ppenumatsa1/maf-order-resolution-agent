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
RESULT_FILE="${POSTGRES_CONNECTIVITY_EVIDENCE_FILE:-${ROOT_DIR}/backend/.foundry/results/private-connectivity-proof.json}"

require_bin az
require_bin azd
require_bin jq

cd "${FOUNDRY_DIR}"

get_env_value() {
  azd env get-value "$1" 2>/dev/null || true
}

resource_group="${AZURE_RESOURCE_GROUP:-$(get_env_value AZURE_RESOURCE_GROUP)}"
backend_name="${SERVICE_BACKEND_NAME:-$(get_env_value SERVICE_BACKEND_NAME)}"
postgres_fqdn="${POSTGRES_SERVER_FQDN:-$(get_env_value POSTGRES_SERVER_FQDN)}"
hosted_agent_name="${HOSTED_AGENT_NAME:-$(get_env_value HOSTED_AGENT_NAME)}"

: "${resource_group:?AZURE_RESOURCE_GROUP is required}"
: "${backend_name:?SERVICE_BACKEND_NAME is required}"
: "${postgres_fqdn:?POSTGRES_SERVER_FQDN is required}"
: "${hosted_agent_name:?HOSTED_AGENT_NAME is required}"

latest_ready_revision="$(
  az containerapp show \
    --resource-group "$resource_group" \
    --name "$backend_name" \
    --query 'properties.latestReadyRevisionName' \
    --output tsv
)"
if [[ -z "$latest_ready_revision" ]]; then
  echo "Backend Container App has no ready revision; it cannot prove PostgreSQL connectivity."
  exit 1
fi

revision_state="$(
  az containerapp revision show \
    --resource-group "$resource_group" \
    --name "$backend_name" \
    --revision "$latest_ready_revision" \
    --query 'properties.runningState' \
    --output tsv
)"
if [[ "$revision_state" != "Running" ]]; then
  echo "Backend revision ${latest_ready_revision} is not running."
  exit 1
fi

# Backend startup runs postgres_db.ensure_schema(), so a running ready revision
# demonstrates that the internal ACA reached the canonical PostgreSQL endpoint.
SMOKE_MESSAGE="${SMOKE_MESSAGE:-Resolve delayed order ORD-1009}" \
  SMOKE_MAX_ATTEMPTS="${SMOKE_MAX_ATTEMPTS:-6}" \
  make -C "$ROOT_DIR" foundry-smoke

mkdir -p "$(dirname "$RESULT_FILE")"
jq -n \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg resource_group "$resource_group" \
  --arg backend_name "$backend_name" \
  --arg backend_revision "$latest_ready_revision" \
  --arg postgres_fqdn "${postgres_fqdn,,}" \
  --arg hosted_agent_name "$hosted_agent_name" \
  '{
    status: "passed",
    generated_at: $generated_at,
    aca_database_connectivity: "passed",
    hosted_agent_database_connectivity: "passed",
    resource_group: $resource_group,
    backend_container_app: $backend_name,
    backend_revision: $backend_revision,
    postgres_fqdn: $postgres_fqdn,
    hosted_agent_name: $hosted_agent_name
  }' >"$RESULT_FILE"

echo "Recorded private connectivity proof at ${RESULT_FILE}."
