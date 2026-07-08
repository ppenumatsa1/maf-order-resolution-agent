#!/usr/bin/env bash
set -euo pipefail

# Bootstrap GitHub configuration for Foundry private runner pipelines.
# Requires: gh CLI, jq
#
# Usage:
#   export GH_PAT=...
#   export REPO=ppenumatsa1/maf-order-resolution-agent
#   export AZURE_CLIENT_ID=...
#   export AZURE_TENANT_ID=...
#   export AZURE_SUBSCRIPTION_ID=...
#   export FOUNDRY_RESOURCE_GROUP=rg-maf-ora-ni-eus-07080910
#   export FOUNDRY_PROJECT_ID=/subscriptions/.../accounts/.../projects/order-resolution-ni
#   export FOUNDRY_PROJECT_ENDPOINT=https://...services.ai.azure.com/api/projects/order-resolution-ni
#   export APPINSIGHTS_APP_ID=...
#   export FOUNDRY_RUNTIME_ENV_FILE=infra/foundry-hosted/runtime/.env
#   ./scripts/github/bootstrap_foundry_github_config.sh

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin gh
require_bin jq

: "${REPO:=}"
: "${AZURE_CLIENT_ID:?AZURE_CLIENT_ID is required}"
: "${AZURE_TENANT_ID:?AZURE_TENANT_ID is required}"
: "${AZURE_SUBSCRIPTION_ID:?AZURE_SUBSCRIPTION_ID is required}"
: "${FOUNDRY_RESOURCE_GROUP:?FOUNDRY_RESOURCE_GROUP is required}"
: "${FOUNDRY_PROJECT_ID:?FOUNDRY_PROJECT_ID is required}"
: "${FOUNDRY_PROJECT_ENDPOINT:?FOUNDRY_PROJECT_ENDPOINT is required}"
: "${APPINSIGHTS_APP_ID:?APPINSIGHTS_APP_ID is required}"

ENV_NAME="${ENV_NAME:-foundry-private-env}"
RUNNER_LABEL="${RUNNER_LABEL:-foundry-private}"
FOUNDRY_AZD_ENV_NAME="${FOUNDRY_AZD_ENV_NAME:-foundry-private-env}"
FOUNDRY_LOCATION="${FOUNDRY_LOCATION:-centralus}"
FOUNDRY_RUNTIME_ENV_FILE="${FOUNDRY_RUNTIME_ENV_FILE:-infra/foundry-hosted/runtime/.env}"

if [[ -z "$REPO" ]]; then
  remote_url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$remote_url" =~ github.com[:/]([^/]+/[^/.]+)(\.git)?$ ]]; then
    REPO="${BASH_REMATCH[1]}"
  fi
fi

if [[ -z "$REPO" ]]; then
  echo "REPO is required (owner/repo). Set REPO and retry."
  exit 1
fi

if [[ ! -f "$FOUNDRY_RUNTIME_ENV_FILE" ]]; then
  echo "FOUNDRY_RUNTIME_ENV_FILE does not exist: $FOUNDRY_RUNTIME_ENV_FILE"
  exit 1
fi

if [[ -n "${GH_PAT:-}" ]]; then
  export GH_TOKEN="$GH_PAT"
elif [[ -n "${GH_TOKEN:-}" ]]; then
  :
elif ! gh auth status >/dev/null 2>&1; then
  echo "No GitHub auth found. Set GH_PAT or run: gh auth login"
  exit 1
fi

echo "Creating/updating environment: $ENV_NAME"
gh api -X PUT "repos/$REPO/environments/$ENV_NAME" >/dev/null

echo "Setting repository variables"
gh variable set RUNNER_LABEL -R "$REPO" -b "$RUNNER_LABEL"
gh variable set AZURE_CLIENT_ID -R "$REPO" -b "$AZURE_CLIENT_ID"
gh variable set AZURE_TENANT_ID -R "$REPO" -b "$AZURE_TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID -R "$REPO" -b "$AZURE_SUBSCRIPTION_ID"
gh variable set FOUNDRY_RESOURCE_GROUP -R "$REPO" -b "$FOUNDRY_RESOURCE_GROUP"
gh variable set FOUNDRY_PROJECT_ID -R "$REPO" -b "$FOUNDRY_PROJECT_ID"
gh variable set FOUNDRY_PROJECT_ENDPOINT -R "$REPO" -b "$FOUNDRY_PROJECT_ENDPOINT"
gh variable set FOUNDRY_AZD_ENV_NAME -R "$REPO" -b "$FOUNDRY_AZD_ENV_NAME"
gh variable set FOUNDRY_LOCATION -R "$REPO" -b "$FOUNDRY_LOCATION"
gh variable set APPINSIGHTS_APP_ID -R "$REPO" -b "$APPINSIGHTS_APP_ID"

echo "Setting environment secret FOUNDRY_RUNTIME_ENV in $ENV_NAME"
gh secret set FOUNDRY_RUNTIME_ENV -R "$REPO" -e "$ENV_NAME" < "$FOUNDRY_RUNTIME_ENV_FILE"

echo "Validation: variables"
gh variable list -R "$REPO" --json name | jq -r '.[].name' | grep -E 'RUNNER_LABEL|AZURE_CLIENT_ID|AZURE_TENANT_ID|AZURE_SUBSCRIPTION_ID|FOUNDRY_RESOURCE_GROUP|FOUNDRY_PROJECT_ID|FOUNDRY_PROJECT_ENDPOINT|FOUNDRY_AZD_ENV_NAME|FOUNDRY_LOCATION|APPINSIGHTS_APP_ID' || true

echo "Validation: environment exists"
gh api "repos/$REPO/environments/$ENV_NAME" --jq '.name'

echo "Done. GitHub configuration is bootstrapped for Foundry private pipelines."