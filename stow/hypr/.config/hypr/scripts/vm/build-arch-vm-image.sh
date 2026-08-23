#!/usr/bin/env bash
# build-arch-vm-image.sh — Packer-build the Arch+hyprconf image for
# `gpu-passthrough.sh vm arch`
#
# Called by gpu-passthrough.sh's `vm arch install`/`build` subcommands, not
# normally run directly. Reads VM_USERNAME/VM_PASSWORD/VM_HOSTNAME/
# VM_TIMEZONE/VM_DISK from the environment (the `vm arch` config) and
# produces ~/.local/share/hyprconf/arch-vm/arch-hyprconf.qcow2 — a real
# hyprconf install, built the same way tests/install/build_image.sh builds
# the CI image, but via a real 'git clone' instead of a worktree tar.
#
# Prerequisites: packer, qemu-desktop (both checked by gpu-passthrough.sh
# before this runs).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"
# This file is a stowed symlink target; resolve the real repo root via git
# rather than a fixed relative-path climb, since the stow layout may change.
REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"

: "${VM_USERNAME:?VM_USERNAME must be set}"
: "${VM_PASSWORD:?VM_PASSWORD must be set}"
: "${VM_HOSTNAME:=hyprconf-arch-vm}"
: "${VM_TIMEZONE:=UTC}"
: "${VM_DISK:=64G}"

ARCHVM_DIR="${HOME}/.local/share/hyprconf/arch-vm"
BUILD_DIR="${ARCHVM_DIR}/.packer-build"
SSH_KEY="${HOME}/.ssh/hyprconf_arch_vm_key"

if [[ ! -f "${SSH_KEY}" ]]; then
  echo "Generating VM SSH key at ${SSH_KEY}..."
  ssh-keygen -t ed25519 -f "${SSH_KEY}" -N ""
fi
SSH_PUBKEY="$(cat "${SSH_KEY}.pub")"

mkdir -p "${ARCHVM_DIR}"
rm -rf "${BUILD_DIR}"

cd "${SCRIPT_DIR}"
packer init arch-vm.pkr.hcl
# The password travels in the environment (packer reads PKR_VAR_<name>), never
# as `-var` on the command line — argv is world-readable through procfs for as
# long as the build runs.
PKR_VAR_password="${VM_PASSWORD}" \
packer build -force \
  -var "username=${VM_USERNAME}" \
  -var "hostname=${VM_HOSTNAME}" \
  -var "timezone=${VM_TIMEZONE}" \
  -var "disk_size=${VM_DISK}" \
  -var "ssh_pubkey=${SSH_PUBKEY}" \
  -var "install_script_path=${REPO_ROOT}/install/install.sh" \
  -var "output_directory=${BUILD_DIR}" \
  arch-vm.pkr.hcl

mv "${BUILD_DIR}/arch-hyprconf.qcow2" "${ARCHVM_DIR}/arch-hyprconf.qcow2"
rm -rf "${BUILD_DIR}"

echo "Image built: ${ARCHVM_DIR}/arch-hyprconf.qcow2"
