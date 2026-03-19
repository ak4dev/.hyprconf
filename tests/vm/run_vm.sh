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
IMAGE="${SCRIPT_DIR}/arch-hyprconf.qcow2"
PID_FILE="/tmp/hyprconf-vm.pid"
SSH_PORT=2222
SSH_KEY="${HOME}/.ssh/hyprconf_vm_key"

_stop() {
    if [[ -f "${PID_FILE}" ]]; then
        local pid
        pid=$(cat "${PID_FILE}")
        kill "${pid}" 2>/dev/null && echo "VM stopped (PID ${pid})." || echo "VM was not running."
        rm -f "${PID_FILE}"
    else
        echo "No PID file found; VM may not be running."
    fi
}

_wait_for_ssh() {
    echo "Waiting for VM SSH on port ${SSH_PORT}..."
    local attempts=0
    while ! ssh -o StrictHostKeyChecking=no \
                -o ConnectTimeout=3 \
                -o BatchMode=yes \
                -i "${SSH_KEY}" \
                -p "${SSH_PORT}" hyprtest@127.0.0.1 echo ok 2>/dev/null; do
        attempts=$((attempts + 1))
        if (( attempts > 40 )); then
            echo "ERROR: VM did not become reachable within 2 minutes." >&2
            exit 1
        fi
        sleep 3
    done
    echo "VM is reachable."
}

case "${1:-}" in
    --stop)  _stop; exit 0 ;;
    --wait)  _wait_for_ssh; exit 0 ;;
esac

if [[ ! -f "${IMAGE}" ]]; then
    echo "ERROR: VM image not found at ${IMAGE}." >&2
    echo "Build it first with: bash tests/install/build_image.sh" >&2
    exit 1
fi

if [[ ! -f "${SSH_KEY}" ]]; then
    echo "Generating test SSH key at ${SSH_KEY}..."
    ssh-keygen -t ed25519 -f "${SSH_KEY}" -N ""
fi

# Launch QEMU with virtio-gpu-gl + egl-headless display (OpenGL without a window)
qemu-system-x86_64 \
    -enable-kvm \
    -m 4G \
    -smp 2 \
    -drive file="${IMAGE}",format=qcow2,if=virtio \
    -device virtio-gpu-gl \
    -display egl-headless \
    -net nic,model=virtio \
    -net user,hostfwd=tcp::${SSH_PORT}-:22 \
    -daemonize \
    -pidfile "${PID_FILE}"

echo "VM started (PID $(cat "${PID_FILE}"))."
_wait_for_ssh
