#!/usr/bin/env bash
# tests/vm/run_vm.sh — launch the hyprconf test VM
#
# Prerequisites:
#   - qemu-full installed
#   - A test VM image at tests/vm/arch-hyprconf.qcow2
#     (build it with: packer build tests/install/arch.pkr.hcl)
#   - An SSH key at ~/.ssh/hyprconf_vm_key (no passphrase)
#     (generate with: ssh-keygen -t ed25519 -f ~/.ssh/hyprconf_vm_key -N "")
#
# Usage:
#   bash tests/vm/run_vm.sh          # start VM in background
#   bash tests/vm/run_vm.sh --stop   # kill the VM
#   bash tests/vm/run_vm.sh --wait   # block until VM is SSH-reachable
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE="${SCRIPT_DIR}/arch-hyprconf.qcow2"
COW_IMAGE="${SCRIPT_DIR}/arch-hyprconf-vm-overlay.qcow2"
PID_FILE="/tmp/hyprconf-vm.pid"
SSH_PORT=2222
SSH_KEY="${HOME}/.ssh/hyprconf_vm_key"

# UEFI firmware — systemd-boot requires UEFI; OVMF_VARS must be a writable copy.
OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
OVMF_VARS_SRC="/usr/share/edk2/x64/OVMF_VARS.4m.fd"
OVMF_VARS="${SCRIPT_DIR}/OVMF_VARS.4m.fd"

_stop() {
    if [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}")
        kill "${pid}" 2>/dev/null && echo "VM stopped (PID ${pid})." || echo "VM was not running."
        rm -f "${PID_FILE}"
    else
        echo "No PID file found; VM may not be running."
    fi
    rm -f "${COW_IMAGE}"
}

_wait_for_ssh() {
    echo "Waiting for VM SSH on port ${SSH_PORT}..."
    local attempts=0
    while ! ssh -o StrictHostKeyChecking=no \
                -o UserKnownHostsFile=/dev/null \
                -o ConnectTimeout=3 \
                -o BatchMode=yes \
                -i "${SSH_KEY}" \
                -p "${SSH_PORT}" hyprtest@127.0.0.1 echo ok 2>/dev/null; do
        attempts=$((attempts + 1))
        if (( attempts > 80 )); then
            echo "ERROR: VM did not become reachable within 7 minutes." >&2
            exit 1
        fi
        sleep 5
    done
    echo "VM is reachable."
}

# Ensure the VM's hyprconf repo is on origin/dev so that 'hyprconf sync'
# (which runs 'git restore .') restores to the current dev codebase.
# Uses a git bundle pushed host→VM to avoid any outbound network from the VM
# (QEMU SLiRP NAT cannot reach external hosts reliably).
# The bundle also includes origin/stable so VM tests can verify the remote ref.
_sync_vm_to_dev() {
    echo "Syncing VM repo to origin/dev..."
    local repo_root bundle
    repo_root="$(cd "${SCRIPT_DIR}/../.." && pwd)"
    bundle="/tmp/hyprconf-vm-sync.bundle"

    # Temporarily create a local stable branch from origin/stable so it can be
    # included in the bundle, giving the VM clone a visible origin/stable ref.
    local _created_stable=false
    if git -C "${repo_root}" show-ref --quiet refs/remotes/origin/stable 2>/dev/null \
       && ! git -C "${repo_root}" show-ref --quiet refs/heads/stable 2>/dev/null; then
        git -C "${repo_root}" branch stable origin/stable --quiet 2>/dev/null \
            && _created_stable=true
    fi

    # Bundle dev + stable (if available) so 'git clone' checks out dev.
    if git -C "${repo_root}" show-ref --quiet refs/heads/stable 2>/dev/null; then
        git -C "${repo_root}" bundle create "${bundle}" HEAD refs/heads/dev refs/heads/stable
    else
        git -C "${repo_root}" bundle create "${bundle}" HEAD refs/heads/dev
    fi

    # Remove the temp local stable branch (only if we just created it).
    if [[ "$_created_stable" == true ]]; then
        git -C "${repo_root}" branch -d stable --quiet 2>/dev/null || true
    fi

    # Push bundle to VM.
    scp -q \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -i "${SSH_KEY}" \
        -P "${SSH_PORT}" \
        "${bundle}" hyprtest@127.0.0.1:/tmp/hyprconf-vm-sync.bundle

    # On VM: replace the stub repo (git-init only) with a real clone from
    # the bundle, then point origin back at GitHub for informational purposes.
    ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 \
        -i "${SSH_KEY}" \
        -p "${SSH_PORT}" \
        hyprtest@127.0.0.1 \
        "rm -rf ~/.hyprconf \
         && git clone --quiet /tmp/hyprconf-vm-sync.bundle ~/.hyprconf \
         && git -C ~/.hyprconf remote set-url origin 'https://github.com/ak4dev/.hyprconf' \
         && rm -f /tmp/hyprconf-vm-sync.bundle \
         && echo 'VM repo synced to dev.'"

    rm -f "${bundle}"

    # Allow SSH through ufw so hyprconf sync (which enables ufw with deny-incoming)
    # does not lock out subsequent SSH connections from the test suite.
    ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 \
        -i "${SSH_KEY}" \
        -p "${SSH_PORT}" \
        hyprtest@127.0.0.1 \
        "sudo ufw allow ssh 2>/dev/null || true"
}

case "${1:-}" in
    --stop)  _stop; exit 0 ;;
    --wait)  _wait_for_ssh; _sync_vm_to_dev; exit 0 ;;
esac

if [[ ! -f "${BASE_IMAGE}" ]]; then
    echo "ERROR: VM image not found at ${BASE_IMAGE}." >&2
    echo "Build it first with: bash tests/install/build_image.sh" >&2
    exit 1
fi

if [[ ! -f "${SSH_KEY}" ]]; then
    echo "Generating test SSH key at ${SSH_KEY}..."
    ssh-keygen -t ed25519 -f "${SSH_KEY}" -N ""
fi

# Copy OVMF_VARS on first use so the writable EFI variable store persists
# across reboots but is never modified in place.
if [[ ! -f "${OVMF_VARS}" ]]; then
    cp "${OVMF_VARS_SRC}" "${OVMF_VARS}"
fi

# Create a fresh COW overlay so the base image is opened read-only.
# This avoids an exclusive write-lock on arch-hyprconf.qcow2, allowing the
# tier-5 install VM to use it as a backing file concurrently.
echo "Creating COW overlay of base image..."
rm -f "${COW_IMAGE}"
qemu-img create -f qcow2 -b "$(realpath "${BASE_IMAGE}")" -F qcow2 "${COW_IMAGE}"

# Launch QEMU with UEFI firmware + virtio-gpu-gl + egl-headless display
qemu-system-x86_64 \
    -enable-kvm \
    -machine q35 \
    -m 4G \
    -smp 2 \
    -drive if=pflash,format=raw,readonly=on,file="${OVMF_CODE}" \
    -drive if=pflash,format=raw,file="${OVMF_VARS}" \
    -drive file="${COW_IMAGE}",format=qcow2,if=virtio \
    -device virtio-gpu-gl \
    -display egl-headless \
    -net nic,model=virtio \
    -net user,hostfwd=tcp::${SSH_PORT}-:22 \
    -daemonize \
    -pidfile "${PID_FILE}"

echo "VM started (PID $(cat "${PID_FILE}"))."
_wait_for_ssh
_sync_vm_to_dev
