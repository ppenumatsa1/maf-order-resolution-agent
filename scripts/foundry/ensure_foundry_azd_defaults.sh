#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}/infra/foundry-hosted"

get_env_value() {
  local key="$1"
  local value
  if value="$(azd env get-value "$key" 2>/dev/null)"; then
    printf "%s" "$value"
  fi
}

url_encode() {
  local raw="$1"
  python3 - "$raw" <<'PY'
import sys
from urllib.parse import quote
print(quote(sys.argv[1], safe=''))
PY
}

url_host() {
  local value="$1"
  python3 - "$value" <<'PY'
import re
import sys
match = re.match(r'^[a-zA-Z0-9+.-]+://(?:[^@/]+@)?([^:/?]+)', sys.argv[1] or '')
print(match.group(1).lower() if match else '')
PY
}

replace_url_host() {
  local value="$1"
  local new_host="$2"
  python3 - "$value" "$new_host" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

value = sys.argv[1]
new_host = sys.argv[2]
parts = urlsplit(value)
if not parts.scheme:
    print(value)
    raise SystemExit(0)

userinfo = ""
host_port = parts.netloc
if "@" in host_port:
    userinfo, host_port = host_port.rsplit("@", 1)

port = ""
if ":" in host_port:
    _, port = host_port.rsplit(":", 1)

netloc = f"{userinfo}@{new_host}" if userinfo else new_host
if port:
    netloc = f"{netloc}:{port}"

print(urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)))
PY
}

set_if_missing() {
  local key="$1"
  local value="$2"
  local existing
  if [[ -z "$value" ]]; then
    return
  fi
  existing="$(get_env_value "$key")"
  if [[ -z "$existing" ]]; then
    azd env set "$key" "$value" >/dev/null
    echo "defaulted $key=$value"
  fi
}

mode="${NETWORK_MODE:-$(get_env_value NETWORK_MODE)}"
if [[ -z "$mode" ]]; then
  mode="private"
fi
if [[ "$mode" != "private" ]]; then
  echo "NETWORK_MODE must be 'private' for this branch. Found: $mode"
  exit 1
fi

private_dns_default="true"
private_endpoints_default="true"
nat_default="true"
runner_access_default="false"
bastion_default="true"
runner_vm_default="true"
network_injection_default="true"
assign_pre_caphost_default="true"
assign_post_caphost_default="true"
create_account_caphost_default="false"
create_project_caphost_default="true"
manage_project_connections_default="true"

set_if_missing NETWORK_MODE "$mode"
set_if_missing AI_SEARCH_LOCATION "${AI_SEARCH_LOCATION:-eastus}"
set_if_missing FOUNDRY_PROJECT_NAME "${FOUNDRY_PROJECT_NAME:-order-resolution}"
set_if_missing HOSTED_AGENT_NAME "${HOSTED_AGENT_NAME:-order-resolution-hosted}"
set_if_missing RUNTIME_DATABASE_URL "${RUNTIME_DATABASE_URL:-}"
set_if_missing DATABASE_URL "${DATABASE_URL:-}"
set_if_missing CREATE_POSTGRES_SERVER "${CREATE_POSTGRES_SERVER:-true}"
set_if_missing POSTGRES_SERVER_NAME "${POSTGRES_SERVER_NAME:-maffndpg7930}"
set_if_missing POSTGRES_ADMIN_USERNAME "${POSTGRES_ADMIN_USERNAME:-pgadmin}"
set_if_missing POSTGRES_ADMIN_PASSWORD "${POSTGRES_ADMIN_PASSWORD:-}"
set_if_missing POSTGRES_DATABASE_NAME "${POSTGRES_DATABASE_NAME:-maf_workflow}"
set_if_missing POSTGRES_LOCATION "${POSTGRES_LOCATION:-centralus}"
set_if_missing CREATE_PRIVATE_DNS_VNET_LINKS "$private_dns_default"
set_if_missing CREATE_PRIVATE_ENDPOINTS "$private_endpoints_default"
set_if_missing CREATE_NAT_GATEWAY "$nat_default"
set_if_missing CREATE_PRIVATE_RUNNER_ACCESS "$runner_access_default"
set_if_missing CREATE_BASTION_HOST "$bastion_default"
set_if_missing CREATE_RUNNER_VM "$runner_vm_default"
set_if_missing ENABLE_STANDARD_AGENT_NETWORK_INJECTION "$network_injection_default"
set_if_missing ASSIGN_PRE_CAPHOST_RBAC "$assign_pre_caphost_default"
set_if_missing ASSIGN_POST_CAPHOST_RBAC "$assign_post_caphost_default"
set_if_missing CREATE_ACCOUNT_CAPABILITY_HOST "$create_account_caphost_default"
set_if_missing CREATE_PROJECT_CAPABILITY_HOST "$create_project_caphost_default"
set_if_missing MANAGE_PROJECT_CONNECTIONS "$manage_project_connections_default"
set_if_missing FOUNDRY_CHAT_DEPLOYMENT_CAPACITY "${FOUNDRY_CHAT_DEPLOYMENT_CAPACITY:-30}"
set_if_missing FOUNDRY_EMBEDDINGS_DEPLOYMENT_CAPACITY "${FOUNDRY_EMBEDDINGS_DEPLOYMENT_CAPACITY:-2}"
set_if_missing RUNNER_VM_SSH_PUBLIC_KEY "${RUNNER_VM_SSH_PUBLIC_KEY:-}"
set_if_missing APPLICATIONINSIGHTS_CONNECTION_STRING "${APPLICATIONINSIGHTS_CONNECTION_STRING:-$(get_env_value applicationInsightsConnectionString)}"
set_if_missing APPINSIGHTS_CONNECTION_STRING "${APPINSIGHTS_CONNECTION_STRING:-$(get_env_value APPLICATIONINSIGHTS_CONNECTION_STRING)}"
set_if_missing MAF_APPINSIGHTS_CONNECTION_STRING "${MAF_APPINSIGHTS_CONNECTION_STRING:-$(get_env_value APPINSIGHTS_CONNECTION_STRING)}"
set_if_missing ENABLE_TELEMETRY "${ENABLE_TELEMETRY:-true}"
set_if_missing ENABLE_INSTRUMENTATION "${ENABLE_INSTRUMENTATION:-true}"
set_if_missing OTEL_SERVICE_NAME "${OTEL_SERVICE_NAME:-maf-order-resolution-hosted}"
set_if_missing OTEL_SERVICE_NAMESPACE "${OTEL_SERVICE_NAMESPACE:-maf-order-resolution}"
set_if_missing OTEL_RECORD_CONTENT "${OTEL_RECORD_CONTENT:-false}"

appinsights_connection_string="$(get_env_value APPINSIGHTS_CONNECTION_STRING)"
if [[ -z "$appinsights_connection_string" ]]; then
  appinsights_connection_string="$(get_env_value APPLICATIONINSIGHTS_CONNECTION_STRING)"
fi
if [[ -n "$appinsights_connection_string" ]]; then
  appinsights_ikey="$(printf "%s" "$appinsights_connection_string" | sed -n 's/.*InstrumentationKey=\([^;]*\).*/\1/p')"
  appinsights_ingestion_endpoint="$(printf "%s" "$appinsights_connection_string" | sed -n 's/.*IngestionEndpoint=\([^;]*\).*/\1/p')"
  set_if_missing APPINSIGHTS_INSTRUMENTATIONKEY "$appinsights_ikey"
  set_if_missing APPINSIGHTS_INGESTIONENDPOINT "$appinsights_ingestion_endpoint"
fi

runtime_database_url_existing="$(get_env_value RUNTIME_DATABASE_URL)"
create_postgres_server="$(get_env_value CREATE_POSTGRES_SERVER)"
postgres_server_name="$(get_env_value POSTGRES_SERVER_NAME)"
postgres_admin_username="$(get_env_value POSTGRES_ADMIN_USERNAME)"
postgres_admin_password="$(get_env_value POSTGRES_ADMIN_PASSWORD)"
postgres_database_name="$(get_env_value POSTGRES_DATABASE_NAME)"

if [[ "$create_postgres_server" == "true" && -n "$postgres_server_name" ]]; then
  computed_runtime_database_url=""
  if [[ -n "$postgres_admin_username" && -n "$postgres_admin_password" && -n "$postgres_database_name" ]]; then
    encoded_password="$(url_encode "$postgres_admin_password")"
    computed_runtime_database_url="postgresql://${postgres_admin_username}:${encoded_password}@${postgres_server_name}.postgres.database.azure.com:5432/${postgres_database_name}?sslmode=require"
  fi
  expected_host="${postgres_server_name}.postgres.database.azure.com"
  runtime_host="$(url_host "$runtime_database_url_existing")"
  runtime_legacy_scheme="false"
  if [[ "$runtime_database_url_existing" == postgresql+psycopg://* ]]; then
    runtime_legacy_scheme="true"
  fi

  if [[ -z "$runtime_database_url_existing" && -n "$computed_runtime_database_url" ]]; then
    azd env set RUNTIME_DATABASE_URL "$computed_runtime_database_url" >/dev/null
    echo "defaulted RUNTIME_DATABASE_URL from postgres settings"
  elif [[ "$runtime_host" != "$expected_host" || "$runtime_legacy_scheme" == "true" ]]; then
    sync_runtime_database_url="$computed_runtime_database_url"
    if [[ -z "$sync_runtime_database_url" && -n "$runtime_database_url_existing" ]]; then
      sync_runtime_database_url="$(replace_url_host "$runtime_database_url_existing" "$expected_host")"
    fi
    if [[ -n "$sync_runtime_database_url" ]]; then
      azd env set RUNTIME_DATABASE_URL "$sync_runtime_database_url" >/dev/null
      azd env set DATABASE_URL "$sync_runtime_database_url" >/dev/null
      azd env set runtimeDatabaseUrl "$sync_runtime_database_url" >/dev/null
      azd env set databaseUrl "$sync_runtime_database_url" >/dev/null
      echo "synchronized runtime DB URLs to current postgres server host ${expected_host}"
    fi
  fi
fi

set_if_missing DATABASE_URL "$(get_env_value RUNTIME_DATABASE_URL)"

# Preserve lowercase env keys used by older scripts/workflows.
set_if_missing aiSearchLocation "$(get_env_value AI_SEARCH_LOCATION)"
set_if_missing foundryProjectName "$(get_env_value FOUNDRY_PROJECT_NAME)"
set_if_missing hostedAgentName "$(get_env_value HOSTED_AGENT_NAME)"
set_if_missing networkMode "$(get_env_value NETWORK_MODE)"
set_if_missing createPrivateDnsVnetLinks "$(get_env_value CREATE_PRIVATE_DNS_VNET_LINKS)"
set_if_missing createPrivateEndpoints "$(get_env_value CREATE_PRIVATE_ENDPOINTS)"
set_if_missing createNatGateway "$(get_env_value CREATE_NAT_GATEWAY)"
set_if_missing createPrivateRunnerAccess "$(get_env_value CREATE_PRIVATE_RUNNER_ACCESS)"
set_if_missing createBastionHost "$(get_env_value CREATE_BASTION_HOST)"
set_if_missing createRunnerVm "$(get_env_value CREATE_RUNNER_VM)"
set_if_missing enableStandardAgentNetworkInjection "$(get_env_value ENABLE_STANDARD_AGENT_NETWORK_INJECTION)"
set_if_missing assignPreCaphostRbac "$(get_env_value ASSIGN_PRE_CAPHOST_RBAC)"
set_if_missing assignPostCaphostRbac "$(get_env_value ASSIGN_POST_CAPHOST_RBAC)"
set_if_missing createAccountCapabilityHost "$(get_env_value CREATE_ACCOUNT_CAPABILITY_HOST)"
set_if_missing createProjectCapabilityHost "$(get_env_value CREATE_PROJECT_CAPABILITY_HOST)"
set_if_missing manageProjectConnections "$(get_env_value MANAGE_PROJECT_CONNECTIONS)"
set_if_missing foundryChatDeploymentCapacity "$(get_env_value FOUNDRY_CHAT_DEPLOYMENT_CAPACITY)"
set_if_missing foundryEmbeddingsDeploymentCapacity "$(get_env_value FOUNDRY_EMBEDDINGS_DEPLOYMENT_CAPACITY)"
set_if_missing runnerVmSshPublicKey "$(get_env_value RUNNER_VM_SSH_PUBLIC_KEY)"
set_if_missing runtimeDatabaseUrl "$(get_env_value RUNTIME_DATABASE_URL)"
set_if_missing databaseUrl "$(get_env_value DATABASE_URL)"
set_if_missing applicationInsightsConnectionString "$(get_env_value APPLICATIONINSIGHTS_CONNECTION_STRING)"
