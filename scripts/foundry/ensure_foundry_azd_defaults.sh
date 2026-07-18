#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}/infra/foundry-hosted"

get_env_value() {
  local key="$1"
  azd env get-value "$key" 2>/dev/null || true
}

set_if_missing() {
  local key="$1"
  local value="$2"
  local existing
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
if [[ "$mode" != "private" && "$mode" != "public" ]]; then
  echo "NETWORK_MODE must be 'public' or 'private'. Found: $mode"
  exit 1
fi

if [[ "$mode" == "private" ]]; then
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
else
  private_dns_default="false"
  private_endpoints_default="false"
  nat_default="false"
  runner_access_default="false"
  bastion_default="false"
  runner_vm_default="false"
  network_injection_default="false"
  assign_pre_caphost_default="false"
  assign_post_caphost_default="false"
  create_account_caphost_default="false"
  create_project_caphost_default="false"
  manage_project_connections_default="true"
fi

set_if_missing NETWORK_MODE "$mode"
set_if_missing AI_SEARCH_LOCATION "${AI_SEARCH_LOCATION:-eastus}"
set_if_missing FOUNDRY_PROJECT_NAME "${FOUNDRY_PROJECT_NAME:-order-resolution}"
set_if_missing HOSTED_AGENT_NAME "${HOSTED_AGENT_NAME:-order-resolution-hosted}"
set_if_missing RUNTIME_DATABASE_URL "${RUNTIME_DATABASE_URL:-}"
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
