#!/usr/bin/env bash
set -euo pipefail

# Verify that a GitHub self-hosted runner with the required label is online.
# Usage:
#   REPO=owner/repo RUNNER_LABEL=foundry-private ./scripts/github/verify_foundry_runner_ready.sh

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required binary: $1"
    exit 1
  }
}

require_bin gh
require_bin jq

REPO="${REPO:-}"
RUNNER_LABEL="${RUNNER_LABEL:-foundry-private}"

if [[ -z "$REPO" ]]; then
  remote_url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$remote_url" =~ github.com[:/]([^/]+/[^/.]+)(\.git)?$ ]]; then
    REPO="${BASH_REMATCH[1]}"
  fi
fi

if [[ -z "$REPO" ]]; then
  echo "REPO is required (owner/repo)."
  exit 1
fi

gh_err_file="$(mktemp)"
if ! runners_json="$(gh api "repos/${REPO}/actions/runners" 2>"$gh_err_file")"; then
  if grep -q "Resource not accessible by integration" "$gh_err_file"; then
    if [[ "${RUNNER_PREFLIGHT_ALLOW_403:-false}" == "true" ]]; then
      echo "Runner readiness check warning: token cannot read repository runners (HTTP 403); continuing due to RUNNER_PREFLIGHT_ALLOW_403=true."
      echo "For strict preflight gating, grant actions:read on GITHUB_TOKEN (or use a token with Actions read scope)."
      rm -f "$gh_err_file"
      exit 0
    fi
    echo "Runner readiness check failed: current token cannot read repository runners (HTTP 403)."
    echo "Grant actions:read permission to GITHUB_TOKEN (or use a token with Actions read scope) for reliable preflight gating."
    rm -f "$gh_err_file"
    exit 1
  fi
  cat "$gh_err_file"
  rm -f "$gh_err_file"
  exit 1
fi
rm -f "$gh_err_file"
match_count="$(echo "$runners_json" | jq --arg label "$RUNNER_LABEL" '[.runners[] | select([.labels[].name] | index($label))] | length')"

if [[ "$match_count" -eq 0 ]]; then
  echo "No runner found with label '${RUNNER_LABEL}' in repo ${REPO}."
  exit 2
fi

online_count="$(echo "$runners_json" | jq --arg label "$RUNNER_LABEL" '[.runners[] | select(( [.labels[].name] | index($label)) and .status=="online")] | length')"
if [[ "$online_count" -eq 0 ]]; then
  echo "Runner(s) with label '${RUNNER_LABEL}' exist but none are online."
  echo "$runners_json" | jq --arg label "$RUNNER_LABEL" '.runners[] | select([.labels[].name] | index($label)) | {name, status, busy, labels:[.labels[].name]}'
  exit 3
fi

echo "Runner readiness check passed for label '${RUNNER_LABEL}'."
echo "$runners_json" | jq --arg label "$RUNNER_LABEL" '.runners[] | select(( [.labels[].name] | index($label)) and .status=="online") | {name, status, busy, labels:[.labels[].name]}'
