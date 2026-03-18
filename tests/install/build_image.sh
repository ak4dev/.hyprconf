#!/usr/bin/env bash
# Build the Arch+hyprconf test image using Packer
# Usage: bash tests/install/build_image.sh
set -euo pipefail
cd "$(dirname "$0")"
packer init arch.pkr.hcl
packer build arch.pkr.hcl
mv output-arch/arch-hyprconf.qcow2 ../vm/arch-hyprconf.qcow2
echo "Image built and moved to tests/vm/arch-hyprconf.qcow2"
