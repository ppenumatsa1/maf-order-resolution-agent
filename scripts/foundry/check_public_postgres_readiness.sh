#!/usr/bin/env bash
set -euo pipefail

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin az
require_bin jq

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-}}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-maf-ora-foundry}"
SERVER_NAME="${SERVER_NAME:-maffndpg7930}"
DATABASE_URL="${DATABASE_URL:-}"

if [[ -z "$SUBSCRIPTION_ID" ]]; then
  echo "SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID is required."
  exit 1
fi

server_json="$(
  az postgres flexible-server show \
    --subscription "$SUBSCRIPTION_ID" \
    --resource-group "$RESOURCE_GROUP" \
    --name "$SERVER_NAME" \
    --query '{name:name,state:state,fqdn:fullyQualifiedDomainName,location:location,publicNetworkAccess:network.publicNetworkAccess,sku:sku.name,tier:sku.tier,version:version,activeDirectoryAuth:authConfig.activeDirectoryAuth,passwordAuth:authConfig.passwordAuth}' \
    -o json
)"

state="$(echo "$server_json" | jq -r '.state // ""')"
fqdn="$(echo "$server_json" | jq -r '.fqdn // ""')"
public_network_access="$(echo "$server_json" | jq -r '.publicNetworkAccess // ""')"

echo "PostgreSQL server: $SERVER_NAME"
echo "Resource group: $RESOURCE_GROUP"
echo "State: ${state:-unknown}"
echo "Public network access: ${public_network_access:-unknown}"
echo "FQDN: ${fqdn:-unknown}"

if [[ "${state,,}" != "ready" ]]; then
  echo "Readiness check failed: server state is '${state}', expected 'Ready'."
  exit 1
fi

if [[ "${public_network_access,,}" != "enabled" ]]; then
  echo "Readiness check failed: public network access is '${public_network_access}', expected 'Enabled'."
  exit 1
fi

firewall_json="$(
  az postgres flexible-server firewall-rule list \
    --subscription "$SUBSCRIPTION_ID" \
    --resource-group "$RESOURCE_GROUP" \
    --name "$SERVER_NAME" \
    -o json
)"

allow_azure_services_count="$(echo "$firewall_json" | jq '[.[] | select(.startIpAddress=="0.0.0.0" and .endIpAddress=="0.0.0.0")] | length')"
if [[ "$allow_azure_services_count" -lt 1 ]]; then
  echo "Readiness check failed: expected at least one firewall rule allowing Azure services (0.0.0.0)."
  exit 1
fi
echo "Firewall check: Azure-services rule present."

if ! db_names="$(az postgres flexible-server db list --subscription "$SUBSCRIPTION_ID" --resource-group "$RESOURCE_GROUP" --server-name "$SERVER_NAME" --query '[].name' -o tsv 2>/dev/null)"; then
  echo "Readiness check warning: unable to list databases right now."
else
  echo "Databases:"
  if [[ -n "$db_names" ]]; then
    echo "$db_names"
  else
    echo "(none listed)"
  fi
fi

if [[ -n "$DATABASE_URL" ]]; then
  if [[ "$DATABASE_URL" != *"sslmode=require"* ]]; then
    echo "Readiness check failed: DATABASE_URL must include sslmode=require."
    exit 1
  fi
  if [[ -n "$fqdn" && "$DATABASE_URL" != *"$fqdn"* ]]; then
    echo "Readiness check failed: DATABASE_URL host does not match server FQDN."
    exit 1
  fi
  echo "DATABASE_URL check passed (TLS + host match)."
fi

echo "PostgreSQL readiness checks passed for public dev reuse."
