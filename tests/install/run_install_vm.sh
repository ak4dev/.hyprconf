#!/usr/bin/env bash
# tests/install/run_install_vm.sh — launch the install-test VM on port 2223
#
# Uses a QEMU COW overlay of tests/vm/arch-hyprconf.qcow2 so the base image
# is never modified by tier-5 tests. Each fresh start begins from the
# pristine post-install state.
#
# Prerequisites:
#   - qemu-full installed
#   - tests/vm/arch-hyprconf.qcow2 exists (build with: bash tests/install/build_image.sh)
#   - ~/.ssh/hyprconf_vm_key exists (no passphrase)
#
# Usage:
#   bash tests/install/run_install_vm.sh          # start VM in background
#   bash tests/install/run_install_vm.sh --stop   # kill the VM
#   bash tests/install/run_install_vm.sh --wait   # block until VM is SSH-reachable
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VM_DIR="${SCRIPT_DIR}/../vm"
BASE_IMAGE="${VM_DIR}/arch-hyprconf.qcow2"
COW_IMAGE="${VM_DIR}/arch-hyprconf-install-overlay.qcow2"
PID_FILE="/tmp/hyprconf-install-vm.pid"
SSH_PORT=2223
SSH_KEY="${HOME}/.ssh/hyprconf_vm_key"

OVMF_CODE="/usr/share/edk2/x64/OVMF_CODE.4m.fd"
OVMF_VARS_SRC="/usr/share/edk2/x64/OVMF_VARS.4m.fd"
OVMF_VARS="${VM_DIR}/OVMF_VARS_install.4m.fd"

_stop() {
    if [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}")
        kill "${pid}" 2>/dev/null && echo "Install VM stopped (PID ${pid})." || echo "Install VM was not running."
        rm -f "${PID_FILE}"
    else
        echo "No PID file found; install VM may not be running."
    fi
    # Remove COW overlay so next start gets a clean slate.
    rm -f "${COW_IMAGE}"
}

_wait_for_ssh() {
    echo "Waiting for install VM SSH on port ${SSH_PORT}..."
    local attempts=0
    while ! ssh -o StrictHostKeyChecking=no \
                -o UserKnownHostsFile=/dev/null \
                -o ConnectTimeout=3 \
                -o BatchMode=yes \
                -i "${SSH_KEY}" \
                -p "${SSH_PORT}" hyprtest@127.0.0.1 echo ok 2>/dev/null; do
        attempts=$((attempts + 1))
        if (( attempts > 80 )); then
            echo "ERROR: Install VM did not become reachable within 7 minutes." >&2
            exit 1
        fi
        sleep 5
    done
    echo "Install VM is reachable."
}

# Sync the VM's hyprconf repo to origin/dev using a host-side git bundle.
# Avoids outbound GitHub access from within the VM (QEMU SLiRP is unreliable
# for external hosts).
# The bundle also includes origin/stable (when available) so that hyprconf
# sync's mainline→stable migration path is exercisable in VM tests.
_sync_vm_to_dev() {
    echo "Syncing install VM repo to origin/dev..."
    local repo_root bundle
    repo_root="$(cd "${SCRIPT_DIR}/../.." && pwd)"
    bundle="/tmp/hyprconf-install-vm-sync.bundle"

    # Temporarily create a local stable branch from origin/stable so it can be
    # included in the bundle.  This gives the VM's clone a visible origin/stable
    # remote-tracking branch, enabling the mainline→stable migration test.
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

    scp -q \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -i "${SSH_KEY}" \
        -P "${SSH_PORT}" \
        "${bundle}" hyprtest@127.0.0.1:/tmp/hyprconf-install-vm-sync.bundle

    ssh -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 \
        -i "${SSH_KEY}" \
        -p "${SSH_PORT}" \
        hyprtest@127.0.0.1 \
        "rm -rf ~/.hyprconf \
         && git clone --quiet /tmp/hyprconf-install-vm-sync.bundle ~/.hyprconf \
         && git -C ~/.hyprconf remote set-url origin 'https://github.com/ak4dev/.hyprconf' \
         && rm -f /tmp/hyprconf-install-vm-sync.bundle \
         && echo 'Install VM repo synced to dev.'"

    rm -f "${bundle}"
}

case "${1:-}" in
    --stop)  _stop; exit 0 ;;
    --wait)  _wait_for_ssh; _sync_vm_to_dev; exit 0 ;;
esac

if [[ ! -f "${BASE_IMAGE}" ]]; then
    echo "ERROR: Base image not found at ${BASE_IMAGE}." >&2
    echo "Build it first with: bash tests/install/build_image.sh" >&2
    exit 1
fi

if [[ ! -f "${SSH_KEY}" ]]; then
    echo "Generating test SSH key at ${SSH_KEY}..."
    ssh-keygen -t ed25519 -f "${SSH_KEY}" -N ""
fi

# Create a fresh COW overlay — any writes during testing go here, not to the
# base image. Deleting it restores the pristine post-install state.
echo "Creating COW overlay of base image..."
rm -f "${COW_IMAGE}"
qemu-img create -f qcow2 -b "$(realpath "${BASE_IMAGE}")" -F qcow2 "${COW_IMAGE}"

# Writable EFI variable store (separate from tier-4's copy).
if [[ ! -f "${OVMF_VARS}" ]]; then
    cp "${OVMF_VARS_SRC}" "${OVMF_VARS}"
fi

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

echo "Install VM started (PID $(cat "${PID_FILE}"))."
_wait_for_ssh
_sync_vm_to_dev
