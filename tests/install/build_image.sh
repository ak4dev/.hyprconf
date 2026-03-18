#!/usr/bin/env bash
# Build the Arch+hyprconf test image using Packer
# Usage: bash tests/install/build_image.sh
set -euo pipefail
cd "$(dirname "$0")"

SSH_KEY="${HOME}/.ssh/hyprconf_vm_key"

# Generate the test SSH key if it doesn't already exist.
if [[ ! -f "${SSH_KEY}" ]]; then
  echo "Generating test SSH key at ${SSH_KEY}..."
  ssh-keygen -t ed25519 -f "${SSH_KEY}" -N ""
fi

SSH_PUBKEY="$(cat "${SSH_KEY}.pub")"

packer init arch.pkr.hcl
packer build -force -var "ssh_pubkey=${SSH_PUBKEY}" arch.pkr.hcl
mv output-arch/arch-hyprconf.qcow2 ../vm/arch-hyprconf.qcow2
echo "Image built and moved to tests/vm/arch-hyprconf.qcow2"
