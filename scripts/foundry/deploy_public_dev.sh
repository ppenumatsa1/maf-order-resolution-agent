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

FOUNDRY_AZD_ENV_NAME="${FOUNDRY_AZD_ENV_NAME:-foundry-public-dev2}"
AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"
AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-maf-ora-foundry-public-dev2}"
AZURE_LOCATION="${AZURE_LOCATION:-eastus2}"
FOUNDRY_ACCOUNT_NAME="${FOUNDRY_ACCOUNT_NAME:-maffndaibfscpfhjr7sp4}"
FOUNDRY_PROJECT_NAME="${FOUNDRY_PROJECT_NAME:-order-resolution-public-managed-dev}"
FOUNDRY_HOSTED_AGENT_NAME="${FOUNDRY_HOSTED_AGENT_NAME:-order-resolution-hosted}"
FOUNDRY_TRACE_READER_PRINCIPAL_ID="${FOUNDRY_TRACE_READER_PRINCIPAL_ID:-$(az ad signed-in-user show --query id -o tsv)}"
POSTGRES_SERVER_NAME="${POSTGRES_SERVER_NAME:-maffndpgbfscpfhjr7sp4cu}"
POSTGRES_ADMIN_USERNAME="${POSTGRES_ADMIN_USERNAME:-pgadmin}"
POSTGRES_LOCATION="${POSTGRES_LOCATION:-centralus}"
RUNTIME_DATABASE_URL="${RUNTIME_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -z "$AZURE_SUBSCRIPTION_ID" ]]; then
  echo "AZURE_SUBSCRIPTION_ID is required."
  exit 1
fi
if [[ -z "$RUNTIME_DATABASE_URL" || -z "${POSTGRES_ADMIN_PASSWORD:-}" ]]; then
  echo "RUNTIME_DATABASE_URL (or DATABASE_URL) and POSTGRES_ADMIN_PASSWORD are required."
  exit 1
fi
if [[ "$POSTGRES_ADMIN_PASSWORD" == *$'\n'* || "$POSTGRES_ADMIN_PASSWORD" == *$'\r'* ]]; then
  echo "POSTGRES_ADMIN_PASSWORD must be a single-line value."
  exit 1
fi
if [[ "$RUNTIME_DATABASE_URL" != *"sslmode=require"* ]]; then
  echo "RUNTIME_DATABASE_URL must include sslmode=require."
  exit 1
fi
if [[ "$RUNTIME_DATABASE_URL" != *"${POSTGRES_SERVER_NAME}.postgres.database.azure.com"* ]]; then
  echo "RUNTIME_DATABASE_URL must target ${POSTGRES_SERVER_NAME}.postgres.database.azure.com."
  exit 1
fi
if [[ ! -f backend/agent.yaml || ! -f backend/foundry/main.py ]]; then
  echo "Hosted source validation failed: backend/agent.yaml and backend/foundry/main.py are required."
  exit 1
fi

AZURE_TENANT_ID="${AZURE_TENANT_ID:-$(az account show --subscription "$AZURE_SUBSCRIPTION_ID" --query tenantId -o tsv)}"
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
az account show --query id -o tsv | grep -qx "$AZURE_SUBSCRIPTION_ID"
azd auth login --check-status >/dev/null

echo "Selecting AZD environment: ${FOUNDRY_AZD_ENV_NAME}"
(
  cd infra/foundry-hosted
  azd env select "$FOUNDRY_AZD_ENV_NAME" || azd env new "$FOUNDRY_AZD_ENV_NAME"
  azd env set AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
  azd env set AZURE_RESOURCE_GROUP "$AZURE_RESOURCE_GROUP"
  azd env set AZURE_LOCATION "$AZURE_LOCATION"
  azd env set AZURE_TENANT_ID "$AZURE_TENANT_ID"
  azd env set FOUNDRY_ACCOUNT_NAME "$FOUNDRY_ACCOUNT_NAME"
  azd env set FOUNDRY_PROJECT_NAME "$FOUNDRY_PROJECT_NAME"
  azd env set HOSTED_AGENT_NAME "$FOUNDRY_HOSTED_AGENT_NAME"
  azd env set FOUNDRY_RUNTIME_DATABASE_URL "$RUNTIME_DATABASE_URL"
  azd env set DATABASE_URL "$RUNTIME_DATABASE_URL"
  azd env set RUNTIME_DATABASE_URL "$RUNTIME_DATABASE_URL"
  azd env set POSTGRES_SERVER_NAME "$POSTGRES_SERVER_NAME"
  azd env set POSTGRES_ADMIN_USERNAME "$POSTGRES_ADMIN_USERNAME"
  azd env set POSTGRES_ADMIN_PASSWORD "$POSTGRES_ADMIN_PASSWORD"
  azd env set POSTGRES_LOCATION "$POSTGRES_LOCATION"
  azd env set APP_ENV "${APP_ENV:-foundry-public-dev2}"
  azd env set STORE_PROVIDER "${STORE_PROVIDER:-postgres}"
  azd env set ENABLE_TELEMETRY "${ENABLE_TELEMETRY:-true}"
  azd env set ENABLE_INSTRUMENTATION "${ENABLE_INSTRUMENTATION:-true}"
  azd env set OTEL_SERVICE_NAME "${OTEL_SERVICE_NAME:-maf-order-resolution-foundry-public}"
  azd env set OTEL_RECORD_CONTENT "${OTEL_RECORD_CONTENT:-false}"
  azd env set FOUNDRY_TRACE_EVALUATION_RECORD_CONTENT "${FOUNDRY_TRACE_EVALUATION_RECORD_CONTENT:-true}"
)

FOUNDRY_PROJECT_NAME="$FOUNDRY_PROJECT_NAME" \
HOSTED_AGENT_NAME="$FOUNDRY_HOSTED_AGENT_NAME" \
./scripts/foundry/ensure_foundry_azd_defaults.sh

echo "Running local release gates"
LOCAL_DATABASE_URL="${LOCAL_DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/maf_workflow?sslmode=disable}"
DATABASE_URL="$LOCAL_DATABASE_URL" make test
DATABASE_URL="$LOCAL_DATABASE_URL" make eval-backend
DATABASE_URL="$LOCAL_DATABASE_URL" make test-e2e

echo "Provisioning and deploying public Foundry agent"
make foundry-up

echo "Running combined hosted smoke and E2E"
./scripts/foundry/hosted_e2e.sh

echo "Publishing enforced Foundry evaluation"
FOUNDRY_PROJECTS_ENDPOINT="$(cd infra/foundry-hosted && azd env get-value FOUNDRY_PROJECTS_ENDPOINT)" \
FOUNDRY_MODEL_DEPLOYMENT_NAME="$(cd infra/foundry-hosted && azd env get-value FOUNDRY_MODEL_DEPLOYMENT_NAME)" \
FOUNDRY_EVAL_MODEL="$(cd infra/foundry-hosted && azd env get-value FOUNDRY_EVAL_MODEL)" \
FOUNDRY_HOSTED_AGENT_NAME="$FOUNDRY_HOSTED_AGENT_NAME" \
FOUNDRY_EVAL_ENFORCE_PASS=true \
FOUNDRY_EVAL_MAX_ERRORED=0 \
make eval-foundry

echo "Verifying Application Insights telemetry"
./scripts/foundry/verify_telemetry.sh

echo "Public Foundry release completed for AZD environment: ${FOUNDRY_AZD_ENV_NAME}"
