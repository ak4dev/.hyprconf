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

# Bundle the current repo as a tar so Packer can upload it directly.
# install.sh will extract this instead of cloning from GitHub, eliminating
# the QEMU network dependency and testing the same export-ignored payload that
# stable installs consume.
echo "Bundling repo from HEAD..."
git -C ../.. archive --worktree-attributes --format=tar.gz --prefix=".hyprconf/" HEAD \
  > /tmp/hyprconf-packer-repo.tar.gz
echo "Repo bundled to /tmp/hyprconf-packer-repo.tar.gz ($(du -sh /tmp/hyprconf-packer-repo.tar.gz | cut -f1))"

packer init arch.pkr.hcl
packer build -force -var "ssh_pubkey=${SSH_PUBKEY}" arch.pkr.hcl
mv output-arch/arch-hyprconf.qcow2 ../vm/arch-hyprconf.qcow2
rm -f /tmp/hyprconf-packer-repo.tar.gz

# Write build metadata alongside the image so scripts/publish can display it.
_GIT_COMMIT="$(git -C ../.. rev-parse --short HEAD 2>/dev/null || echo unknown)"
_BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > ../vm/arch-hyprconf.meta <<EOF
built_at=${_BUILT_AT}
git_commit=${_GIT_COMMIT}
EOF

echo "Image built and moved to tests/vm/arch-hyprconf.qcow2"
echo "Metadata: built_at=${_BUILT_AT}, git_commit=${_GIT_COMMIT}"
