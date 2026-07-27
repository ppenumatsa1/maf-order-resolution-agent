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
AGENT_NAME="${FOUNDRY_HOSTED_AGENT_NAME:-order-resolution-hosted}"

require_bin azd
require_bin jq

cd "$FOUNDRY_DIR"

connection_json="$(
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd ai connection show ApplicationInsights --output json --no-prompt
)"
application_insights_id="$(
  printf '%s' "$connection_json" |
    jq -r '.target // .metadata.ResourceId // .properties.target // empty'
)"
if [[ ! "$application_insights_id" =~ ^/subscriptions/.+/providers/Microsoft\.Insights/components/.+$ ]]; then
  echo "ApplicationInsights project connection does not resolve to an Application Insights resource ID."
  exit 1
fi
echo "Application Insights project binding: ${application_insights_id}"

agent_json="$(
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd ai agent show "$AGENT_NAME" --output json --no-prompt
)"
printf '%s' "$agent_json" |
  jq '{name, status, version, active_version, endpoint}' |
  sed -E 's#([a-zA-Z][a-zA-Z0-9+.-]*://)[^[:space:]@]+@#\1***@#g'

sessions_json="$(
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd ai agent sessions list --agent-name "$AGENT_NAME" --limit 10 --output json --no-prompt
)"
session_id="$(
  printf '%s' "$sessions_json" |
    jq -r 'first(.. | objects | .id? | strings) // empty'
)"
if [[ -z "$session_id" ]]; then
  echo "No hosted-agent session is available for observability diagnostics."
  exit 1
fi

diagnostic_lines="$(
  AZURE_DEV_USER_AGENT=microsoft_foundry_skill \
    azd ai agent monitor "$AGENT_NAME" \
      --session-id "$session_id" \
      --tail 250 \
      --utc \
      --no-prompt 2>&1 |
    grep -E 'HOSTED_ENV_DIAGNOSTIC|Hosted observability initialized' |
    tail -20 || true
)"
if [[ -z "$diagnostic_lines" ]]; then
  echo "The selected hosted-agent session has no startup observability diagnostic."
  exit 1
fi

printf '%s\n' "$diagnostic_lines" |
  sed -E \
    -e 's#([a-zA-Z][a-zA-Z0-9+.-]*://)[^[:space:]@]+@#\1***@#g' \
    -e 's/(password|token|secret|connection string)=([^[:space:]]+)/\1=***/Ig'

if ! grep -q '"applicationinsights_connection_string":{"present":true' <<<"$diagnostic_lines"; then
  echo "Foundry did not inject APPLICATIONINSIGHTS_CONNECTION_STRING into the hosted agent."
  exit 1
fi

echo "Hosted Application Insights injection is present."
