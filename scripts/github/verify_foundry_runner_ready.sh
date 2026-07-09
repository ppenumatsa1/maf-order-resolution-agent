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

runners_json="$(gh api "repos/${REPO}/actions/runners")"
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
