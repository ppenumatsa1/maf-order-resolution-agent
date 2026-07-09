#!/usr/bin/env bash
set -euo pipefail

# Idempotent host bootstrap for GitHub self-hosted runner VMs.
# Target: Ubuntu 22.04+ private runner hosts.
#
# Installs/verifies required packages and tools for Foundry workflows:
# - core tools: git, curl, jq, tar, unzip, make, ca-certificates
# - runtime tools: python3, pip, docker
# - azure tools: az CLI, azd

require_root_or_sudo() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    echo "This script requires root or sudo."
    exit 1
  fi
}

run_privileged() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_base_packages() {
  run_privileged apt-get update -y
  run_privileged apt-get install -y \
    git curl jq tar unzip make ca-certificates gnupg lsb-release \
    python3 python3-pip
}

install_docker_if_missing() {
  if have_cmd docker; then
    return
  fi

  run_privileged install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | run_privileged gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  run_privileged chmod a+r /etc/apt/keyrings/docker.gpg
  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
  arch="$(dpkg --print-architecture)"
  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${codename} stable" \
    | run_privileged tee /etc/apt/sources.list.d/docker.list >/dev/null
  run_privileged apt-get update -y
  run_privileged apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

install_az_if_missing() {
  if have_cmd az; then
    return
  fi

  curl -sL https://aka.ms/InstallAzureCLIDeb | run_privileged bash
}

install_azd_if_missing() {
  if have_cmd azd; then
    return
  fi

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  curl -fsSL https://aka.ms/install-azd.sh -o "${tmp_dir}/install-azd.sh"
  chmod +x "${tmp_dir}/install-azd.sh"
  run_privileged env PATH="$PATH:/usr/local/bin" "${tmp_dir}/install-azd.sh"
}

configure_runner_host_paths() {
  run_privileged mkdir -p /mnt/.azure /mnt/.azd /mnt/.tmp /mnt/actions-runner
  run_privileged chown -R "${RUNNER_USER}:${RUNNER_USER}" /mnt/.azure /mnt/.azd /mnt/.tmp /mnt/actions-runner

  grep -q '^AZURE_CONFIG_DIR=/mnt/.azure$' /etc/environment 2>/dev/null || echo 'AZURE_CONFIG_DIR=/mnt/.azure' | run_privileged tee -a /etc/environment >/dev/null
  grep -q '^AZD_CONFIG_DIR=/mnt/.azd$' /etc/environment 2>/dev/null || echo 'AZD_CONFIG_DIR=/mnt/.azd' | run_privileged tee -a /etc/environment >/dev/null
  grep -q '^TMPDIR=/mnt/.tmp$' /etc/environment 2>/dev/null || echo 'TMPDIR=/mnt/.tmp' | run_privileged tee -a /etc/environment >/dev/null
}

post_verify() {
  for cmd in git curl jq tar unzip make python3 pip3 docker az azd; do
    if ! have_cmd "$cmd"; then
      echo "Missing required command after bootstrap: $cmd"
      exit 1
    fi
  done

  run_privileged systemctl enable docker >/dev/null 2>&1 || true
  run_privileged systemctl start docker
  run_privileged usermod -aG docker "${RUNNER_USER}" || true
  run_privileged docker version >/dev/null

  echo "Runner host bootstrap completed successfully for user: ${RUNNER_USER}"
  echo "Note: If docker group was newly assigned, re-login may be required for non-sudo docker commands."
}

require_root_or_sudo
RUNNER_USER="${RUNNER_USER:-${SUDO_USER:-$USER}}"

install_base_packages
install_docker_if_missing
install_az_if_missing
install_azd_if_missing
configure_runner_host_paths
post_verify
