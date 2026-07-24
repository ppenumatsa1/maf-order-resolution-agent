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
#   export FOUNDRY_RESOURCE_GROUP=rg-maf-ora-foundry-v2
#   export FOUNDRY_PROJECT_NAME=order-resolution
#   export POSTGRES_SERVER_NAME=<canonical-private-flexible-server>
#   export POSTGRES_DATABASE_NAME=maf_workflow
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
: "${POSTGRES_SERVER_NAME:?POSTGRES_SERVER_NAME is required}"

ENV_NAME="foundry-private-env"
RUNNER_LABEL="foundry-private-v2"
FOUNDRY_PROJECT_NAME="${FOUNDRY_PROJECT_NAME:-order-resolution}"
POSTGRES_DATABASE_NAME="${POSTGRES_DATABASE_NAME:-maf_workflow}"

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

if [[ "$FOUNDRY_RESOURCE_GROUP" != "rg-maf-ora-foundry-v2" ||
      "$FOUNDRY_PROJECT_NAME" != "order-resolution" ||
      "$POSTGRES_DATABASE_NAME" != "maf_workflow" ]]; then
  echo "This bootstrap script only configures the canonical foundry-private-env target."
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

echo "Setting environment-scoped OIDC and target variables"
gh variable set AZURE_CLIENT_ID -R "$REPO" --env "$ENV_NAME" -b "$AZURE_CLIENT_ID"
gh variable set AZURE_TENANT_ID -R "$REPO" --env "$ENV_NAME" -b "$AZURE_TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID -R "$REPO" --env "$ENV_NAME" -b "$AZURE_SUBSCRIPTION_ID"
gh variable set FOUNDRY_RESOURCE_GROUP -R "$REPO" --env "$ENV_NAME" -b "$FOUNDRY_RESOURCE_GROUP"
gh variable set FOUNDRY_PROJECT_NAME -R "$REPO" --env "$ENV_NAME" -b "$FOUNDRY_PROJECT_NAME"
gh variable set POSTGRES_SERVER_NAME -R "$REPO" --env "$ENV_NAME" -b "$POSTGRES_SERVER_NAME"
gh variable set POSTGRES_DATABASE_NAME -R "$REPO" --env "$ENV_NAME" -b "$POSTGRES_DATABASE_NAME"
gh variable set RUNNER_LABEL -R "$REPO" --env "$ENV_NAME" -b "$RUNNER_LABEL"

echo "Validation: variables"
gh variable list -R "$REPO" --env "$ENV_NAME" --json name | jq -r '.[].name' | grep -E 'RUNNER_LABEL|AZURE_CLIENT_ID|AZURE_TENANT_ID|AZURE_SUBSCRIPTION_ID|FOUNDRY_RESOURCE_GROUP|FOUNDRY_PROJECT_NAME|POSTGRES_SERVER_NAME|POSTGRES_DATABASE_NAME' || true

echo "Validation: environment exists"
gh api "repos/$REPO/environments/$ENV_NAME" --jq '.name'

echo "Done. The private runner must retain the selected AZD environment and its secrets locally."