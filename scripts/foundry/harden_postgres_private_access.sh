#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP is required}"
: "${POSTGRES_SERVER_FQDN:?POSTGRES_SERVER_FQDN is required}"
: "${POSTGRES_PRIVATE_ENDPOINT_NAME:?POSTGRES_PRIVATE_ENDPOINT_NAME is required}"
: "${POSTGRES_PRIVATE_DNS_ZONE_NAME:?POSTGRES_PRIVATE_DNS_ZONE_NAME is required}"
: "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE:?POSTGRES_CONNECTIVITY_EVIDENCE_FILE is required}"

command -v jq >/dev/null 2>&1 || {
  echo "jq is required to validate PostgreSQL connectivity evidence."
  exit 1
}
[[ -f "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}" ]] || {
  echo "PostgreSQL connectivity evidence is required: ${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}"
  exit 1
}

canonical_fqdn="$(tr '[:upper:]' '[:lower:]' <<<"${POSTGRES_SERVER_FQDN%.}")"
if [[ ! "${canonical_fqdn}" =~ ^[a-z0-9][a-z0-9-]*\.postgres\.database\.azure\.com$ ]]; then
  echo "POSTGRES_SERVER_FQDN must be a PostgreSQL Flexible Server FQDN."
  exit 1
fi

evidence_status="$(jq -r '.status // empty' "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}")"
aca_connectivity="$(jq -r '.aca_database_connectivity // empty' "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}")"
hosted_agent_connectivity="$(jq -r '.hosted_agent_database_connectivity // empty' "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}")"
evidence_fqdn="$(jq -r '.postgres_fqdn // empty' "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}" | tr '[:upper:]' '[:lower:]')"
evidence_generated_at="$(jq -r '.generated_at // empty' "${POSTGRES_CONNECTIVITY_EVIDENCE_FILE}")"
evidence_epoch="$(date -u -d "${evidence_generated_at}" +%s 2>/dev/null || true)"
maximum_evidence_age_seconds="${POSTGRES_CONNECTIVITY_MAX_AGE_SECONDS:-3600}"
current_epoch="$(date -u +%s)"
evidence_age_seconds="$((current_epoch - evidence_epoch))"
if [[ "$evidence_status" != "passed" ||
      "$aca_connectivity" != "passed" ||
      "$hosted_agent_connectivity" != "passed" ||
      "$evidence_fqdn" != "$canonical_fqdn" ||
      -z "$evidence_epoch" ||
      "$evidence_age_seconds" -lt 0 ||
      "$evidence_age_seconds" -gt "$maximum_evidence_age_seconds" ]]; then
  echo "Refusing PostgreSQL public-access lockdown without current successful ACA and hosted-agent connectivity evidence for ${canonical_fqdn}."
  exit 1
fi

postgres_server_name="${canonical_fqdn%%.*}"
resolved_fqdn="$(
  az postgres flexible-server show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${postgres_server_name}" \
    --query fullyQualifiedDomainName \
    --output tsv
)"
if [[ "${resolved_fqdn,,}" != "${canonical_fqdn}" ]]; then
  echo "PostgreSQL Flexible Server ${postgres_server_name} does not resolve to the requested canonical FQDN."
  exit 1
fi
if [[ -n "${POSTGRES_SERVER_NAME:-}" && "${POSTGRES_SERVER_NAME}" != "${postgres_server_name}" ]]; then
  echo "POSTGRES_SERVER_NAME does not match the canonical server resolved from POSTGRES_SERVER_FQDN."
  exit 1
fi

server_id="$(
  az postgres flexible-server show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${postgres_server_name}" \
    --query id \
    --output tsv
)"
endpoint_target_id="$(
  az network private-endpoint show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_PRIVATE_ENDPOINT_NAME}" \
    --query 'privateLinkServiceConnections[0].privateLinkServiceId' \
    --output tsv
)"
endpoint_status="$(
  az network private-endpoint show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_PRIVATE_ENDPOINT_NAME}" \
    --query 'privateLinkServiceConnections[0].privateLinkServiceConnectionState.status' \
    --output tsv
)"
endpoint_group_id="$(
  az network private-endpoint show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_PRIVATE_ENDPOINT_NAME}" \
    --query 'privateLinkServiceConnections[0].groupIds[0]' \
    --output tsv
)"
if [[ "${endpoint_status}" != "Approved" || "${endpoint_group_id}" != "postgresqlServer" || "${endpoint_target_id,,}" != "${server_id,,}" ]]; then
  echo "PostgreSQL private endpoint must be Approved and target the canonical server using group postgresqlServer."
  exit 1
fi

endpoint_subnet_id="$(
  az network private-endpoint show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_PRIVATE_ENDPOINT_NAME}" \
    --query 'subnet.id' \
    --output tsv
)"
endpoint_nic_id="$(
  az network private-endpoint show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${POSTGRES_PRIVATE_ENDPOINT_NAME}" \
    --query 'networkInterfaces[0].id' \
    --output tsv
)"
endpoint_private_ip="$(
  az network nic show \
    --ids "${endpoint_nic_id}" \
    --query 'ipConfigurations[0].privateIPAddress' \
    --output tsv
)"
if [[ -z "${endpoint_subnet_id}" || -z "${endpoint_private_ip}" ]]; then
  echo "PostgreSQL private endpoint does not have a subnet and private IP."
  exit 1
fi

dns_record_name="${postgres_server_name}"
dns_record_ips="$(
  az network private-dns record-set a show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --zone-name "${POSTGRES_PRIVATE_DNS_ZONE_NAME}" \
    --name "${dns_record_name}" \
    --query 'aRecords[].ipv4Address' \
    --output tsv
)"
if ! grep -Fxq "${endpoint_private_ip}" <<<"${dns_record_ips}"; then
  echo "Private DNS record ${dns_record_name}.${POSTGRES_PRIVATE_DNS_ZONE_NAME} does not resolve to the PostgreSQL private endpoint IP."
  exit 1
fi

endpoint_vnet_id="${endpoint_subnet_id%/subnets/*}"
dns_linked_vnet_ids="$(
  az network private-dns link vnet list \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --zone-name "${POSTGRES_PRIVATE_DNS_ZONE_NAME}" \
    --query '[].virtualNetwork.id' \
    --output tsv
)"
if ! tr '[:upper:]' '[:lower:]' <<<"${dns_linked_vnet_ids}" | grep -Fxq "${endpoint_vnet_id,,}"; then
  echo "Private DNS zone ${POSTGRES_PRIVATE_DNS_ZONE_NAME} is not linked to the private endpoint VNet."
  exit 1
fi

public_network_access="$(
  az postgres flexible-server show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${postgres_server_name}" \
    --query 'network.publicNetworkAccess' \
    --output tsv
)"
if [[ "${public_network_access}" != "Enabled" && "${public_network_access}" != "Disabled" ]]; then
  echo "Unexpected PostgreSQL public network access state: ${public_network_access:-missing}"
  exit 1
fi

if [[ "${public_network_access}" == "Enabled" ]]; then
az postgres flexible-server update \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --name "${postgres_server_name}" \
  --public-access Disabled \
  --only-show-errors \
  --output none
fi

public_network_access="$(
  az postgres flexible-server show \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${postgres_server_name}" \
    --query 'network.publicNetworkAccess' \
    --output tsv
)"
if [[ "${public_network_access}" != "Disabled" ]]; then
  echo "PostgreSQL public access was not disabled; preserving the Azure-services firewall rule."
  exit 1
fi

azure_services_rule="$(
  az postgres flexible-server firewall-rule list \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${postgres_server_name}" \
    --query "[?name=='allow-azure-services'].name" \
    --output tsv
)"
if [[ "${azure_services_rule}" == "allow-azure-services" ]]; then
  az postgres flexible-server firewall-rule delete \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --name "${postgres_server_name}" \
    --rule-name allow-azure-services \
    --yes \
    --only-show-errors \
    --output none

  azure_services_rule="$(
    az postgres flexible-server firewall-rule list \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --name "${postgres_server_name}" \
      --query "[?name=='allow-azure-services'].name" \
      --output tsv
  )"
  if [[ -n "${azure_services_rule}" ]]; then
    echo "Azure-services firewall rule removal did not complete."
    exit 1
  fi
fi

echo "PostgreSQL public access disabled and Azure-services firewall rule removed."
