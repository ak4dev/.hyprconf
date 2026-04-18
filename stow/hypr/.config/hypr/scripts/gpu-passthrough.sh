#!/usr/bin/env bash
set -euo pipefail

# gpu-passthrough.sh — GPU detection, VFIO mode management, and passthrough
#
# Sourced by the hyprconf binary (hyprconf hardware gpu …).
# All functions prefixed with _gpu_ to avoid namespace collisions.
#
# Mode system (mirrors omarchy approach):
#   mode vm   — bind GPU + IOMMU group to vfio-pci (ready for VM)
#   mode host — unbind from vfio-pci, reload native driver
#   mode none — unbind from all drivers (power saving)
#
# No libvirt dependency — all binding via direct sysfs writes.

readonly _GPU_CONF_DIR="${HOME}/.config/hyprconf"
readonly _GPU_CONF="${_GPU_CONF_DIR}/gpu-passthrough.conf"
readonly _GPU_LOG="/tmp/hyprconf-gpu-passthrough.log"
: "${_GPU_BLACKLIST_CONF:=/etc/modprobe.d/blacklist-gpu-passthrough.conf}"
readonly _GPU_VFIO_CONF="/etc/modprobe.d/vfio.conf"
readonly _GPU_STATE_MARKER="/var/run/hyprconf-gpu-mode"
: "${_GPU_SYSFS:=/sys}"

# ── Logging ────────────────────────────────────────────────────────────────────

_gpu_log() {
    local level="$1"; shift
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" >> "$_GPU_LOG" 2>/dev/null || true
}

# ── PCI Helpers (mirrors omarchy utils) ────────────────────────────────────────

_gpu_normalize_pci() {
    # Normalize a PCI address to 0000:XX:XX.X form.
    local pci="$1"
    [[ -z "$pci" ]] && return 1
    [[ ! "$pci" =~ ^[0-9a-fA-F]{4}: ]] && pci="0000:${pci}"
    if [[ ! "$pci" =~ ^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$ ]]; then
        return 1
    fi
    echo "$pci"
}

_gpu_get_pci_driver() {
    # Read current driver (empty string if none). Delegates to sysfs-based lookup.
    local d; d=$(_gpu_current_driver "$1")
    [[ "$d" == "none" ]] && d=""
    echo "$d"
}

_gpu_get_pci_class() {
    # Read PCI device class code (e.g. 0300 for VGA, 0604 for bridge).
    local pci_addr="$1"
    lspci -Dn -s "$pci_addr" 2>/dev/null | awk '{print $2}' | cut -d: -f1 || true
}

_gpu_get_pci_device_id() {
    # Read vendor:device ID (e.g. 10de:2684).
    local pci_addr="$1"
    lspci -nn -s "$pci_addr" 2>/dev/null | grep -oP '\[\K[0-9a-f]{4}:[0-9a-f]{4}(?=\])' | tail -1 || true
}

_gpu_is_module_loaded() {
    local module="$1"
    [[ -z "$module" ]] && return 1
    lsmod 2>/dev/null | grep -q "^${module}[[:space:]]"
}

_gpu_ensure_sudo() {
    # Validate sudo credentials (prompts for password if needed).
    # All subsequent sudo -n calls will use the cached credential.
    if ! sudo -v 2>/dev/null; then
        printf "  ✘ Root privileges required. Run with: sudo hyprconf hardware gpu mode ...\n" >&2
        return 1
    fi
}

_gpu_sysfs_write() {
    # Write a value to a sysfs path with a timeout to prevent kernel hangs.
    # Usage: _gpu_sysfs_write <value> <sysfs_path>
    local value="$1" path="$2"
    if ! timeout 5 bash -c 'echo "$1" | sudo -n tee "$2" > /dev/null 2>&1' _ "$value" "$path"; then
        _gpu_log "WARN" "sysfs write timed out or failed: $path"
        return 1
    fi
}

# ── GPU Detection ──────────────────────────────────────────────────────────────

_gpu_list_raw() {
    # Output: PCI_ADDR VENDOR_ID:DEVICE_ID DESCRIPTION
    lspci -nn 2>/dev/null | grep -iE '(VGA compatible controller|3D controller|Display controller)' || true
}

_gpu_audio_device() {
    # Find the companion audio device at the same PCI bus slot.
    local pci_addr="$1"
    local bus_slot="${pci_addr%.*}"
    local audio_line
    audio_line=$(lspci -nn 2>/dev/null | grep "^${bus_slot}\." | grep -i "audio" | head -1)
    if [[ -n "$audio_line" ]]; then
        local audio_addr audio_ids
        audio_addr=$(echo "$audio_line" | awk '{print $1}')
        audio_ids=$(echo "$audio_line" | grep -oP '\[\w{4}:\w{4}\]' | tr -d '[]')
        printf "%s (%s)" "$audio_addr" "$audio_ids"
    fi
}

_gpu_iommu_group_details() {
    # Print all devices in the given IOMMU group with descriptions and warnings.
    local pci_addr="$1"
    local iommu_grp="$2"

    [[ -z "$iommu_grp" ]] && return

    local devs
    devs=$(_gpu_iommu_devices "$pci_addr") || return 0
    [[ -z "$devs" ]] && return

    local dev_count
    dev_count=$(echo "$devs" | wc -l)
    (( dev_count > 1 )) || return 0

    printf "  IOMMU Devices:  (%d devices)\n" "$dev_count"
    local dev
    while IFS= read -r dev; do
        [[ -z "$dev" ]] && continue
        local desc
        desc=$(lspci -nn 2>/dev/null | grep "^${dev} " | sed 's/^[0-9a-f:.]* //' || true)
        printf "    %s: %s\n" "$dev" "${desc:-unknown}"
    done <<< "$devs"

    # Warnings for problematic device types in the group
    while IFS= read -r dev; do
        [[ -z "$dev" ]] && continue
        local dev_desc
        dev_desc=$(lspci -nn 2>/dev/null | grep "^${dev} " || true)
        if echo "$dev_desc" | grep -qi "USB controller"; then
            printf "    ⚠ USB controller in IOMMU group (GPU has USB-C port)\n"
            printf "    ⚠ Unplug USB devices from GPU's USB-C before VM start\n"
        fi
        if echo "$dev_desc" | grep -qi "PCI bridge"; then
            printf "    ⚠ PCI bridge in IOMMU group\n"
        fi
    done <<< "$devs"
}

_gpu_detect() {
    # Print detected GPUs in a structured format.
    local idx=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        idx=$((idx + 1))

        local pci_addr vendor_device name driver type iommu_grp
        pci_addr=$(echo "$line" | awk '{print $1}')
        vendor_device=$(echo "$line" | grep -oP '\[\w{4}:\w{4}\]' | tr -d '[]')
        name=$(echo "$line" | sed -E 's/^[0-9a-f:.]+\s+[^:]+:\s+//' | sed -E 's/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]//g' | sed -E 's/\s*\(rev [^)]+\)//')
        driver=$(_gpu_current_driver "$pci_addr")
        type=$(_gpu_classify "$pci_addr" "$name")
        iommu_grp=$(_gpu_iommu_group "$pci_addr")

        printf "GPU %d: %s\n" "$idx" "$name"
        printf "  PCI Address:    %s\n" "$pci_addr"
        printf "  Vendor:Device:  %s\n" "$vendor_device"
        printf "  Type:           %s\n" "$type"
        printf "  Driver:         %s\n" "${driver:-none}"

        # Audio device at same bus slot
        local audio_info
        audio_info=$(_gpu_audio_device "$pci_addr")
        if [[ -n "$audio_info" ]]; then
            printf "  Audio Device:   %s\n" "$audio_info"
        fi

        printf "  IOMMU Group:    %s\n" "${iommu_grp:-unknown}"

        # List all IOMMU group devices with warnings
        _gpu_iommu_group_details "$pci_addr" "$iommu_grp"

        printf "\n"
    done < <(_gpu_list_raw)

    if (( idx == 0 )); then
        printf "No GPUs detected.\n"
        return 1
    fi
}

_gpu_classify() {
    local pci_addr="$1" name="$2"
    # Integrated if at 00:02.0 (Intel iGPU) or contains "Integrated"
    if [[ "$pci_addr" == "00:02.0" ]] || echo "$name" | grep -qi "integrated"; then
        echo "integrated"
    else
        echo "dedicated"
    fi
}

_gpu_is_display_gpu() {
    # Return 0 if the GPU at pci_addr has an active display connector.
    local pci_addr="$1"
    local full_addr="0000:${pci_addr}"
    local drm_dir="/sys/bus/pci/devices/${full_addr}/drm"

    [[ -d "$drm_dir" ]] || return 1

    local card status_file
    for card in "$drm_dir"/card*; do
        [[ -d "$card" ]] || continue
        local card_name
        card_name=$(basename "$card")
        for status_file in /sys/class/drm/"${card_name}"-*/status; do
            [[ -f "$status_file" ]] || continue
            if [[ "$(cat "$status_file" 2>/dev/null)" == "connected" ]]; then
                return 0
            fi
        done
    done
    return 1
}

_gpu_current_driver() {
    local pci_addr="$1"
    local full_addr="0000:${pci_addr}"
    local driver_link="/sys/bus/pci/devices/${full_addr}/driver"
    if [[ -L "$driver_link" ]]; then
        basename "$(readlink "$driver_link")"
    else
        echo "none"
    fi
}

_gpu_detect_mode() {
    # Detect the current GPU mode from its driver.
    local driver="$1"
    case "$driver" in
        vfio-pci) echo "vm" ;;
        nvidia|nvidia_drm|amdgpu|i915) echo "host" ;;
        none|"") echo "none" ;;
        *) echo "unknown" ;;
    esac
}

_gpu_iommu_group() {
    local pci_addr="$1"
    local full_addr="0000:${pci_addr}"
    local iommu_link="/sys/bus/pci/devices/${full_addr}/iommu_group"
    if [[ -L "$iommu_link" ]]; then
        basename "$(readlink "$iommu_link")"
    else
        echo ""
    fi
}

_gpu_iommu_devices() {
    # List all PCI addresses in the same IOMMU group as the given device.
    local pci_addr="$1"
    local group
    group=$(_gpu_iommu_group "$pci_addr")
    [[ -z "$group" ]] && return 1

    local grp_dir="/sys/kernel/iommu_groups/${group}/devices"
    [[ -d "$grp_dir" ]] || return 1

    local dev
    for dev in "$grp_dir"/*; do
        basename "$dev" | sed 's/^0000://'
    done
}

# ── GPU Name Resolution ────────────────────────────────────────────────────────

_gpu_resolve() {
    # Resolve a user-friendly GPU identifier to a PCI address.
    # Accepts: PCI address (01:00.0), partial model name (3070, 5090),
    #          or ordinal (nvidia0, nvidia1).
    local input="$1"

    # Already a PCI address (e.g. 01:00.0)?
    if [[ "$input" =~ ^[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]$ ]]; then
        echo "$input"
        return 0
    fi

    # Ordinal (nvidia0, nvidia1)?
    if [[ "$input" =~ ^nvidia([0-9]+)$ ]]; then
        local ordinal="${BASH_REMATCH[1]}"
        local idx=0
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            if echo "$line" | grep -qi nvidia; then
                if (( idx == ordinal )); then
                    echo "$line" | awk '{print $1}'
                    return 0
                fi
                idx=$((idx + 1))
            fi
        done < <(_gpu_list_raw)
        return 1
    fi

    # Partial model name match (e.g. "3070", "5090", "RTX 3070")
    local match_count=0 match_addr=""
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        if echo "$line" | grep -qi "$input"; then
            match_addr=$(echo "$line" | awk '{print $1}')
            match_count=$((match_count + 1))
        fi
    done < <(_gpu_list_raw)

    if (( match_count == 1 )); then
        echo "$match_addr"
        return 0
    elif (( match_count > 1 )); then
        echo "Ambiguous: '$input' matches $match_count GPUs. Be more specific." >&2
        return 1
    else
        echo "No GPU matching '$input' found." >&2
        return 1
    fi
}

# ── VT Console / Framebuffer Unbind ────────────────────────────────────────────

_gpu_unbind_vtconsoles() {
    # Unbind VT consoles and EFI framebuffer before GPU driver unbind.
    # Without this, the kernel blocks sysfs unbind writes because the
    # boot console or EFI framebuffer still holds a reference to the GPU.
    _gpu_log "INFO" "Unbinding VT consoles and framebuffer..."

    local vtcon
    for vtcon in "${_GPU_SYSFS}/class/vtconsole"/vtcon*; do
        [[ -f "$vtcon/bind" ]] || continue
        if [[ "$(cat "$vtcon/bind" 2>/dev/null)" == "1" ]]; then
            printf "  Unbinding %s...\n" "$(basename "$vtcon")"
            _gpu_sysfs_write 0 "$vtcon/bind" || true
        fi
    done

    # Unbind EFI framebuffer if bound to the GPU
    if [[ -e "${_GPU_SYSFS}/bus/platform/drivers/efi-framebuffer/efi-framebuffer.0" ]]; then
        printf "  Unbinding EFI framebuffer...\n"
        _gpu_sysfs_write efi-framebuffer.0 "${_GPU_SYSFS}/bus/platform/drivers/efi-framebuffer/unbind" || true
    fi
}

# ── NVIDIA Module Management ───────────────────────────────────────────────────

_gpu_nvidia_used_by_other_gpu() {
    # Return 0 if nvidia driver is bound to devices OUTSIDE our IOMMU group.
    # In multi-GPU setups the display GPU shares nvidia modules with the
    # passthrough GPU — modules cannot (and need not) be unloaded.
    local nvidia_drv_dir="${_GPU_SYSFS}/bus/pci/drivers/nvidia"
    [[ -d "$nvidia_drv_dir" ]] || return 1

    local iommu_list=" ${GPU_IOMMU_DEVICES:-} "
    local bound_dev short_addr
    for bound_dev in "$nvidia_drv_dir"/0000:*; do
        [[ -e "$bound_dev" ]] || continue
        short_addr=$(basename "$bound_dev" | sed 's/^0000://')
        if [[ "$iommu_list" != *" $short_addr "* ]]; then
            return 0
        fi
    done
    return 1
}

_gpu_has_other_nvidia_gpu() {
    # Return 0 if other NVIDIA VGA/3D GPUs exist besides the passthrough GPU.
    # Uses lspci (works at setup time before drivers are bound).
    local passthrough_addr="${GPU_PCI_ADDR:-}"
    local pci_addr
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        echo "$line" | grep -q '\[10de:' || continue
        pci_addr=$(echo "$line" | awk '{print $1}')
        [[ "$pci_addr" != "$passthrough_addr" ]] && return 0
    done < <(_gpu_list_raw)
    return 1
}

_gpu_unload_nvidia_modules() {
    # Unload NVIDIA modules in dependency order (drm → modeset → uvm → nvidia).
    # Returns non-zero if modules cannot be unloaded (GPU still in use).
    printf "  Unloading NVIDIA modules...\n"
    _gpu_log "INFO" "Unloading NVIDIA modules..."

    local mod
    for mod in nvidia_drm nvidia_modeset nvidia_uvm nvidia; do
        if _gpu_is_module_loaded "$mod"; then
            if sudo -n modprobe -r "$mod" 2>/dev/null; then
                _gpu_log "INFO" "$mod unloaded"
            else
                _gpu_log "WARN" "$mod: in use — retrying after 1s..."
                sleep 1
                if sudo -n modprobe -r "$mod" 2>/dev/null; then
                    _gpu_log "INFO" "$mod unloaded on retry"
                else
                    printf "  ✘ Cannot unload %s — GPU still in use.\n" "$mod" >&2
                    printf "    Close GPU applications (games, browsers with HW accel, etc.) first.\n" >&2
                    _gpu_log "ERROR" "$mod: cannot unload after retry"
                    return 1
                fi
            fi
        fi
    done

    # Final verification — catch any leftover nvidia modules
    if lsmod 2>/dev/null | grep -q "^nvidia"; then
        printf "  ✘ NVIDIA modules still loaded. Close all GPU applications first.\n" >&2
        _gpu_log "ERROR" "NVIDIA modules still present after unload attempt"
        return 1
    fi
    return 0
}

# ── Safety Checks (mirrors omarchy) ───────────────────────────────────────────

_gpu_check_processes() {
    # Abort if the GPU is actively in use.
    local current_driver="$1"

    [[ -z "$current_driver" || "$current_driver" == "none" ]] && return 0

    _gpu_log "INFO" "Checking for processes using GPU..."

    if [[ "$current_driver" == "nvidia" ]]; then
        local gpu_mem=0
        if command -v nvidia-smi &>/dev/null; then
            gpu_mem=$(nvidia-smi --query-compute-apps=used_memory --format=csv,noheader,nounits 2>/dev/null \
                | awk '{sum+=$1} END {print sum+0}' || echo 0)
        fi
        if (( gpu_mem > 10 )); then
            printf "  ✘ GPU actively in use (%d MiB memory). Close GPU apps first.\n" "$gpu_mem" >&2
            _gpu_log "ERROR" "GPU in use: ${gpu_mem} MiB"
            return 1
        fi
    elif [[ "$current_driver" == "vfio-pci" ]]; then
        # Check for QEMU/VM processes
        if pgrep -f 'qemu.*vfio' &>/dev/null; then
            printf "  ✘ GPU in use by a VM. Stop the VM first.\n" >&2
            _gpu_log "ERROR" "GPU in use by VM (qemu)"
            return 1
        fi
    fi
    return 0
}

_gpu_check_display_safety() {
    # Abort if a monitor is connected to the passthrough GPU.
    local pci_addr="$1"
    if _gpu_is_display_gpu "$pci_addr"; then
        printf "  ✘ Monitor connected to GPU at %s — unbinding will cause a blackscreen!\n" "$pci_addr" >&2
        printf "    Move your monitor cable to the iGPU (motherboard) port first.\n" >&2
        _gpu_log "ERROR" "Display connected to passthrough GPU ${pci_addr}"
        return 1
    fi
    return 0
}

# ── State Marker ───────────────────────────────────────────────────────────────

_gpu_update_state_marker() {
    local mode="$1"
    echo "$mode" | sudo -n tee "$_GPU_STATE_MARKER" > /dev/null 2>&1 || true
}

_gpu_read_state_marker() {
    [[ -r "$_GPU_STATE_MARKER" ]] && cat "$_GPU_STATE_MARKER" 2>/dev/null || echo ""
}

# ── Mode System (mirrors omarchy mode vm/host/none) ───────────────────────────

_gpu_mode_get() {
    # Show current GPU mode.
    if ! _gpu_load_config 2>/dev/null; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n"
        return 1
    fi

    local driver mode
    driver=$(_gpu_current_driver "$GPU_PCI_ADDR")
    mode=$(_gpu_detect_mode "$driver")

    printf "GPU:    %s [%s]\n" "${GPU_NAME:-unknown}" "${GPU_PCI_ADDR:-unknown}"
    printf "Driver: %s\n" "${driver:-none}"
    printf "Mode:   %s\n" "$mode"

    _gpu_update_state_marker "$mode"
}

_gpu_mode_vm() {
    # Bind GPU + all IOMMU group devices to vfio-pci (mirrors omarchy cmd_bind).
    local force="${1:-}"

    if ! _gpu_load_config; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n" >&2
        return 1
    fi

    _gpu_ensure_sudo || return 1

    local gpu_pci_full
    gpu_pci_full=$(_gpu_normalize_pci "$GPU_PCI_ADDR") || {
        printf "Invalid GPU PCI address: %s\n" "$GPU_PCI_ADDR" >&2
        return 1
    }

    local current_driver
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")

    _gpu_log "INFO" "=== MODE VM START === GPU: ${GPU_NAME} (${GPU_PCI_ADDR}), driver: ${current_driver:-none}"

    if [[ "$current_driver" == "vfio-pci" ]]; then
        printf "✔ GPU already bound to vfio-pci (ready for VM).\n"
        _gpu_update_state_marker "vm"
        return 0
    fi

    # Multi-GPU safety: refuse runtime nvidia→vfio unbind.
    # The nvidia kernel module shares state between GPUs — unbinding one
    # while the other is rendering deadlocks in the .remove() callback.
    # The correct approach is to reboot with the GPU Passthrough boot entry.
    local _multi_gpu=false
    if _gpu_is_module_loaded nvidia && _gpu_nvidia_used_by_other_gpu; then
        _multi_gpu=true
        if [[ "$force" != "force" ]]; then
            if ! _gpu_booted_vm_mode; then
                printf "✘ Runtime GPU unbind is unsafe in multi-NVIDIA setups.\n" >&2
                printf "  The nvidia driver shares kernel state between GPUs —\n" >&2
                printf "  unbinding one while the other renders causes a system freeze.\n\n" >&2
                if _gpu_has_vm_boot_entry; then
                    printf "  → Reboot and select the \"GPU Passthrough\" boot entry.\n" >&2
                else
                    printf "  → Run 'hyprconf hardware gpu setup' to create boot entries,\n" >&2
                    printf "    then reboot and select the \"GPU Passthrough\" entry.\n" >&2
                fi
                return 1
            fi
        fi
    fi

    # Safety checks
    _gpu_check_processes "$current_driver" || return 1
    if [[ "$force" != "force" ]]; then
        _gpu_check_display_safety "$GPU_PCI_ADDR" || return 1
    fi

    # Unload NVIDIA modules if any are loaded — not just when driver is "nvidia".
    # A previous failed attempt may have unbound the driver but left modules
    # loaded, creating a zombie state where sysfs writes hang indefinitely.
    if _gpu_is_module_loaded nvidia; then
        if [[ "$_multi_gpu" == true ]]; then
            printf "  ℹ NVIDIA driver in use by display GPU — using per-device unbind.\n"
            _gpu_log "INFO" "Multi-GPU: skipping nvidia module unload"
        else
            _gpu_unload_nvidia_modules || return 1
        fi
    fi

    # Unbind VT consoles / EFI framebuffer to release GPU references.
    # In multi-GPU, the consoles and framebuffer belong to the display GPU —
    # unbinding them destabilises the active display.
    if [[ "$_multi_gpu" == false ]]; then
        _gpu_unbind_vtconsoles
    fi

    # NOTE: GPU unbind is handled per-device in the IOMMU loop below.
    # driver_override is set BEFORE unbinding so the kernel knows which
    # driver to use on re-probe.  Doing a standalone unbind here (without
    # driver_override) causes kernel hangs on multi-NVIDIA systems where
    # the nvidia module is shared between the display and passthrough GPUs.

    # Ensure vfio-pci module is loaded
    if ! _gpu_is_module_loaded vfio_pci; then
        if ! sudo -n modprobe vfio-pci 2>/dev/null; then
            printf "  ✘ Failed to load vfio-pci module.\n" >&2
            return 1
        fi
    fi

    # Get all IOMMU group devices
    local iommu_devs
    iommu_devs="${GPU_IOMMU_DEVICES:-}"
    if [[ -z "$iommu_devs" ]]; then
        iommu_devs=$(_gpu_iommu_devices "$GPU_PCI_ADDR" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
    fi
    _gpu_log "INFO" "IOMMU devices: ${iommu_devs}"

    # Register GPU vendor:device with vfio-pci (legacy fallback)
    local vendor_id device_id
    vendor_id="${GPU_VENDOR_DEVICE%%:*}"
    device_id="${GPU_VENDOR_DEVICE##*:}"
    _gpu_sysfs_write "${vendor_id} ${device_id}" "${_GPU_SYSFS}/bus/pci/drivers/vfio-pci/new_id" || true

    # Bind each IOMMU group device to vfio-pci via driver_override + drivers_probe
    local dev_pci dev_pci_full
    for dev_pci in $iommu_devs; do
        dev_pci_full=$(_gpu_normalize_pci "$dev_pci") || continue

        [[ ! -e "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}" ]] && continue

        # Skip PCI bridges (class 0604)
        local dev_class
        dev_class=$(_gpu_get_pci_class "$dev_pci")
        [[ "$dev_class" == "0604" ]] && continue

        # Set driver_override to vfio-pci (tells kernel which driver to use)
        if ! _gpu_sysfs_write "vfio-pci" "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver_override"; then
            _gpu_log "WARN" "$dev_pci: failed to set driver_override"
        fi

        # Unbind from current driver
        if [[ -f "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver/unbind" ]]; then
            _gpu_sysfs_write "$dev_pci_full" "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver/unbind" || true
        fi

        # Probe to bind with the overridden driver
        _gpu_sysfs_write "$dev_pci_full" "${_GPU_SYSFS}/bus/pci/drivers_probe" || true

        _gpu_log "INFO" "Bound $dev_pci to vfio-pci"
    done

    # Verify
    sleep 1
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")
    if [[ "$current_driver" == "vfio-pci" ]]; then
        printf "✔ GPU bound to vfio-pci (ready for VM).\n"
        _gpu_log "SUCCESS" "=== MODE VM SUCCESS ==="
        _gpu_update_state_marker "vm"
        return 0
    else
        printf "✘ Failed to bind GPU (driver: %s).\n" "${current_driver:-none}" >&2
        _gpu_log "ERROR" "=== MODE VM FAILED: driver ${current_driver:-none} ==="
        return 1
    fi
}

_gpu_mode_host() {
    # Unbind from vfio-pci, restore native driver (mirrors omarchy cmd_unbind).

    if ! _gpu_load_config; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n" >&2
        return 1
    fi

    _gpu_ensure_sudo || return 1

    local gpu_pci_full
    gpu_pci_full=$(_gpu_normalize_pci "$GPU_PCI_ADDR") || {
        printf "Invalid GPU PCI address: %s\n" "$GPU_PCI_ADDR" >&2
        return 1
    }

    local current_driver native_driver
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")
    native_driver="${GPU_DRIVER_ORIGINAL:-}"

    # Infer native driver from vendor ID if config is missing it
    if [[ -z "$native_driver" || "$native_driver" == "none" ]]; then
        local vid="${GPU_VENDOR_DEVICE%%:*}"
        case "$vid" in
            10de) native_driver="nvidia" ;;
            1002) native_driver="amdgpu" ;;
            8086) native_driver="i915" ;;
            *) printf "Cannot determine native driver for vendor: %s\n" "$vid" >&2; return 1 ;;
        esac
    fi

    _gpu_log "INFO" "=== MODE HOST START === GPU: ${GPU_NAME} (${GPU_PCI_ADDR}), driver: ${current_driver:-none}, target: ${native_driver}"

    if [[ "$current_driver" == "$native_driver" ]]; then
        printf "✔ GPU already using %s.\n" "$native_driver"
        _gpu_update_state_marker "host"
        return 0
    fi

    # Safety check
    _gpu_check_processes "$current_driver" || return 1

    if [[ "$current_driver" == "vfio-pci" ]]; then
        # Get all IOMMU group devices
        local iommu_devs
        iommu_devs="${GPU_IOMMU_DEVICES:-}"
        if [[ -z "$iommu_devs" ]]; then
            iommu_devs=$(_gpu_iommu_devices "$GPU_PCI_ADDR" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
        fi

        # Unbind all IOMMU group devices from vfio-pci and clear driver_override
        local dev_pci dev_pci_full
        for dev_pci in $iommu_devs; do
            dev_pci_full=$(_gpu_normalize_pci "$dev_pci") || continue
            if [[ -d "${_GPU_SYSFS}/bus/pci/drivers/vfio-pci/${dev_pci_full}" ]]; then
                _gpu_sysfs_write "$dev_pci_full" "${_GPU_SYSFS}/bus/pci/drivers/vfio-pci/unbind" || true
            fi
            # Clear driver_override so the native driver can reclaim
            _gpu_sysfs_write "" "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver_override" || true
        done

        # Remove vfio-pci device IDs
        for dev_pci in $iommu_devs; do
            local dev_ids
            dev_ids=$(_gpu_get_pci_device_id "$dev_pci")
            if [[ -n "$dev_ids" ]]; then
                _gpu_sysfs_write "${dev_ids/:/ }" "${_GPU_SYSFS}/bus/pci/drivers/vfio-pci/remove_id" || true
            fi
        done

        # Rebind USB controllers to xhci_hcd
        if [[ -d "${_GPU_SYSFS}/bus/pci/drivers/xhci_hcd" ]]; then
            for dev_pci in $iommu_devs; do
                dev_pci_full=$(_gpu_normalize_pci "$dev_pci") || continue
                local dev_class
                dev_class=$(_gpu_get_pci_class "$dev_pci")
                if [[ "$dev_class" == "0c03" ]]; then
                    _gpu_sysfs_write "$dev_pci_full" "${_GPU_SYSFS}/bus/pci/drivers/xhci_hcd/bind" || true
                fi
            done
        fi

        _gpu_log "INFO" "All IOMMU devices unbound from vfio-pci"
    fi

    # Load native driver (use -i to bypass blacklist)
    printf "  Loading %s driver...\n" "$native_driver"
    if [[ "$native_driver" == "nvidia" ]]; then
        local mod
        for mod in nvidia nvidia_uvm nvidia_modeset nvidia_drm; do
            sudo -n modprobe -i "$mod" 2>/dev/null || true
        done
    else
        sudo -n modprobe -i "$native_driver" 2>/dev/null || true
    fi

    # Trigger PCI rescan + drivers_probe for reliable rebinding
    _gpu_sysfs_write 1 "${_GPU_SYSFS}/bus/pci/rescan" || true
    _gpu_sysfs_write "$gpu_pci_full" "${_GPU_SYSFS}/bus/pci/drivers_probe" || true

    # Fallback: direct bind if drivers_probe didn't claim the device
    if [[ -d "${_GPU_SYSFS}/bus/pci/drivers/$native_driver" ]] && \
       [[ ! -d "${_GPU_SYSFS}/bus/pci/drivers/$native_driver/$gpu_pci_full" ]]; then
        _gpu_sysfs_write "$gpu_pci_full" "${_GPU_SYSFS}/bus/pci/drivers/$native_driver/bind" || true
    fi

    sleep 2
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")

    if [[ "$current_driver" == "$native_driver" || ( -n "$current_driver" && "$current_driver" != "vfio-pci" ) ]]; then
        printf "✔ GPU restored to %s (available to host).\n" "${current_driver:-$native_driver}"
        _gpu_log "SUCCESS" "=== MODE HOST SUCCESS ==="
        _gpu_update_state_marker "host"

        # Note: with dual boot entries, the VM entry is preserved.
        # The user boots the normal entry next time for full desktop.
        if _gpu_booted_vm_mode; then
            printf "\n  ℹ You booted with the GPU Passthrough entry.\n"
            printf "    Boot the normal entry next time for both GPUs on the host.\n"
        fi

        return 0
    else
        printf "⚠ Unbound but driver not auto-loaded (current: %s).\n" "${current_driver:-none}"
        printf "  Manual reload: sudo modprobe -i %s\n" "$native_driver"
        _gpu_log "WARN" "=== MODE HOST PARTIAL: driver ${current_driver:-none} ==="
        _gpu_update_state_marker "host"
        return 0
    fi
}

_gpu_mode_none() {
    # Unbind GPU from all drivers (mirrors omarchy cmd_set_none).

    if ! _gpu_load_config; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n" >&2
        return 1
    fi

    _gpu_ensure_sudo || return 1

    local gpu_pci_full
    gpu_pci_full=$(_gpu_normalize_pci "$GPU_PCI_ADDR") || {
        printf "Invalid GPU PCI address: %s\n" "$GPU_PCI_ADDR" >&2
        return 1
    }

    local current_driver
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")

    _gpu_log "INFO" "=== MODE NONE START === GPU: ${GPU_NAME} (${GPU_PCI_ADDR}), driver: ${current_driver:-none}"

    if [[ -z "$current_driver" || "$current_driver" == "none" ]]; then
        printf "✔ GPU already in none mode (no driver).\n"
        _gpu_update_state_marker "none"
        return 0
    fi

    _gpu_check_processes "$current_driver" || return 1

    # Unload NVIDIA modules if loaded (even when driver is already "none")
    local _multi_gpu=false
    if _gpu_is_module_loaded nvidia; then
        if _gpu_nvidia_used_by_other_gpu; then
            _multi_gpu=true
            printf "  ℹ NVIDIA driver in use by display GPU — using per-device unbind.\n"
            _gpu_log "INFO" "Multi-GPU: skipping nvidia module unload"
        else
            _gpu_unload_nvidia_modules || return 1
        fi
    fi

    # Unbind VT consoles / EFI framebuffer to release GPU references.
    # In multi-GPU, skip — consoles belong to the display GPU.
    if [[ "$_multi_gpu" == false ]]; then
        _gpu_unbind_vtconsoles
    fi

    # Get all IOMMU group devices
    local iommu_devs
    iommu_devs="${GPU_IOMMU_DEVICES:-}"
    if [[ -z "$iommu_devs" ]]; then
        iommu_devs=$(_gpu_iommu_devices "$GPU_PCI_ADDR" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
    fi

    # Unbind each IOMMU group device and clear driver_override
    local dev_pci dev_pci_full
    for dev_pci in $iommu_devs; do
        dev_pci_full=$(_gpu_normalize_pci "$dev_pci") || continue
        if [[ -f "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver/unbind" ]]; then
            _gpu_sysfs_write "$dev_pci_full" "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver/unbind" || true
        fi
        # Clear driver_override so no driver auto-claims the device
        _gpu_sysfs_write "" "${_GPU_SYSFS}/bus/pci/devices/${dev_pci_full}/driver_override" || true
    done

    # If was vfio-pci, remove device IDs and rebind USB
    if [[ "$current_driver" == "vfio-pci" ]]; then
        for dev_pci in $iommu_devs; do
            local dev_ids
            dev_ids=$(_gpu_get_pci_device_id "$dev_pci")
            if [[ -n "$dev_ids" ]]; then
                _gpu_sysfs_write "${dev_ids/:/ }" "${_GPU_SYSFS}/bus/pci/drivers/vfio-pci/remove_id" || true
            fi
        done
        if [[ -d "${_GPU_SYSFS}/bus/pci/drivers/xhci_hcd" ]]; then
            for dev_pci in $iommu_devs; do
                dev_pci_full=$(_gpu_normalize_pci "$dev_pci") || continue
                local dev_class
                dev_class=$(_gpu_get_pci_class "$dev_pci")
                if [[ "$dev_class" == "0c03" ]]; then
                    _gpu_sysfs_write "$dev_pci_full" "${_GPU_SYSFS}/bus/pci/drivers/xhci_hcd/bind" || true
                fi
            done
        fi
    fi

    sleep 1
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")

    if [[ -z "$current_driver" || "$current_driver" == "none" ]]; then
        printf "✔ GPU set to none mode (no driver loaded).\n"
        _gpu_log "SUCCESS" "=== MODE NONE SUCCESS ==="
        _gpu_update_state_marker "none"
        return 0
    else
        printf "✘ Failed to unbind (current: %s).\n" "$current_driver" >&2
        _gpu_log "ERROR" "=== MODE NONE FAILED: driver ${current_driver} ==="
        return 1
    fi
}

# ── Audit ──────────────────────────────────────────────────────────────────────

_gpu_audit() {
    local errors=0 warnings=0

    printf "GPU Passthrough System Audit\n"
    printf "════════════════════════════\n\n"

    # 1. IOMMU enabled?
    printf "IOMMU\n"
    if grep -qE '(intel_iommu|amd_iommu)=on' /proc/cmdline 2>/dev/null; then
        printf "  ✔ IOMMU enabled in kernel cmdline\n"
    else
        printf "  ✘ IOMMU not enabled in kernel cmdline\n"
        printf "    Add intel_iommu=on iommu=pt (Intel) or amd_iommu=on iommu=pt (AMD)\n"
        errors=$((errors + 1))
    fi

    if grep -q 'iommu=pt' /proc/cmdline 2>/dev/null; then
        printf "  ✔ IOMMU passthrough mode enabled\n"
    else
        printf "  ⚠ iommu=pt not set (recommended for performance)\n"
        warnings=$((warnings + 1))
    fi

    if [[ -d /sys/kernel/iommu_groups ]] && [[ -n "$(ls -A /sys/kernel/iommu_groups 2>/dev/null)" ]]; then
        local grp_count
        grp_count=$(ls -1 /sys/kernel/iommu_groups 2>/dev/null | wc -l)
        printf "  ✔ %d IOMMU groups present\n" "$grp_count"
    else
        printf "  ✘ No IOMMU groups found (BIOS VT-d/AMD-Vi may be disabled)\n"
        errors=$((errors + 1))
    fi

    # 2. Kernel modules
    printf "\nKernel Modules\n"
    local mod
    for mod in vfio vfio_pci vfio_iommu_type1; do
        local mod_underscore="${mod//-/_}"
        if lsmod | grep -q "^${mod_underscore}"; then
            printf "  ✔ %s loaded\n" "$mod"
        elif modinfo "$mod" &>/dev/null; then
            printf "  ⚠ %s available but not loaded (will load on first use)\n" "$mod"
            warnings=$((warnings + 1))
        else
            printf "  ✘ %s not available\n" "$mod"
            errors=$((errors + 1))
        fi
    done

    # 3. Packages
    printf "\nPackages\n"
    local pkg
    for pkg in qemu-desktop edk2-ovmf dmidecode; do
        if pacman -Qi "$pkg" &>/dev/null; then
            printf "  ✔ %s installed\n" "$pkg"
        else
            printf "  ⚠ %s not installed\n" "$pkg"
            warnings=$((warnings + 1))
        fi
    done

    # 4. Driver isolation
    printf "\nDriver Isolation\n"
    if _gpu_has_other_nvidia_gpu 2>/dev/null; then
        # Multi-NVIDIA: check for dual boot entries
        if _gpu_has_vm_boot_entry; then
            printf "  ✔ GPU Passthrough boot entry exists\n"
            if _gpu_booted_vm_mode; then
                local boot_ids
                boot_ids=$(sed -E 's/.*vfio-pci\.ids=([^ ]+).*/\1/' /proc/cmdline 2>/dev/null)
                printf "  ✔ Booted in passthrough mode (vfio-pci.ids=%s)\n" "$boot_ids"
            else
                printf "  ℹ Booted in normal mode (select \"GPU Passthrough\" entry for VM)\n"
            fi
        else
            printf "  ⚠ Multi-NVIDIA detected — no GPU Passthrough boot entry found.\n"
            printf "    Run 'hyprconf hardware gpu setup' to create dual boot entries.\n"
            warnings=$((warnings + 1))
        fi

        # Check mkinitcpio module order
        local mkinit_modules=""
        if [[ -f /etc/mkinitcpio.conf ]]; then
            mkinit_modules=$(grep '^MODULES=' /etc/mkinitcpio.conf 2>/dev/null | head -1)
        fi
        if echo "$mkinit_modules" | grep -qE 'vfio.pci.*nvidia'; then
            printf "  ✔ vfio-pci before nvidia in mkinitcpio MODULES\n"
        elif echo "$mkinit_modules" | grep -q 'nvidia'; then
            printf "  ⚠ nvidia in mkinitcpio MODULES but vfio-pci not before it\n"
            warnings=$((warnings + 1))
        fi

        # Check softdep
        if grep -q 'softdep nvidia pre: vfio-pci' /etc/modprobe.d/vfio.conf 2>/dev/null; then
            printf "  ✔ softdep nvidia pre: vfio-pci configured\n"
        else
            printf "  ⚠ Missing softdep nvidia pre: vfio-pci in /etc/modprobe.d/vfio.conf\n"
            warnings=$((warnings + 1))
        fi

        # Warn if stale blacklist exists (shouldn't with multi-GPU)
        if [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
            printf "  ⚠ Stale driver blacklist found (%s) — not needed for multi-GPU\n" "$_GPU_BLACKLIST_CONF"
            warnings=$((warnings + 1))
        fi
    elif [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
        printf "  ✔ GPU driver blacklist configured (%s)\n" "$_GPU_BLACKLIST_CONF"
    else
        printf "  ⚠ No driver blacklist (GPU loads native driver at boot)\n"
        warnings=$((warnings + 1))
    fi

    # 5. User groups
    printf "\nUser Groups\n"
    local grp
    for grp in kvm; do
        if id -nG "$USER" | grep -qw "$grp"; then
            printf "  ✔ %s in '%s' group\n" "$USER" "$grp"
        else
            printf "  ✘ %s not in '%s' group\n" "$USER" "$grp"
            errors=$((errors + 1))
        fi
    done

    # 6. GPU overview
    printf "\nGPUs\n"
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local pci_addr name driver
        pci_addr=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | sed -E 's/^[0-9a-f:.]+\s+[^:]+:\s+//' | sed -E 's/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]//g' | sed -E 's/\s*\(rev [^)]+\)//')
        driver=$(_gpu_current_driver "$pci_addr" 2>/dev/null)
        printf "  %s: %s (%s)\n" "$pci_addr" "$name" "${driver:-none}"
    done < <(_gpu_list_raw)

    printf "\n"
    if (( errors == 0 && warnings == 0 )); then
        printf "✔ System is ready for GPU passthrough.\n"
    elif (( errors == 0 )); then
        printf "⚠ %d warning(s) — passthrough may work but review above.\n" "$warnings"
    else
        printf "✘ %d error(s), %d warning(s) — fix errors before attempting passthrough.\n" "$errors" "$warnings"
    fi

    return "$errors"
}

# ── Setup Wizard ───────────────────────────────────────────────────────────────

_gpu_setup() {
    printf "GPU Passthrough Setup Wizard\n"
    printf "════════════════════════════\n\n"

    # 1. Detect CPU vendor
    local cpu_vendor iommu_param
    if grep -q "GenuineIntel" /proc/cpuinfo 2>/dev/null; then
        cpu_vendor="intel"
        iommu_param="intel_iommu=on iommu=pt"
    elif grep -q "AuthenticAMD" /proc/cpuinfo 2>/dev/null; then
        cpu_vendor="amd"
        iommu_param="amd_iommu=on iommu=pt"
    else
        printf "⚠ Unknown CPU vendor — cannot determine IOMMU parameter.\n"
        return 1
    fi
    printf "CPU: %s\n" "$cpu_vendor"

    # 2. Check IOMMU kernel params
    if grep -qE '(intel_iommu|amd_iommu)=on' /proc/cmdline 2>/dev/null; then
        printf "✔ IOMMU already enabled in kernel cmdline.\n\n"
    else
        printf "⚠ IOMMU not enabled in kernel cmdline.\n"
        printf "  Required: %s\n\n" "$iommu_param"

        local applied=false

        # Detect bootloader and apply automatically
        if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
            local entries_dir="/boot/loader/entries"
            local entry
            for entry in "$entries_dir"/*.conf; do
                [[ -f "$entry" ]] || continue
                if grep -q "^options " "$entry" 2>/dev/null; then
                    if ! grep -qE '(intel_iommu|amd_iommu)=on' "$entry" 2>/dev/null; then
                        printf "→ Updating systemd-boot entry: %s\n" "$(basename "$entry")"
                        sudo sed -i "s/^options .*/& ${iommu_param}/" "$entry"
                        applied=true
                    fi
                fi
            done

            if [[ "$applied" == "false" ]]; then
                # No .conf entries found — check /etc/kernel/cmdline (used by UKI/mkinitcpio)
                local kernel_cmdline="/etc/kernel/cmdline"
                if [[ -f "$kernel_cmdline" ]]; then
                    if ! grep -qE '(intel_iommu|amd_iommu)=on' "$kernel_cmdline" 2>/dev/null; then
                        printf "→ Updating %s\n" "$kernel_cmdline"
                        sudo sed -i "s/$/ ${iommu_param}/" "$kernel_cmdline"
                        applied=true
                    fi
                else
                    # Create /etc/kernel/cmdline from current cmdline + IOMMU params
                    printf "→ Creating %s from current cmdline\n" "$kernel_cmdline"
                    printf '%s %s\n' "$(cat /proc/cmdline)" "$iommu_param" | sudo tee "$kernel_cmdline" > /dev/null
                    applied=true
                fi

                # Rebuild initramfs if using mkinitcpio (picks up /etc/kernel/cmdline for UKI)
                if command -v mkinitcpio &>/dev/null; then
                    printf "→ Rebuilding initramfs...\n"
                    sudo mkinitcpio -P 2>/dev/null || true
                fi
            fi
        elif [[ -f /etc/default/grub ]]; then
            local grub_default="/etc/default/grub"
            if ! grep -qE '(intel_iommu|amd_iommu)=on' "$grub_default" 2>/dev/null; then
                printf "→ Updating GRUB_CMDLINE_LINUX_DEFAULT in %s\n" "$grub_default"
                sudo sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"/&${iommu_param} /" "$grub_default"
                printf "→ Regenerating GRUB config...\n"
                sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null
                applied=true
            fi
        elif [[ -f /etc/default/limine ]]; then
            local limine_default="/etc/default/limine"
            if ! grep -qE '(intel_iommu|amd_iommu)=on' "$limine_default" 2>/dev/null; then
                printf "→ Updating %s\n" "$limine_default"
                printf 'KERNEL_CMDLINE[default]+=" %s"\n' "$iommu_param" | sudo tee -a "$limine_default" > /dev/null
                if command -v limine-mkinitcpio &>/dev/null; then
                    printf "→ Rebuilding boot entries...\n"
                    sudo limine-mkinitcpio 2>/dev/null || true
                fi
                applied=true
            fi
        fi

        if [[ "$applied" == "true" ]]; then
            printf "\n✔ IOMMU kernel parameters applied.\n"
            printf "  ⚠ A reboot is required for IOMMU to take effect.\n\n"
        else
            printf "\n⚠ Could not auto-apply IOMMU params. Add manually to kernel cmdline:\n"
            printf "  %s\n\n" "$iommu_param"
        fi
    fi

    # 3. VFIO modprobe options (disable_vga + disable_idle_d3)
    local vfio_conf="/etc/modprobe.d/vfio.conf"
    if [[ ! -f "$vfio_conf" ]] || ! grep -q "disable_vga=1" "$vfio_conf" 2>/dev/null; then
        printf "→ Writing VFIO modprobe options: %s\n" "$vfio_conf"
        printf '# VFIO GPU Passthrough — generated by hyprconf\noptions vfio-pci disable_vga=1\noptions vfio-pci disable_idle_d3=1\n' \
            | sudo tee "$vfio_conf" > /dev/null
    else
        printf "✔ VFIO modprobe options already configured.\n"
    fi

    # 4. Install packages via addon
    printf "\nInstalling VFIO packages...\n"
    printf "(This will run: hyprconf addon vfio)\n\n"

    # The actual addon install is handled by the caller (cmd_hardware gpu setup)
    # to avoid circular sourcing. We just signal what's needed.
    printf "__NEED_ADDON_VFIO__\n"

    # 5. Driver blacklisting / boot-time binding is configured AFTER GPU
    # selection (see _gpu_configure_boot_binding called from the CLI dispatch).

    # 6. Detect GPUs and let user choose
    printf "\nDetected GPUs:\n\n"
    _gpu_detect

    printf "Run 'hyprconf hardware gpu mode vm' to bind the GPU to vfio-pci.\n"
    printf "Run 'hyprconf hardware gpu mode host' to restore to host driver.\n"
    printf "Run 'hyprconf hardware gpu audit' to verify system readiness.\n"
}

_gpu_configure_blacklist() {
    # Legacy wrapper — delegates to _gpu_configure_boot_binding.
    _gpu_configure_boot_binding "$@"
}

_gpu_configure_boot_binding() {
    # Configure GPU driver isolation at boot time.
    #
    # Single-NVIDIA + iGPU:  install nvidia /bin/false (blacklist)
    # Multi-NVIDIA:           vfio-pci.ids=VENDOR:DEVICE in kernel cmdline
    #                         + vfio-pci before nvidia in mkinitcpio MODULES
    #                         + softdep nvidia pre: vfio-pci in modprobe.d
    #                         → passthrough GPU claimed by vfio-pci at boot
    local vendor_device="${GPU_VENDOR_DEVICE:-}"

    if [[ -z "$vendor_device" ]]; then
        _gpu_load_config 2>/dev/null || true
        vendor_device="${GPU_VENDOR_DEVICE:-}"
    fi

    if [[ -z "$vendor_device" ]]; then
        printf "  ⚠ No GPU configured — skipping boot binding.\n"
        return 0
    fi

    local vendor_id="${vendor_device%%:*}"
    local device_id="${vendor_device##*:}"

    if [[ "$vendor_id" == "10de" ]]; then
        if _gpu_has_other_nvidia_gpu; then
            # ── Multi-NVIDIA: dual boot entries ───────────────────────
            # Create a separate boot entry with vfio-pci.ids so the user
            # picks "Normal" vs "GPU Passthrough" at the boot menu.
            # This avoids runtime nvidia unbind which freezes multi-GPU.

            # Remove stale blacklist if present from a previous single-GPU config.
            if [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
                sudo rm -f "$_GPU_BLACKLIST_CONF"
                printf "  ✔ Removed stale NVIDIA blacklist (multi-GPU)\n"
            fi

            # Collect passthrough GPU + companion audio device IDs
            local vfio_ids="$vendor_device"
            local audio_ids="${GPU_AUDIO_IDS:-}"
            if [[ -n "$audio_ids" ]]; then
                vfio_ids="${vfio_ids},${audio_ids}"
            fi

            printf "\n→ Configuring dual boot entries (multi-NVIDIA)...\n"
            printf "  Passthrough IDs: %s\n" "$vfio_ids"

            # 1. Clean vfio-pci.ids from normal entries (undo old single-entry approach)
            _gpu_clean_vfio_ids_from_entries

            # 2. Create VM boot entry with vfio-pci.ids
            _gpu_create_vm_boot_entry "$vfio_ids"

            # 3. Ensure vfio-pci loads before nvidia in mkinitcpio
            _gpu_ensure_mkinitcpio_vfio_first

            # 4. Add softdep to modprobe.d (ensures module load order at runtime)
            _gpu_ensure_vfio_softdep

            # 5. Rebuild initramfs
            _gpu_rebuild_initramfs

            printf "  ✔ Dual boot entries configured.\n"
            printf "    Boot \"GPU Passthrough\" entry to use the VM.\n"
            printf "    Boot the normal entry for full desktop.\n"
        else
            # ── Single-NVIDIA + iGPU: blacklist nvidia entirely ───────
            printf "\n→ Configuring NVIDIA driver blacklist...\n"
            sudo tee "$_GPU_BLACKLIST_CONF" > /dev/null <<'EOF'
# GPU Passthrough — prevent NVIDIA auto-load at boot
# Display handled by iGPU, NVIDIA used only for VM passthrough
# Use modprobe -i nvidia to bypass this blacklist (mode host)
install nvidia /bin/false
EOF
            printf "  ✔ NVIDIA blacklist: %s\n" "$_GPU_BLACKLIST_CONF"

            # Remove any stale vfio-pci.ids from cmdline (switching from multi to single)
            _gpu_remove_kernel_param "vfio-pci.ids"

            _gpu_rebuild_initramfs
        fi
    else
        # AMD/Intel: cannot easily blacklist (iGPU may share driver)
        if [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
            sudo rm -f "$_GPU_BLACKLIST_CONF"
        fi
        printf "  ℹ Non-NVIDIA GPU — driver blacklist not needed.\n"
    fi
}

# ── Boot Entry Management (dual entries for GPU passthrough) ───────────────────

readonly _GPU_VM_ENTRY_NAME="hyprconf-vm"

_gpu_create_vm_boot_entry() {
    # Create a separate boot entry for GPU passthrough (VM mode).
    # Duplicates the default entry and adds vfio-pci.ids to the cmdline.
    # This avoids runtime nvidia driver unbind (which freezes multi-GPU systems).
    local vfio_ids="$1"

    if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
        _gpu_create_vm_entry_systemdboot "$vfio_ids"
    elif [[ -f /etc/default/grub ]]; then
        _gpu_create_vm_entry_grub "$vfio_ids"
    else
        printf "  ⚠ Unsupported bootloader — create a VM boot entry manually.\n"
        printf "    Add 'vfio-pci.ids=%s' to the kernel cmdline.\n" "$vfio_ids"
        return 1
    fi
}

_gpu_create_vm_entry_systemdboot() {
    local vfio_ids="$1"
    local entries_dir="/boot/loader/entries"
    local vm_entry="${entries_dir}/${_GPU_VM_ENTRY_NAME}.conf"

    # /boot often has restricted permissions — all reads need sudo
    local source_entry=""
    local default_name
    default_name=$(sudo grep -E '^\s*default\s' /boot/loader/loader.conf 2>/dev/null \
        | awk '{print $2}' | sed 's/\.conf$//' | sed 's/\*//')

    if [[ -n "$default_name" ]]; then
        local candidate
        for candidate in $(sudo ls "${entries_dir}/" 2>/dev/null); do
            [[ "$candidate" == *.conf ]] || continue
            local base="${candidate%.conf}"
            [[ "$base" == "$_GPU_VM_ENTRY_NAME" ]] && continue
            # Match default pattern (default_name is prefix after glob strip)
            [[ "$base" == "${default_name}"* ]] || continue
            source_entry="${entries_dir}/${candidate}"
            break
        done
    fi

    # Fallback: first non-VM entry
    if [[ -z "$source_entry" ]]; then
        local entry
        for entry in $(sudo ls "${entries_dir}/" 2>/dev/null); do
            [[ "$entry" == *.conf ]] || continue
            [[ "${entry%.conf}" == "$_GPU_VM_ENTRY_NAME" ]] && continue
            source_entry="${entries_dir}/${entry}"
            break
        done
    fi

    # UKI fallback: if no type 1 entries, build one from /etc/kernel/cmdline
    if [[ -z "$source_entry" ]]; then
        _gpu_create_vm_entry_from_uki "$vfio_ids"
        return $?
    fi

    printf "  → Creating VM boot entry from: %s\n" "$(basename "$source_entry")"

    sudo cp "$source_entry" "$vm_entry"

    # Set title: replace existing title with a passthrough variant
    local orig_title
    orig_title=$(sudo grep '^title' "$source_entry" 2>/dev/null | sed 's/^title\s*//')
    sudo sed -i "s/^title .*/title ${orig_title} (GPU Passthrough)/" "$vm_entry"

    # Clean any existing vfio-pci.ids then append ours
    sudo sed -i "s/ *vfio-pci\.ids=[^ ]*//" "$vm_entry"
    sudo sed -i "s/^options .*/& vfio-pci.ids=${vfio_ids}/" "$vm_entry"

    printf "  ✔ Boot entries configured.\n"
    printf "    Normal:        %s\n" "$(basename "$source_entry")"
    printf "    Passthrough:   %s\n" "$(basename "$vm_entry")"
    printf "    Select at boot menu to switch GPU modes.\n"
}

_gpu_create_vm_entry_from_uki() {
    # Create a type 1 boot entry when only UKI entries exist.
    # Reads /etc/kernel/cmdline and builds a manual .conf entry.
    local vfio_ids="$1"
    local entries_dir="/boot/loader/entries"
    local vm_entry="${entries_dir}/${_GPU_VM_ENTRY_NAME}.conf"

    local cmdline_file="/etc/kernel/cmdline"
    if [[ ! -f "$cmdline_file" ]]; then
        printf "  ⚠ No boot entries or /etc/kernel/cmdline found.\n"
        return 1
    fi

    local base_cmdline
    base_cmdline=$(cat "$cmdline_file" 2>/dev/null | sed "s/ *vfio-pci\.ids=[^ ]*//")

    # Find the kernel + initrd
    local linux_path="" initrd_path=""
    for kpath in /boot/vmlinuz-linux /boot/vmlinuz-linux-zen /boot/vmlinuz-linux-lts; do
        if [[ -f "$kpath" ]]; then
            linux_path="$kpath"
            initrd_path="${kpath/vmlinuz/initramfs}.img"
            break
        fi
    done

    if [[ -z "$linux_path" ]]; then
        printf "  ⚠ Cannot find kernel image in /boot/.\n"
        return 1
    fi

    printf "  → Creating VM boot entry from UKI: %s\n" "$(basename "$vm_entry")"

    sudo tee "$vm_entry" > /dev/null <<EOF
# Generated by hyprconf — GPU Passthrough boot entry
title   Arch Linux (GPU Passthrough)
linux   ${linux_path}
initrd  ${initrd_path}
options ${base_cmdline} vfio-pci.ids=${vfio_ids}
EOF

    printf "  ✔ VM boot entry created: %s\n" "$(basename "$vm_entry")"
}

_gpu_remove_vm_boot_entry() {
    # Remove the GPU passthrough boot entry.
    if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
        local vm_entry="/boot/loader/entries/${_GPU_VM_ENTRY_NAME}.conf"
        if sudo test -f "$vm_entry"; then
            sudo rm -f "$vm_entry"
            printf "  ✔ Removed VM boot entry.\n"
        fi
    elif [[ -f /etc/default/grub ]]; then
        local grub_custom="/etc/grub.d/99-hyprconf-vm"
        if [[ -f "$grub_custom" ]]; then
            sudo rm -f "$grub_custom"
            sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
            printf "  ✔ Removed GRUB VM menu entry.\n"
        fi
    fi
}

_gpu_clean_vfio_ids_from_entries() {
    # Strip vfio-pci.ids from all non-VM boot entries.
    # Cleans up damage from the old _gpu_set_kernel_param approach that
    # modified ALL entries (making every boot use passthrough mode).
    if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
        local entries_dir="/boot/loader/entries"
        local entry
        for entry in $(sudo ls "${entries_dir}/" 2>/dev/null); do
            [[ "$entry" == *.conf ]] || continue
            [[ "${entry%.conf}" == "$_GPU_VM_ENTRY_NAME" ]] && continue
            if sudo grep -qE 'vfio-pci\.ids=' "${entries_dir}/${entry}" 2>/dev/null; then
                sudo sed -i "s/ *vfio-pci\.ids=[^ ]*//" "${entries_dir}/${entry}"
                printf "  → Cleaned vfio-pci.ids from: %s\n" "$entry"
            fi
        done

        local kernel_cmdline="/etc/kernel/cmdline"
        if [[ -f "$kernel_cmdline" ]] && grep -qE 'vfio-pci\.ids=' "$kernel_cmdline" 2>/dev/null; then
            sudo sed -i "s/ *vfio-pci\.ids=[^ ]*//" "$kernel_cmdline"
            printf "  → Cleaned vfio-pci.ids from: %s\n" "$kernel_cmdline"
        fi
    elif [[ -f /etc/default/grub ]]; then
        if grep -qE 'vfio-pci\.ids=' /etc/default/grub 2>/dev/null; then
            sudo sed -i "s/ *vfio-pci\.ids=[^ \"]*//g" /etc/default/grub
            sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
            printf "  → Cleaned vfio-pci.ids from GRUB config.\n"
        fi
    fi
}

_gpu_create_vm_entry_grub() {
    # Create a GRUB menuentry for GPU passthrough.
    local vfio_ids="$1"
    local grub_custom="/etc/grub.d/99-hyprconf-vm"

    printf "  → Creating GRUB VM menu entry...\n"

    sudo tee "$grub_custom" > /dev/null <<'GRUBEOF'
#!/bin/sh
exec tail -n +3 $0
menuentry "Arch Linux (GPU Passthrough)" --class arch --class gnu-linux {
    search --no-floppy --set=root --fs-uuid $(grub-probe --target=fs_uuid /)
    linux $(ls /boot/vmlinuz-linux* | head -1) root=UUID=$(findmnt -no UUID /) rw VFIO_IDS
    initrd $(ls /boot/initramfs-linux*.img | head -1)
}
GRUBEOF

    # Replace VFIO_IDS placeholder
    sudo sed -i "s|VFIO_IDS|vfio-pci.ids=${vfio_ids}|" "$grub_custom"
    sudo chmod +x "$grub_custom"
    sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true

    printf "  ✔ GRUB VM menu entry created.\n"
}

_gpu_has_vm_boot_entry() {
    # Return 0 if a VM boot entry exists (any bootloader).
    if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
        sudo test -f "/boot/loader/entries/${_GPU_VM_ENTRY_NAME}.conf"
    elif [[ -f /etc/default/grub ]]; then
        [[ -f "/etc/grub.d/99-hyprconf-vm" ]]
    else
        return 1
    fi
}

_gpu_booted_vm_mode() {
    # Return 0 if currently booted with vfio-pci.ids in cmdline (VM entry).
    grep -qE 'vfio-pci\.ids=' /proc/cmdline 2>/dev/null
}

# ── Kernel Command Line Helpers ────────────────────────────────────────────────

_gpu_set_kernel_param() {
    # Add or update a kernel cmdline parameter (key=value).
    # Handles systemd-boot entries, /etc/kernel/cmdline, GRUB, and Limine.
    local key="$1" value="$2"
    local param="${key}=${value}"
    local applied=false

    # Check if already set correctly
    if grep -q "${param}" /proc/cmdline 2>/dev/null; then
        printf "  ✔ %s already in kernel cmdline.\n" "$param"
        return 0
    fi

    # systemd-boot
    if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
        local entries_dir="/boot/loader/entries"
        local entry
        for entry in "$entries_dir"/*.conf; do
            [[ -f "$entry" ]] || continue
            if grep -q "^options " "$entry" 2>/dev/null; then
                # Remove old value if present, then append new one
                if grep -qE "${key}=" "$entry" 2>/dev/null; then
                    sudo sed -i "s/ *${key}=[^ ]*//" "$entry"
                fi
                sudo sed -i "s/^options .*/& ${param}/" "$entry"
                printf "  → Updated systemd-boot: %s\n" "$(basename "$entry")"
                applied=true
            fi
        done

        if [[ "$applied" == "false" ]]; then
            local kernel_cmdline="/etc/kernel/cmdline"
            if [[ -f "$kernel_cmdline" ]]; then
                sudo sed -i "s/ *${key}=[^ ]*//" "$kernel_cmdline"
                sudo sed -i "s/$/ ${param}/" "$kernel_cmdline"
            else
                printf '%s %s\n' "$(cat /proc/cmdline)" "$param" | sudo tee "$kernel_cmdline" > /dev/null
            fi
            printf "  → Updated %s\n" "$kernel_cmdline"
            applied=true
        fi
    elif [[ -f /etc/default/grub ]]; then
        local grub_default="/etc/default/grub"
        sudo sed -i "s/ *${key}=[^ \"]*//g" "$grub_default"
        sudo sed -i "s/^GRUB_CMDLINE_LINUX_DEFAULT=\"/&${param} /" "$grub_default"
        sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null
        printf "  → Updated GRUB: %s\n" "$param"
        applied=true
    elif [[ -f /etc/default/limine ]]; then
        local limine_default="/etc/default/limine"
        printf 'KERNEL_CMDLINE[default]+=" %s"\n' "$param" | sudo tee -a "$limine_default" > /dev/null
        if command -v limine-mkinitcpio &>/dev/null; then
            sudo limine-mkinitcpio 2>/dev/null || true
        fi
        printf "  → Updated Limine: %s\n" "$param"
        applied=true
    fi

    if [[ "$applied" == "false" ]]; then
        printf "  ⚠ Could not auto-apply %s. Add manually to kernel cmdline.\n" "$param"
    fi
}

_gpu_remove_kernel_param() {
    # Remove a kernel cmdline parameter by key prefix.
    local key="$1"

    if command -v bootctl &>/dev/null && sudo bootctl is-installed &>/dev/null 2>&1; then
        local entries_dir="/boot/loader/entries"
        local entry
        for entry in "$entries_dir"/*.conf; do
            [[ -f "$entry" ]] || continue
            if grep -qE "${key}=" "$entry" 2>/dev/null; then
                sudo sed -i "s/ *${key}=[^ ]*//" "$entry"
            fi
        done
        local kernel_cmdline="/etc/kernel/cmdline"
        if [[ -f "$kernel_cmdline" ]] && grep -qE "${key}=" "$kernel_cmdline" 2>/dev/null; then
            sudo sed -i "s/ *${key}=[^ ]*//" "$kernel_cmdline"
        fi
    elif [[ -f /etc/default/grub ]]; then
        sudo sed -i "s/ *${key}=[^ \"]*//g" /etc/default/grub
        sudo grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
    fi
    # Limine: appended lines can't be cleanly removed, but won't cause harm
}

# ── mkinitcpio / initramfs Helpers ─────────────────────────────────────────────

_gpu_ensure_mkinitcpio_vfio_first() {
    # Ensure vfio-pci appears BEFORE nvidia in mkinitcpio MODULES.
    # Module load order in the initramfs determines which driver claims a
    # device first.  vfio-pci + vfio-pci.ids must win the race vs nvidia.
    local mkinitcpio="/etc/mkinitcpio.conf"
    [[ -f "$mkinitcpio" ]] || return 0

    local current_modules
    current_modules=$(grep '^MODULES=' "$mkinitcpio" 2>/dev/null | head -1 | sed 's/MODULES=(\(.*\))/\1/')

    # Already has vfio-pci before nvidia?
    if echo "$current_modules" | grep -qE 'vfio.pci.*nvidia'; then
        printf "  ✔ vfio-pci already before nvidia in mkinitcpio MODULES.\n"
        return 0
    fi

    # Remove any existing vfio-pci/vfio_pci entries
    local cleaned
    cleaned=$(echo "$current_modules" | sed -E 's/\bvfio[-_]pci\b//g' | tr -s ' ' | sed 's/^ //;s/ $//')

    # Prepend vfio-pci before nvidia modules
    local new_modules
    if echo "$cleaned" | grep -q 'nvidia'; then
        new_modules=$(echo "$cleaned" | sed 's/nvidia/vfio-pci nvidia/')
    else
        new_modules="vfio-pci ${cleaned}"
    fi
    # Normalize whitespace
    new_modules=$(echo "$new_modules" | tr -s ' ' | sed 's/^ //;s/ $//')

    printf "  → Updating mkinitcpio MODULES: %s\n" "$new_modules"
    sudo sed -i "s/^MODULES=(.*/MODULES=(${new_modules})/" "$mkinitcpio"
}

_gpu_ensure_vfio_softdep() {
    # Add softdep nvidia pre: vfio-pci to vfio.conf so module-based loading
    # respects the order even outside initramfs (e.g. systemd-modules-load).
    local vfio_conf="/etc/modprobe.d/vfio.conf"
    if [[ -f "$vfio_conf" ]] && grep -q 'softdep nvidia pre: vfio-pci' "$vfio_conf" 2>/dev/null; then
        printf "  ✔ softdep nvidia pre: vfio-pci already in %s.\n" "$vfio_conf"
        return 0
    fi

    printf "  → Adding softdep to %s\n" "$vfio_conf"
    printf 'softdep nvidia pre: vfio-pci\n' | sudo tee -a "$vfio_conf" > /dev/null
}

_gpu_rebuild_initramfs() {
    # Rebuild initramfs to pick up modprobe.d and mkinitcpio changes.
    if command -v mkinitcpio &>/dev/null; then
        printf "  → Rebuilding initramfs...\n"
        sudo mkinitcpio -P 2>/dev/null || {
            printf "  ⚠ mkinitcpio -P failed — rebuild manually: sudo mkinitcpio -P\n"
            return 1
        }
        printf "  ✔ Initramfs rebuilt.\n"
    fi
}

_gpu_setup_select() {
    # Interactive GPU selection — must run in the main shell (not a subshell)
    # so that read works from the terminal.
    local gpu_lines=() gpu_addrs=() gpu_names=() gpu_vdevs=() gpu_drivers=() gpu_iommus=()
    local idx=0

    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        idx=$((idx + 1))

        local pci_addr vendor_device name driver iommu_grp
        pci_addr=$(echo "$line" | awk '{print $1}')
        vendor_device=$(echo "$line" | grep -oP '\[\w{4}:\w{4}\]' | tr -d '[]')
        name=$(echo "$line" | sed -E 's/^[0-9a-f:.]+\s+[^:]+:\s+//' | sed -E 's/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]//g' | sed -E 's/\s*\(rev [^)]+\)//')
        driver=$(_gpu_current_driver "$pci_addr")
        iommu_grp=$(_gpu_iommu_group "$pci_addr")
        gpu_addrs+=("$pci_addr")
        gpu_names+=("$name")
        gpu_vdevs+=("$vendor_device")
        gpu_drivers+=("$driver")
        gpu_iommus+=("$iommu_grp")

        printf "  %d) %s [%s] (driver: %s, IOMMU group: %s)\n" "$idx" "$name" "$pci_addr" "${driver:-none}" "${iommu_grp:-?}"
    done < <(_gpu_list_raw)

    if (( idx == 0 )); then
        printf "No GPUs detected — nothing to configure.\n"
        return 1
    fi

    if (( idx == 1 )); then
        printf "\nOnly one GPU detected — selecting it automatically.\n"
        local sel=0
    else
        printf "\nSelect GPU for passthrough [1-%d]: " "$idx"
        local choice
        read -r choice
        if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > idx )); then
            printf "Invalid selection.\n"
            return 1
        fi
        local sel=$((choice - 1))
    fi

    local sel_addr="${gpu_addrs[$sel]}"
    local sel_name="${gpu_names[$sel]}"
    local sel_vdev="${gpu_vdevs[$sel]}"
    local sel_driver="${gpu_drivers[$sel]}"
    local sel_iommu="${gpu_iommus[$sel]}"

    # Collect IOMMU group devices
    local iommu_devs=""
    if [[ -n "$sel_iommu" ]]; then
        iommu_devs=$(_gpu_iommu_devices "$sel_addr" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')
    fi

    _gpu_save_config "$sel_addr" "$sel_name" "$sel_vdev" "$sel_driver" "$sel_iommu" "$iommu_devs"

    printf "\n✔ GPU configured for passthrough: %s [%s]\n" "$sel_name" "$sel_addr"
    printf "  Config saved to %s\n" "$_GPU_CONF"
}

# ── Config Management ──────────────────────────────────────────────────────────

_gpu_save_config() {
    local pci_addr="$1" name="$2" vendor_device="$3" driver="$4" iommu_group="$5" iommu_devs="$6"

    local vendor_id="${vendor_device%%:*}"
    local device_id="${vendor_device##*:}"

    # Audio device detection
    local audio_info
    audio_info=$(_gpu_audio_device "$pci_addr") || true
    local audio_pci="" audio_ids=""
    if [[ -n "$audio_info" ]]; then
        audio_pci=$(echo "$audio_info" | awk '{print $1}')
        audio_ids=$(echo "$audio_info" | grep -oP '\(\K[^)]+' || true)
    fi

    mkdir -p "$_GPU_CONF_DIR"
    {
        printf '# Generated by hyprconf hardware gpu setup — %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf 'GPU_PCI_ADDR="%s"\n' "$pci_addr"
        printf 'GPU_VENDOR_ID="%s"\n' "$vendor_id"
        printf 'GPU_DEVICE_ID="%s"\n' "$device_id"
        printf 'GPU_NAME="%s"\n' "$name"
        printf 'GPU_VENDOR_DEVICE="%s"\n' "$vendor_device"
        printf 'GPU_DRIVER_ORIGINAL="%s"\n' "$driver"
        printf 'GPU_IOMMU_GROUP="%s"\n' "$iommu_group"
        printf 'GPU_IOMMU_DEVICES="%s"\n' "$iommu_devs"
        printf 'GPU_AUDIO_PCI="%s"\n' "$audio_pci"
        printf 'GPU_AUDIO_IDS="%s"\n' "$audio_ids"
    } > "$_GPU_CONF"

    _gpu_log "INFO" "Config saved: ${_GPU_CONF}"
}

_gpu_load_config() {
    if [[ -f "$_GPU_CONF" ]]; then
        # shellcheck source=/dev/null
        source "$_GPU_CONF"
        return 0
    fi
    return 1
}

# ── Diagnose ───────────────────────────────────────────────────────────────────

_gpu_diagnose() {
    local report="/tmp/hyprconf-gpu-diagnostics-$(date '+%Y%m%d_%H%M%S').txt"

    {
        printf "=== hyprconf GPU Passthrough Diagnostics ===\n"
        printf "Generated: %s\n\n" "$(date)"

        printf "[SYSTEM]\n"
        printf "CPU: %s\n" "$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs)"
        printf "Kernel: %s\n" "$(uname -r)"
        printf "OS: %s\n" "$(grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"
        printf "\n"

        printf "[KERNEL CMDLINE]\n"
        cat /proc/cmdline 2>/dev/null
        printf "\n\n"

        printf "[IOMMU STATUS]\n"
        if [[ -d /sys/kernel/iommu_groups ]]; then
            printf "IOMMU groups: %d\n" "$(ls -1 /sys/kernel/iommu_groups 2>/dev/null | wc -l)"
        else
            printf "No IOMMU groups found\n"
        fi
        printf "\n"

        printf "[IOMMU GROUPS]\n"
        local grp
        for grp in /sys/kernel/iommu_groups/*/devices/*; do
            [[ -e "$grp" ]] || continue
            local dev_addr grp_num
            dev_addr=$(basename "$grp")
            grp_num=$(echo "$grp" | grep -oP 'iommu_groups/\K[0-9]+')
            local desc
            desc=$(lspci -nns "$dev_addr" 2>/dev/null || echo "unknown")
            printf "Group %s: %s\n" "$grp_num" "$desc"
        done
        printf "\n"

        printf "[GPU INFORMATION]\n"
        _gpu_list_raw
        printf "\n"

        printf "[GPU DRIVERS]\n"
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            local pci_addr driver
            pci_addr=$(echo "$line" | awk '{print $1}')
            driver=$(_gpu_current_driver "$pci_addr")
            printf "%s: %s\n" "$pci_addr" "$driver"
        done < <(_gpu_list_raw)
        printf "\n"

        printf "[LOADED VFIO MODULES]\n"
        lsmod | grep -i vfio 2>/dev/null || printf "None\n"
        printf "\n"

        printf "[LOADED GPU MODULES]\n"
        lsmod | grep -iE '(nvidia|nouveau|amdgpu|radeon|i915)' 2>/dev/null || printf "None\n"
        printf "\n"

        printf "[DRIVER BLACKLIST]\n"
        if [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
            cat "$_GPU_BLACKLIST_CONF"
        else
            printf "No blacklist configured\n"
        fi
        printf "\n"

        printf "[DMESG — IOMMU]\n"
        dmesg 2>/dev/null | grep -i iommu | tail -20 || printf "Cannot read dmesg\n"
        printf "\n"

        printf "[DMESG — VFIO]\n"
        dmesg 2>/dev/null | grep -i vfio | tail -20 || printf "Cannot read dmesg\n"
        printf "\n"

        if [[ -f "$_GPU_CONF" ]]; then
            printf "[HYPRCONF GPU CONFIG]\n"
            cat "$_GPU_CONF"
            printf "\n"
        fi

    } > "$report" 2>&1

    cat "$report"
    printf "\n✔ Report saved: %s\n" "$report"
}

# ── Hardware Report ────────────────────────────────────────────────────────────

_gpu_report() {
    printf "GPU Passthrough — Hardware Report\n"
    printf "═════════════════════════════════\n\n"

    # SYSTEM
    printf "[SYSTEM]\n"
    printf "  CPU:     %s\n" "$(grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs)"
    printf "  Kernel:  %s\n" "$(uname -r)"
    printf "  OS:      %s\n" "$(grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"

    local mem_total
    mem_total=$(awk '/MemTotal/ {printf "%.1f GB", $2/1024/1024}' /proc/meminfo 2>/dev/null)
    printf "  RAM:     %s\n\n" "${mem_total:-unknown}"

    # MOTHERBOARD
    printf "[MOTHERBOARD]\n"
    local smbios
    smbios=$(_gpu_host_smbios 2>/dev/null) || true
    if [[ -n "$smbios" ]]; then
        local mfg product serial
        IFS=$'\t' read -r mfg product serial <<< "$smbios"
        printf "  Vendor:  %s\n" "${mfg:-unknown}"
        printf "  Model:   %s\n" "${product:-unknown}"
        printf "  Serial:  %s\n\n" "${serial:-unknown}"
    else
        printf "  (dmidecode unavailable)\n\n"
    fi

    # GPUs
    printf "[GPUs]\n"
    local gpu_idx=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        gpu_idx=$((gpu_idx + 1))

        local pci_addr vendor_device name driver type iommu_grp
        pci_addr=$(echo "$line" | awk '{print $1}')
        vendor_device=$(echo "$line" | grep -oP '\[\w{4}:\w{4}\]' | tr -d '[]')
        name=$(echo "$line" | sed -E 's/^[0-9a-f:.]+\s+[^:]+:\s+//' | sed -E 's/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]//g' | sed -E 's/\s*\(rev [^)]+\)//')
        driver=$(_gpu_current_driver "$pci_addr")
        type=$(_gpu_classify "$pci_addr" "$name")
        iommu_grp=$(_gpu_iommu_group "$pci_addr")
        printf "  GPU %d: %s\n" "$gpu_idx" "$name"
        printf "    PCI:        %s\n" "$pci_addr"
        printf "    IDs:        %s\n" "$vendor_device"
        printf "    Type:       %s\n" "$type"
        printf "    Driver:     %s\n" "${driver:-none}"
        printf "    IOMMU:      group %s\n" "${iommu_grp:-unknown}"

        local audio_info
        audio_info=$(_gpu_audio_device "$pci_addr")
        if [[ -n "$audio_info" ]]; then
            printf "    Audio:      %s\n" "$audio_info"
        fi

        # DRM card + display connectors
        local full_addr="0000:${pci_addr}"
        local drm_dir="/sys/bus/pci/devices/${full_addr}/drm"
        if [[ -d "$drm_dir" ]]; then
            local card
            for card in "$drm_dir"/card*; do
                [[ -d "$card" ]] || continue
                printf "    DRM:        %s\n" "$(basename "$card")"
            done
        fi

        # vRAM (NVIDIA via nvidia-smi, fallback to sysfs)
        local vram=""
        if command -v nvidia-smi &>/dev/null && [[ "$driver" == "nvidia" ]]; then
            vram=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i "$pci_addr" 2>/dev/null | head -1 || true)
            [[ -n "$vram" ]] && vram="${vram} MiB"
        fi
        if [[ -z "$vram" ]] && [[ -f "/sys/bus/pci/devices/${full_addr}/mem_info_vram_total" ]]; then
            local vram_bytes
            vram_bytes=$(cat "/sys/bus/pci/devices/${full_addr}/mem_info_vram_total" 2>/dev/null)
            if [[ -n "$vram_bytes" ]] && (( vram_bytes > 0 )); then
                vram="$(( vram_bytes / 1024 / 1024 )) MiB"
            fi
        fi
        [[ -n "$vram" ]] && printf "    VRAM:       %s\n" "$vram"

        printf "\n"
    done < <(_gpu_list_raw)

    if (( gpu_idx == 0 )); then
        printf "  No GPUs detected.\n\n"
    fi

    # IOMMU GROUPS (only for groups containing GPUs)
    printf "[IOMMU GROUPS]\n"
    local seen_groups=()
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local pci_addr iommu_grp
        pci_addr=$(echo "$line" | awk '{print $1}')
        iommu_grp=$(_gpu_iommu_group "$pci_addr")
        [[ -z "$iommu_grp" ]] && continue

        # Skip already-printed groups
        local already=false
        local g; for g in "${seen_groups[@]:-}"; do
            [[ "$g" == "$iommu_grp" ]] && already=true
        done
        $already && continue
        seen_groups+=("$iommu_grp")

        printf "  Group %s:\n" "$iommu_grp"
        local devs
        devs=$(_gpu_iommu_devices "$pci_addr") || true
        local dev
        while IFS= read -r dev; do
            [[ -z "$dev" ]] && continue
            local desc
            desc=$(lspci -nn 2>/dev/null | grep "^${dev} " | sed 's/^[0-9a-f:.]* //' || true)
            printf "    %s: %s\n" "$dev" "${desc:-unknown}"
        done <<< "$devs"
        printf "\n"
    done < <(_gpu_list_raw)

    # DISPLAY
    printf "[DISPLAY]\n"
    printf "  Session:     %s\n" "${XDG_SESSION_TYPE:-unknown}"
    printf "  Compositor:  %s\n\n" "${XDG_CURRENT_DESKTOP:-unknown}"

    # DRIVER VERSIONS
    printf "[DRIVER VERSIONS]\n"
    if command -v nvidia-smi &>/dev/null; then
        local nv_ver
        nv_ver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || true)
        printf "  nvidia:  %s\n" "${nv_ver:-not loaded}"
    fi
    if lsmod 2>/dev/null | grep -q amdgpu; then
        printf "  amdgpu:  loaded\n"
    fi
    if lsmod 2>/dev/null | grep -q vfio_pci; then
        printf "  vfio:    loaded\n"
    else
        printf "  vfio:    not loaded\n"
    fi
    printf "\n"

    # PASSTHROUGH STATUS
    printf "[PASSTHROUGH STATUS]\n"
    if [[ -f "$_GPU_CONF" ]]; then
        _gpu_load_config
        printf "  Configured:  %s [%s]\n" "${GPU_NAME:-unknown}" "${GPU_PCI_ADDR:-unknown}"
        if [[ -n "${GPU_PCI_ADDR:-}" ]]; then
            local cfg_driver mode
            cfg_driver=$(_gpu_current_driver "$GPU_PCI_ADDR")
            mode=$(_gpu_detect_mode "$cfg_driver")
            printf "  Mode:        %s (%s)\n" "$mode" "$cfg_driver"
        fi
    else
        printf "  Configured:  none (run: hyprconf hardware gpu setup)\n"
    fi

    # Blacklist status
    printf "\n[DRIVER BLACKLIST]\n"
    if [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
        printf "  Status:      active\n"
        printf "  File:        %s\n" "$_GPU_BLACKLIST_CONF"
    else
        printf "  Status:      not configured\n"
    fi
}

# ── SMBIOS (sysfs-based, no dmidecode dependency) ─────────────────────────────

_gpu_host_smbios() {
    # Read host SMBIOS system info via sysfs (no root needed).
    # Returns manufacturer, product, serial as tab-separated values.
    local dmi="/sys/devices/virtual/dmi/id"
    local mfg="" product="" serial=""

    [[ -r "$dmi/sys_vendor" ]] && mfg=$(cat "$dmi/sys_vendor" 2>/dev/null)
    [[ -r "$dmi/product_name" ]] && product=$(cat "$dmi/product_name" 2>/dev/null)
    [[ -r "$dmi/product_serial" ]] && serial=$(cat "$dmi/product_serial" 2>/dev/null)

    # Fallback to dmidecode if sysfs is empty
    if [[ -z "$mfg" ]] && command -v dmidecode &>/dev/null; then
        mfg=$(sudo -n dmidecode -s system-manufacturer 2>/dev/null | head -1 || true)
        product=$(sudo -n dmidecode -s system-product-name 2>/dev/null | head -1 || true)
        serial=$(sudo -n dmidecode -s system-serial-number 2>/dev/null | head -1 || true)
    fi

    printf '%s\t%s\t%s\n' "$mfg" "$product" "$serial"
}

_gpu_vm_smbios_sanitize() {
    # Replace spaces with underscores and escape commas with QEMU's double-comma
    # convention so the value survives Dockurr's unquoted $ARGS expansion.
    local v="$1"
    v="${v// /_}"
    v="${v//,/,,}"
    printf '%s' "$v"
}

_gpu_vm_smbios_args() {
    # Generate QEMU -smbios args from host hardware identity.
    # Passes real BIOS (type 0), system (type 1), and processor (type 4) info
    # so the guest sees genuine manufacturer/product strings instead of
    # "QEMU Standard PC".  Prevents anti-cheat (EAC, VAC, …) VM detection.
    local dmi="/sys/devices/virtual/dmi/id"
    local args=""

    # ── Type 0 — BIOS ──────────────────────────────────────────────────────
    local bios_vendor="" bios_version="" bios_date=""
    [[ -r "$dmi/bios_vendor" ]]  && bios_vendor=$(cat "$dmi/bios_vendor" 2>/dev/null)
    [[ -r "$dmi/bios_version" ]] && bios_version=$(cat "$dmi/bios_version" 2>/dev/null)
    [[ -r "$dmi/bios_date" ]]    && bios_date=$(cat "$dmi/bios_date" 2>/dev/null)
    if [[ -n "$bios_vendor" ]]; then
        args+="-smbios type=0"
        args+=",vendor=$(_gpu_vm_smbios_sanitize "$bios_vendor")"
        [[ -n "$bios_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$bios_version")"
        [[ -n "$bios_date" ]]    && args+=",date=$(_gpu_vm_smbios_sanitize "$bios_date")"
        args+=",uefi=on"
    fi

    # ── Type 1 — System ────────────────────────────────────────────────────
    local sys_vendor="" product_name="" product_version=""
    local product_serial="" product_uuid="" product_family=""
    [[ -r "$dmi/sys_vendor" ]]       && sys_vendor=$(cat "$dmi/sys_vendor" 2>/dev/null)
    [[ -r "$dmi/product_name" ]]     && product_name=$(cat "$dmi/product_name" 2>/dev/null)
    [[ -r "$dmi/product_version" ]]  && product_version=$(cat "$dmi/product_version" 2>/dev/null)
    [[ -r "$dmi/product_serial" ]]   && product_serial=$(cat "$dmi/product_serial" 2>/dev/null)
    [[ -r "$dmi/product_uuid" ]]     && product_uuid=$(cat "$dmi/product_uuid" 2>/dev/null)
    [[ -r "$dmi/product_family" ]]   && product_family=$(cat "$dmi/product_family" 2>/dev/null)
    if [[ -n "$sys_vendor" ]]; then
        args+=" -smbios type=1"
        args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$sys_vendor")"
        [[ -n "$product_name" ]]    && args+=",product=$(_gpu_vm_smbios_sanitize "$product_name")"
        [[ -n "$product_version" ]] && args+=",version=$(_gpu_vm_smbios_sanitize "$product_version")"
        [[ -n "$product_serial" ]]  && args+=",serial=$(_gpu_vm_smbios_sanitize "$product_serial")"
        # UUID: only pass if valid format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
        if [[ "$product_uuid" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]; then
            args+=",uuid=$product_uuid"
        fi
        [[ -n "$product_family" ]]  && args+=",family=$(_gpu_vm_smbios_sanitize "$product_family")"
    fi

    # ── Type 4 — Processor ─────────────────────────────────────────────────
    local cpu_mfg="" cpu_ver="" cpu_cur_speed="" cpu_max_speed=""
    if command -v dmidecode &>/dev/null; then
        cpu_mfg=$(sudo -n dmidecode -t processor 2>/dev/null \
            | grep -m1 'Manufacturer:' | sed 's/.*Manufacturer:[[:space:]]*//' || true)
        cpu_ver=$(sudo -n dmidecode -t processor 2>/dev/null \
            | grep -m1 'Version:' | sed 's/.*Version:[[:space:]]*//' || true)
        cpu_cur_speed=$(sudo -n dmidecode -t processor 2>/dev/null \
            | grep -m1 'Current Speed:' | grep -oP '\d+' | head -1 || true)
        cpu_max_speed=$(sudo -n dmidecode -t processor 2>/dev/null \
            | grep -m1 'Max Speed:' | grep -oP '\d+' | head -1 || true)
    fi
    # Fallback to /proc/cpuinfo
    [[ -z "$cpu_mfg" ]] && cpu_mfg=$(grep -m1 'vendor_id' /proc/cpuinfo 2>/dev/null \
        | awk -F': ' '{print $2}' || true)
    [[ -z "$cpu_ver" ]] && cpu_ver=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null \
        | awk -F': ' '{print $2}' || true)
    if [[ -n "$cpu_mfg" ]] && [[ -n "$cpu_ver" ]]; then
        args+=" -smbios type=4"
        args+=",manufacturer=$(_gpu_vm_smbios_sanitize "$cpu_mfg")"
        args+=",version=$(_gpu_vm_smbios_sanitize "$cpu_ver")"
        [[ -n "$cpu_cur_speed" ]] && args+=",current-speed=${cpu_cur_speed}"
        [[ -n "$cpu_max_speed" ]] && args+=",max-speed=${cpu_max_speed}"
    fi

    args="${args# }"  # trim leading space
    printf '%s' "$args"
}

_gpu_vm_cpu_flags() {
    # Generate CPU_FLAGS for anti-detection: hides hypervisor CPUID bit,
    # sets Hyper-V vendor ID to real CPU vendor, passes host CPU identity.
    # Returned value is set as the CPU_FLAGS Docker env var; Dockurr appends
    # it after its own CPU features, so our -hypervisor overrides +hypervisor.
    local vendor flags=""
    vendor=$(grep -m1 'vendor_id' /proc/cpuinfo 2>/dev/null | awk -F': ' '{print $2}')
    [[ -z "$vendor" ]] && return 0

    flags="-hypervisor,hv_vendor_id=${vendor}"

    local family model stepping
    family=$(grep -m1 '^cpu family[[:space:]]*:' /proc/cpuinfo 2>/dev/null | awk -F': ' '{print $2}')
    model=$(grep -m1 '^model[[:space:]]*:' /proc/cpuinfo 2>/dev/null | awk -F': ' '{print $2}')
    stepping=$(grep -m1 '^stepping[[:space:]]*:' /proc/cpuinfo 2>/dev/null | awk -F': ' '{print $2}')
    [[ "$family" =~ ^[0-9]+$ ]]   && flags+=",family=${family}"
    [[ "$model" =~ ^[0-9]+$ ]]    && flags+=",model=${model}"
    [[ "$stepping" =~ ^[0-9]+$ ]] && flags+=",stepping=${stepping}"

    printf '%s' "$flags"
}

_gpu_vm_disk_flags() {
    # Generate -global ide-hd.* args to spoof SATA disk identity.
    # With DISK_TYPE=sata, Dockurr uses ich9-ahci + ide-hd (not scsi-hd).
    # Without these, Windows sees "QEMU HARDDISK" — a major VM fingerprint.
    local disk_model="" disk_serial="" flags=""

    # Try NVMe first, fall back to SATA/SAS
    disk_model=$(lsblk -ndo MODEL /dev/nvme0n1 2>/dev/null | xargs)
    disk_serial=$(lsblk -ndo SERIAL /dev/nvme0n1 2>/dev/null | xargs)
    if [[ -z "$disk_model" ]]; then
        disk_model=$(lsblk -ndo MODEL /dev/sda 2>/dev/null | xargs)
        disk_serial=$(lsblk -ndo SERIAL /dev/sda 2>/dev/null | xargs)
    fi

    if [[ -n "$disk_model" ]]; then
        flags+="-global ide-hd.model=$(_gpu_vm_smbios_sanitize "$disk_model")"
        [[ -n "$disk_serial" ]] && flags+=" -global ide-hd.serial=$(_gpu_vm_smbios_sanitize "$disk_serial")"
        # Also spoof the CD-ROM to hide "QEMU DVD-ROM"
        flags+=" -global ide-cd.model=ATAPI_DVD_RW"
    fi

    printf '%s' "$flags"
}

# ── Status (default view) ─────────────────────────────────────────────────────

_gpu_status() {
    local gpu_count=0

    printf "GPU Passthrough Status\n"
    printf "══════════════════════\n\n"

    # IOMMU status
    if grep -qE '(intel_iommu|amd_iommu)=on' /proc/cmdline 2>/dev/null; then
        printf "IOMMU: enabled ✔\n"
    else
        printf "IOMMU: not enabled ✘\n"
    fi

    # Blacklist status
    if [[ -f "$_GPU_BLACKLIST_CONF" ]]; then
        printf "Blacklist: active ✔\n"
    else
        printf "Blacklist: not configured\n"
    fi

    # Configured GPU mode
    if [[ -f "$_GPU_CONF" ]]; then
        _gpu_load_config
        local cfg_driver mode
        cfg_driver=$(_gpu_current_driver "$GPU_PCI_ADDR")
        mode=$(_gpu_detect_mode "$cfg_driver")
        printf "Mode: %s\n" "$mode"
    fi

    printf "\nGPUs:\n"
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        gpu_count=$((gpu_count + 1))

        local pci_addr name driver status_icon
        pci_addr=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | sed -E 's/^[0-9a-f:.]+\s+[^:]+:\s+//' | sed -E 's/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]//g' | sed -E 's/\s*\(rev [^)]+\)//')
        driver=$(_gpu_current_driver "$pci_addr")
        if [[ "$driver" == "vfio-pci" ]]; then
            status_icon="🔒 vm (vfio-pci)"
        elif [[ "$driver" == "none" ]]; then
            status_icon="⚪ none"
        else
            status_icon="🖥  host (${driver})"
        fi

        printf "  %-6s  %-55s %s\n" "$pci_addr" "$name" "$status_icon"
    done < <(_gpu_list_raw)

    if (( gpu_count == 0 )); then
        printf "  No GPUs detected.\n"
    fi

    # Show configured GPU (if any)
    if [[ -f "$_GPU_CONF" ]]; then
        _gpu_load_config
        printf "\nConfigured GPU: %s [%s]\n" "${GPU_NAME:-unknown}" "${GPU_PCI_ADDR:-unknown}"
    fi
}

# ── Windows VM Management ──────────────────────────────────────────────────────

readonly _GPU_VM_CONF="${_GPU_CONF_DIR}/gpu-vm.conf"
readonly _GPU_VM_COMPOSE="${_GPU_CONF_DIR}/gpu-vm.yml"
readonly _GPU_VM_CONTAINER="hyprconf-windows"
readonly _GPU_VM_STORAGE_DIR="${HOME}/.local/share/hyprconf/windows-vm"
readonly _GPU_VM_SHARED_DIR="${HOME}/Windows"
readonly _GPU_VM_OEM_DIR="${HOME}/.local/share/hyprconf/windows-vm-oem"
readonly _GPU_VM_USB_CONF="${_GPU_CONF_DIR}/gpu-vm-usb.conf"
readonly _GPU_VM_QEMU_MONITOR="/run/qemu.monitor"
_GPU_VM_KVMFR_DEV="/dev/kvmfr0"

_gpu_vm_spice_dir() {
    printf '%s' "${XDG_RUNTIME_DIR:-/tmp}/hyprconf-spice"
}

_gpu_vm_freerdp_bin() {
    # FreeRDP v3 renamed the binary to xfreerdp3
    if command -v xfreerdp3 &>/dev/null; then
        printf 'xfreerdp3'
    elif command -v xfreerdp &>/dev/null; then
        printf 'xfreerdp'
    else
        return 1
    fi
}

# ── USB Passthrough ────────────────────────────────────────────────────────────

_gpu_vm_usb_load() {
    # Load saved USB devices from config. Sets _GPU_VM_USB_DEVICES array.
    _GPU_VM_USB_DEVICES=()
    [[ -f "$_GPU_VM_USB_CONF" ]] || return 0
    local line
    while IFS= read -r line; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        _GPU_VM_USB_DEVICES+=("$line")
    done < "$_GPU_VM_USB_CONF"
}

_gpu_vm_usb_save() {
    # Persist _GPU_VM_USB_DEVICES array to config file.
    mkdir -p "$_GPU_CONF_DIR"
    {
        printf "# USB devices for VM passthrough — managed by hyprconf\n"
        printf "# Format: vendor_id:product_id  description\n"
        local entry
        for entry in "${_GPU_VM_USB_DEVICES[@]}"; do
            printf "%s\n" "$entry"
        done
    } > "$_GPU_VM_USB_CONF"
}

_gpu_vm_usb_list_host() {
    # List USB devices on the host (excludes root hubs).
    # Output: one line per device — "VID:PID  description"
    if ! command -v lsusb &>/dev/null; then
        printf "lsusb not found. Install: sudo pacman -S usbutils\n" >&2
        return 1
    fi
    lsusb 2>/dev/null | grep -v 'root hub' | while IFS= read -r line; do
        local vid_pid name
        vid_pid=$(echo "$line" | grep -oP 'ID \K[0-9a-f]{4}:[0-9a-f]{4}')
        name=$(echo "$line" | sed -E 's/^Bus [0-9]+ Device [0-9]+: ID [0-9a-f:]+\s*//')
        [[ -z "$vid_pid" ]] && continue
        printf "%s  %s\n" "$vid_pid" "$name"
    done | sort -u
}

_gpu_vm_usb() {
    # Show available USB devices and currently saved ones.
    printf "── Host USB Devices ──\n"
    local idx=0 devs=()
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        idx=$((idx + 1))
        devs+=("$line")
        printf "  %2d) %s\n" "$idx" "$line"
    done < <(_gpu_vm_usb_list_host)

    if (( idx == 0 )); then
        printf "  No USB devices found.\n"
    fi

    _gpu_vm_usb_load
    if (( ${#_GPU_VM_USB_DEVICES[@]} > 0 )); then
        printf "\n── Saved for VM ──\n"
        local entry
        for entry in "${_GPU_VM_USB_DEVICES[@]}"; do
            printf "  • %s\n" "$entry"
        done
    else
        printf "\n  No USB devices saved for VM.\n"
    fi
    printf "\n  Add:    hyprconf hardware gpu vm usb add\n"
    printf "  Remove: hyprconf hardware gpu vm usb remove\n"
}

_gpu_vm_usb_add() {
    # Interactive picker to add USB device(s) for VM passthrough.
    # If the VM is running, hot-adds immediately via QEMU monitor.
    local devs=() idx=0
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        idx=$((idx + 1))
        devs+=("$line")
        printf "  %2d) %s\n" "$idx" "$line"
    done < <(_gpu_vm_usb_list_host)

    if (( idx == 0 )); then
        printf "No USB devices found.\n"
        return 1
    fi

    printf "\nSelect device(s) to add (e.g. 1 3 5 or 1,3,5): "
    read -r selection
    selection="${selection//,/ }"

    _gpu_vm_usb_load
    local added=0 num vid_pid dev_line
    for num in $selection; do
        if [[ ! "$num" =~ ^[0-9]+$ ]] || (( num < 1 || num > idx )); then
            printf "  ⚠ Invalid selection: %s\n" "$num"
            continue
        fi
        dev_line="${devs[$((num - 1))]}"
        vid_pid="${dev_line%% *}"

        # Skip if already saved
        local existing
        for existing in "${_GPU_VM_USB_DEVICES[@]}"; do
            [[ "${existing%% *}" == "$vid_pid" ]] && { printf "  ℹ %s already saved.\n" "$vid_pid"; continue 2; }
        done

        _GPU_VM_USB_DEVICES+=("$dev_line")
        added=$((added + 1))
        printf "  ✔ Added %s\n" "$dev_line"

        # Hot-add if VM is running
        if _gpu_vm_is_running; then
            _gpu_vm_usb_hotplug "add" "$vid_pid"
        fi
    done

    if (( added > 0 )); then
        _gpu_vm_usb_save
        printf "\n✔ %d device(s) saved.\n" "$added"
        if ! _gpu_vm_is_running; then
            printf "  Devices will be passed on next VM launch.\n"
        fi
    fi
}

_gpu_vm_usb_remove() {
    # Interactive picker to remove saved USB device(s) from VM passthrough.
    _gpu_vm_usb_load
    if (( ${#_GPU_VM_USB_DEVICES[@]} == 0 )); then
        printf "No USB devices saved for VM.\n"
        return 0
    fi

    printf "── Saved USB Devices ──\n"
    local idx=0 entry
    for entry in "${_GPU_VM_USB_DEVICES[@]}"; do
        idx=$((idx + 1))
        printf "  %2d) %s\n" "$idx" "$entry"
    done

    printf "\nSelect device(s) to remove (e.g. 1 3 or 1,3): "
    read -r selection
    selection="${selection//,/ }"

    local removed=0 keep=() num
    for (( i=0; i<${#_GPU_VM_USB_DEVICES[@]}; i++ )); do
        local should_remove=false
        for num in $selection; do
            if [[ "$num" =~ ^[0-9]+$ ]] && (( num == i + 1 )); then
                should_remove=true
                break
            fi
        done
        if [[ "$should_remove" == "true" ]]; then
            local vid_pid="${_GPU_VM_USB_DEVICES[$i]%% *}"
            printf "  ✔ Removed %s\n" "${_GPU_VM_USB_DEVICES[$i]}"
            removed=$((removed + 1))
            # Hot-remove if VM is running
            if _gpu_vm_is_running; then
                _gpu_vm_usb_hotplug "del" "$vid_pid"
            fi
        else
            keep+=("${_GPU_VM_USB_DEVICES[$i]}")
        fi
    done

    _GPU_VM_USB_DEVICES=("${keep[@]+"${keep[@]}"}")
    _gpu_vm_usb_save
    printf "\n✔ %d device(s) removed.\n" "$removed"
}

_gpu_vm_is_running() {
    # Return 0 if the VM container is running.
    local status
    status=$(docker inspect --format='{{.State.Status}}' "$_GPU_VM_CONTAINER" 2>/dev/null || echo "")
    [[ "$status" == "running" ]]
}

_gpu_vm_usb_hotplug() {
    # Hot-add or hot-remove a USB device via the QEMU monitor socket.
    # Usage: _gpu_vm_usb_hotplug add|del vendor_id:product_id
    local action="$1" vid_pid="$2"
    local vid="${vid_pid%%:*}" pid="${vid_pid##*:}"
    local dev_id="usb-${vid}-${pid}"

    local monitor_cmd
    if [[ "$action" == "add" ]]; then
        monitor_cmd="device_add usb-host,vendorid=0x${vid},productid=0x${pid},id=${dev_id}"
    else
        monitor_cmd="device_del ${dev_id}"
    fi

    printf "  → Hot-%s %s to VM...\n" "$action" "$vid_pid"
    local result
    if result=$(docker exec "$_GPU_VM_CONTAINER" bash -c \
        "echo '${monitor_cmd}' | socat - UNIX-CONNECT:${_GPU_VM_QEMU_MONITOR}" 2>&1); then
        printf "  ✔ USB %s hot-%s successful.\n" "$vid_pid" "${action/del/remove}d"
        _gpu_log "INFO" "USB hot-${action}: ${vid_pid} (${monitor_cmd})"
    else
        # Fallback: try writing directly if socat unavailable
        if docker exec "$_GPU_VM_CONTAINER" bash -c \
            "printf '%s\n' '${monitor_cmd}' > ${_GPU_VM_QEMU_MONITOR}" 2>/dev/null; then
            printf "  ✔ USB %s hot-%s successful.\n" "$vid_pid" "${action/del/remove}d"
            _gpu_log "INFO" "USB hot-${action} (direct): ${vid_pid}"
        else
            printf "  ⚠ Hot-%s failed. Device will be applied on next VM restart.\n" "$action" >&2
            _gpu_log "WARN" "USB hot-${action} failed: ${vid_pid}: ${result}"
        fi
    fi
}

_gpu_vm_usb_qemu_args() {
    # Output QEMU -device args for all saved USB devices.
    _gpu_vm_usb_load
    local entry vid_pid vid pid
    for entry in "${_GPU_VM_USB_DEVICES[@]}"; do
        vid_pid="${entry%% *}"
        vid="${vid_pid%%:*}"
        pid="${vid_pid##*:}"
        printf " -device usb-host,vendorid=0x%s,productid=0x%s,id=usb-%s-%s" "$vid" "$pid" "$vid" "$pid"
    done
}

# ── VM Config ──────────────────────────────────────────────────────────────────

_gpu_vm_load_config() {
    if [[ -f "$_GPU_VM_CONF" ]]; then
        # shellcheck source=/dev/null
        source "$_GPU_VM_CONF"
        return 0
    fi
    return 1
}

_gpu_vm_save_config() {
    mkdir -p "$_GPU_CONF_DIR"
    cat > "$_GPU_VM_CONF" <<EOF
# Generated by hyprconf hardware gpu vm install — $(date '+%Y-%m-%d %H:%M:%S')
VM_RAM="${VM_RAM}"
VM_CPU="${VM_CPU}"
VM_DISK="${VM_DISK}"
VM_USERNAME="${VM_USERNAME}"
VM_PASSWORD="${VM_PASSWORD}"
VM_VERSION="${VM_VERSION}"
VM_IVSHMEM_SIZE="${VM_IVSHMEM_SIZE:-64}"
EOF
}

_gpu_vm_generate_oem() {
    # Generate OEM install.bat that auto-installs gaming platforms, Firefox,
    # and applies maximum privacy settings.
    # Dockurr copies /oem → C:\OEM and runs install.bat at the end of unattended setup.
    mkdir -p "$_GPU_VM_OEM_DIR"
    cat > "$_GPU_VM_OEM_DIR/install.bat" <<'OEMEOF'
@echo off
setlocal

echo === hyprconf OEM: Installing software ===

echo [1/4] Downloading Steam...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://cdn.cloudflare.steamstatic.com/client/installer/SteamSetup.exe' -OutFile '%TEMP%\SteamSetup.exe'"
if exist "%TEMP%\SteamSetup.exe" (
    echo [1/4] Installing Steam silently...
    start /wait "" "%TEMP%\SteamSetup.exe" /S
    del "%TEMP%\SteamSetup.exe"
    echo [1/4] Steam installed.
) else (
    echo [1/4] Steam download failed, skipping.
)

echo [2/4] Downloading Epic Games Launcher...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi' -OutFile '%TEMP%\EpicInstaller.msi'"
if exist "%TEMP%\EpicInstaller.msi" (
    echo [2/4] Installing Epic Games Launcher silently...
    msiexec /i "%TEMP%\EpicInstaller.msi" /quiet /norestart
    del "%TEMP%\EpicInstaller.msi"
    echo [2/4] Epic Games Launcher installed.
) else (
    echo [2/4] Epic download failed, skipping.
)

echo [3/4] Downloading Battle.net...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.battle.net/download/getInstallerForGame?os=win&gameProgram=BATTLENET_APP&version=Live' -OutFile '%TEMP%\Battle.net-Setup.exe'"
if exist "%TEMP%\Battle.net-Setup.exe" (
    echo [3/4] Installing Battle.net silently...
    start /wait "" "%TEMP%\Battle.net-Setup.exe" --lang=enUS --installpath="C:\Program Files (x86)\Battle.net" --productinstall
    del "%TEMP%\Battle.net-Setup.exe"
    echo [3/4] Battle.net installed.
) else (
    echo [3/4] Battle.net download failed, skipping.
)

echo [4/4] Downloading Firefox...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US' -OutFile '%TEMP%\FirefoxSetup.exe'"
if exist "%TEMP%\FirefoxSetup.exe" (
    echo [4/4] Installing Firefox silently...
    start /wait "" "%TEMP%\FirefoxSetup.exe" /S
    del "%TEMP%\FirefoxSetup.exe"
    echo [4/4] Firefox installed.
) else (
    echo [4/4] Firefox download failed, skipping.
)

echo === Applying privacy settings ===
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 $p='HKLM:\SOFTWARE\Policies\Microsoft\Windows';^
 $c='HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion';^
 ^
 # --- Telemetry ---^
 New-Item -Path \"$p\DataCollection\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$p\DataCollection\" -Name AllowTelemetry -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$p\DataCollection\" -Name DoNotShowFeedbackNotifications -Value 1 -Type DWord;^
 New-Item -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Diagnostics\DiagTrack' -Force | Out-Null;^
 Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Diagnostics\DiagTrack' -Name ShowedToastAtLevel -Value 1 -Type DWord;^
 ^
 # --- Advertising ID ---^
 New-Item -Path \"$c\AdvertisingInfo\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\AdvertisingInfo\" -Name Enabled -Value 0 -Type DWord;^
 ^
 # --- Activity History ---^
 New-Item -Path \"$p\System\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$p\System\" -Name EnableActivityFeed -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$p\System\" -Name PublishUserActivities -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$p\System\" -Name UploadUserActivities -Value 0 -Type DWord;^
 ^
 # --- Location ---^
 New-Item -Path \"$c\CapabilityAccessManager\ConsentStore\location\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\CapabilityAccessManager\ConsentStore\location\" -Name Value -Value 'Deny';^
 ^
 # --- Cortana ---^
 New-Item -Path \"$p\Windows Search\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$p\Windows Search\" -Name AllowCortana -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$p\Windows Search\" -Name AllowSearchToUseLocation -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$p\Windows Search\" -Name AllowCloudSearch -Value 0 -Type DWord;^
 ^
 # --- Start menu suggestions / tips ---^
 New-Item -Path \"$c\ContentDeliveryManager\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SystemPaneSuggestionsEnabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SoftLandingEnabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SubscribedContent-338388Enabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SubscribedContent-310093Enabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SubscribedContent-338389Enabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SubscribedContent-338393Enabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name OemPreInstalledAppsEnabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name PreInstalledAppsEnabled -Value 0 -Type DWord;^
 Set-ItemProperty -Path \"$c\ContentDeliveryManager\" -Name SilentInstalledAppsEnabled -Value 0 -Type DWord;^
 ^
 # --- Tailored experiences ---^
 New-Item -Path \"$c\Privacy\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\Privacy\" -Name TailoredExperiencesWithDiagnosticDataEnabled -Value 0 -Type DWord;^
 ^
 # --- Online speech recognition ---^
 New-Item -Path 'HKCU:\SOFTWARE\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy' -Force | Out-Null;^
 Set-ItemProperty -Path 'HKCU:\SOFTWARE\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy' -Name HasAccepted -Value 0 -Type DWord;^
 ^
 # --- Inking and typing personalisation ---^
 New-Item -Path \"$c\InputPersonalization\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\InputPersonalization\" -Name RestrictImplicitInkCollection -Value 1 -Type DWord;^
 Set-ItemProperty -Path \"$c\InputPersonalization\" -Name RestrictImplicitTextCollection -Value 1 -Type DWord;^
 New-Item -Path \"$c\InputPersonalization\TrainedDataStore\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\InputPersonalization\TrainedDataStore\" -Name HarvestContacts -Value 0 -Type DWord;^
 ^
 # --- App launch tracking ---^
 New-Item -Path \"$c\Explorer\Advanced\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$c\Explorer\Advanced\" -Name Start_TrackProgs -Value 0 -Type DWord;^
 ^
 # --- Disable DiagTrack and dmwappushservice ---^
 Stop-Service -Name DiagTrack -Force -ErrorAction SilentlyContinue;^
 Set-Service -Name DiagTrack -StartupType Disabled -ErrorAction SilentlyContinue;^
 Stop-Service -Name dmwappushservice -Force -ErrorAction SilentlyContinue;^
 Set-Service -Name dmwappushservice -StartupType Disabled -ErrorAction SilentlyContinue;^
 ^
 # --- Disable Copilot ---^
 New-Item -Path \"$p\WindowsCopilot\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$p\WindowsCopilot\" -Name TurnOffWindowsCopilot -Value 1 -Type DWord;^
 ^
 # --- Disable Recall ---^
 New-Item -Path \"$p\WindowsAI\" -Force | Out-Null;^
 Set-ItemProperty -Path \"$p\WindowsAI\" -Name DisableAIDataAnalysis -Value 1 -Type DWord;^
 ^
 # --- Disable widgets ---^
 New-Item -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Dsh' -Force | Out-Null;^
 Set-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Dsh' -Name AllowNewsAndInterests -Value 0 -Type DWord;^
 ^
 Write-Host 'Privacy settings applied.'

echo === OEM install complete ===
endlocal
OEMEOF
}

_gpu_vm_generate_compose() {
    # Generate docker-compose.yml with GPU passthrough, Looking Glass,
    # and comprehensive anti-detection (SMBIOS, CPU, disk, devices).
    if ! _gpu_load_config; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n" >&2
        return 1
    fi
    if ! _gpu_vm_load_config; then
        printf "Windows VM not configured. Run: hyprconf hardware gpu vm install\n" >&2
        return 1
    fi

    local iommu_group="${GPU_IOMMU_GROUP:-}"
    if [[ -z "$iommu_group" ]]; then
        printf "IOMMU group not set in GPU config.\n" >&2
        return 1
    fi

    # ── Build QEMU ARGUMENTS ──────────────────────────────────────────────
    local qemu_args=""

    # Anti-detection: SMBIOS host-identity spoofing
    local smbios_args
    smbios_args=$(_gpu_vm_smbios_args)
    [[ -n "$smbios_args" ]] && qemu_args+="${smbios_args}"

    # Anti-detection: Disk identity spoofing
    local disk_flags
    disk_flags=$(_gpu_vm_disk_flags)
    [[ -n "$disk_flags" ]] && qemu_args+=" ${disk_flags}"

    # Looking Glass: ivshmem shared memory device (only if kvmfr is loaded)
    local ivshmem_size="${VM_IVSHMEM_SIZE:-64}"
    local has_kvmfr=false
    if [[ -e "$_GPU_VM_KVMFR_DEV" ]]; then
        has_kvmfr=true
        qemu_args+=" -device ivshmem-plain,id=shmem0,memdev=looking-glass"
        qemu_args+=" -object memory-backend-file,id=looking-glass,mem-path=${_GPU_VM_KVMFR_DEV},size=${ivshmem_size}M,share=yes"
    fi

    # GPU passthrough: vfio-pci devices (skip PCI bridges)
    local dev_pci dev_class
    for dev_pci in ${GPU_IOMMU_DEVICES:-$GPU_PCI_ADDR}; do
        dev_class=$(_gpu_get_pci_class "$dev_pci" 2>/dev/null) || continue
        [[ "$dev_class" == "0604" ]] && continue
        qemu_args+=" -device vfio-pci,host=${dev_pci}"
    done

    # SPICE + Looking Glass input devices (only when kvmfr is available)
    if [[ "$has_kvmfr" == true ]]; then
        # Audio output via intel-hda over SPICE
        qemu_args+=" -audiodev spice,id=spice"
        qemu_args+=" -device intel-hda"
        qemu_args+=" -device hda-duplex,audiodev=spice"

        # SPICE display socket (Looking Glass connects here for input)
        qemu_args+=" -spice unix=on,addr=/tmp/spice/spice.sock,disable-ticketing=on,agent-mouse=off"

        # SPICE clipboard channel (vdagent)
        qemu_args+=" -device virtio-serial-pci"
        qemu_args+=" -device virtserialport,chardev=spicechannel0,name=com.redhat.spice.0"
        qemu_args+=" -chardev spicevmc,id=spicechannel0,name=vdagent"

        # Input: mouse and keyboard via virtio
        qemu_args+=" -device virtio-mouse-pci"
        qemu_args+=" -device virtio-keyboard-pci"
    fi

    # Power: disable S3/S4 (suspend/hibernate breaks GPU passthrough)
    qemu_args+=" -global ICH9-LPC.disable_s3=1"
    qemu_args+=" -global ICH9-LPC.disable_s4=1"

    # USB: add controller + devices only if user has configured USB passthrough
    local usb_args
    usb_args=$(_gpu_vm_usb_qemu_args)
    if [[ -n "$usb_args" ]]; then
        qemu_args+=" -device qemu-xhci,id=xhci${usb_args}"
    fi

    qemu_args="${qemu_args# }"  # trim leading space

    # ── Build remaining compose fields ────────────────────────────────────
    # CPU anti-detection flags (hides hypervisor bit, passes real CPU identity)
    local cpu_flags
    cpu_flags=$(_gpu_vm_cpu_flags)

    local spice_dir
    spice_dir=$(_gpu_vm_spice_dir)

    local tz
    tz=$(timedatectl show -p Timezone --value 2>/dev/null || echo "UTC")

    mkdir -p "$_GPU_CONF_DIR" "$_GPU_VM_STORAGE_DIR" "$_GPU_VM_SHARED_DIR" "$_GPU_VM_OEM_DIR"

    # Build devices list (kvmfr0 only if module is loaded)
    local devices_block="      - /dev/kvm
      - /dev/net/tun
      - /dev/vfio/${iommu_group}:/dev/vfio/${iommu_group}
      - /dev/vfio/vfio:/dev/vfio/vfio"
    if [[ "$has_kvmfr" == true ]]; then
        devices_block="      - /dev/kvm
      - /dev/net/tun
      - ${_GPU_VM_KVMFR_DEV}:${_GPU_VM_KVMFR_DEV}
      - /dev/vfio/${iommu_group}:/dev/vfio/${iommu_group}
      - /dev/vfio/vfio:/dev/vfio/vfio"
    fi

    cat > "$_GPU_VM_COMPOSE" <<EOF
services:
  windows:
    image: dockurr/windows
    container_name: ${_GPU_VM_CONTAINER}
    environment:
      VERSION: "${VM_VERSION:-11}"
      RAM_SIZE: "${VM_RAM:-8G}"
      CPU_CORES: "${VM_CPU:-4}"
      DISK_SIZE: "${VM_DISK:-64G}"
      USERNAME: "${VM_USERNAME:-user}"
      PASSWORD: "${VM_PASSWORD:-admin}"
      TZ: "${tz}"
      CPU_FLAGS: "${cpu_flags}"
      MACHINE: "q35"
      DISPLAY: "none"
      ADAPTER: "e1000e"
      DISK_TYPE: "sata"
      USB: "no"
      ARGUMENTS: "${qemu_args}"
    devices:
${devices_block}
    cap_add:
      - NET_ADMIN
    privileged: true
    ulimits:
      memlock:
        soft: -1
        hard: -1
    ports:
      - 127.0.0.1:8006:8006
      - 127.0.0.1:3389:3389/tcp
      - 127.0.0.1:3389:3389/udp
    volumes:
      - ${_GPU_VM_STORAGE_DIR}:/storage
      - ${_GPU_VM_SHARED_DIR}:/shared
      - ${_GPU_VM_OEM_DIR}:/oem
      - ${spice_dir}:/tmp/spice
    restart: unless-stopped
    stop_grace_period: 2m
EOF
    return 0
}

_gpu_vm_install() {
    # Interactive setup wizard for Windows VM configuration.
    if ! _gpu_load_config; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n" >&2
        return 1
    fi

    # Check prerequisites
    if ! command -v docker &>/dev/null; then
        printf "Docker not installed. Install with: sudo pacman -S docker\n" >&2
        return 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        printf "Docker daemon not running. Start with: sudo systemctl start docker\n" >&2
        return 1
    fi
    if ! command -v docker-compose &>/dev/null; then
        printf "docker-compose not installed. Install with: sudo pacman -S docker-compose\n" >&2
        return 1
    fi

    local total_ram_gb total_cores
    total_ram_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
    total_cores=$(nproc)

    printf "\nSystem resources:\n"
    printf "  RAM: %sGB | CPU cores: %s\n\n" "$total_ram_gb" "$total_cores"

    # RAM selection
    local ram_default="8G"
    printf "RAM to allocate [%s]: " "$ram_default"
    read -r VM_RAM
    VM_RAM="${VM_RAM:-$ram_default}"

    # CPU selection
    local cpu_default="4"
    (( cpu_default > total_cores )) && cpu_default="$total_cores"
    printf "CPU cores to allocate [%s]: " "$cpu_default"
    read -r VM_CPU
    VM_CPU="${VM_CPU:-$cpu_default}"

    # Disk selection
    local disk_default="64G"
    printf "Disk size [%s]: " "$disk_default"
    read -r VM_DISK
    VM_DISK="${VM_DISK:-$disk_default}"

    # Windows version
    local version_default="11"
    printf "Windows version (11, 11l, 10, 10l) [%s]: " "$version_default"
    read -r VM_VERSION
    VM_VERSION="${VM_VERSION:-$version_default}"

    # IVSHMEM size for Looking Glass shared memory
    printf "\nLooking Glass IVSHMEM size:\n"
    printf "  32  — 1080p\n"
    printf "  64  — 1440p (recommended)\n"
    printf "  128 — 4K\n"
    local ivshmem_default="64"
    printf "IVSHMEM size in MB [%s]: " "$ivshmem_default"
    read -r VM_IVSHMEM_SIZE
    VM_IVSHMEM_SIZE="${VM_IVSHMEM_SIZE:-$ivshmem_default}"

    # Credentials
    local user_default="user"
    printf "Windows username [%s]: " "$user_default"
    read -r VM_USERNAME
    VM_USERNAME="${VM_USERNAME:-$user_default}"

    local pass_default="admin"
    printf "Windows password [%s]: " "$pass_default"
    read -r -s VM_PASSWORD
    VM_PASSWORD="${VM_PASSWORD:-$pass_default}"
    printf "\n"

    # Summary
    printf "\n── Windows VM Configuration ──\n"
    printf "  GPU:      %s (%s)\n" "${GPU_NAME}" "${GPU_PCI_ADDR}"
    printf "  RAM:      %s\n" "$VM_RAM"
    printf "  CPU:      %s cores\n" "$VM_CPU"
    printf "  Disk:     %s\n" "$VM_DISK"
    printf "  Version:  Windows %s\n" "$VM_VERSION"
    printf "  IVSHMEM:  %sMB (Looking Glass)\n" "$VM_IVSHMEM_SIZE"
    printf "  Username: %s\n" "$VM_USERNAME"
    printf "  Storage:  %s\n" "$_GPU_VM_STORAGE_DIR"
    printf "  Shared:   %s\n\n" "$_GPU_VM_SHARED_DIR"

    printf "Proceed? [Y/n]: "
    read -r confirm
    if [[ "${confirm:-y}" =~ ^[Nn] ]]; then
        printf "Cancelled.\n"
        return 1
    fi

    _gpu_vm_save_config
    _gpu_vm_generate_oem
    _gpu_vm_generate_compose

    printf "\n✔ Windows VM configured.\n"
    printf "  Prerequisites:\n"
    printf "    sudo modprobe kvmfr static_size_mb=%s\n" "$VM_IVSHMEM_SIZE"
    printf "    (Add 'kvmfr' to /etc/modules-load.d/ for persistence)\n"
    printf "    GPU must have a display connected (monitor, second cable, or dummy plug)\n"
    printf "  Launch:  hyprconf hardware gpu vm launch\n"
    printf "  Status:  hyprconf hardware gpu vm status\n"
}

_gpu_vm_launch() {
    # Bind GPU to vfio-pci (if needed), start Docker container, connect.
    local stop_on_disconnect=false force="" use_rdp=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --stop-on-disconnect|-s) stop_on_disconnect=true ;;
            --keep-alive|-k)         ;;  # legacy no-op (now the default)
            --force|-f)              force="force" ;;
            --rdp)                   use_rdp=true ;;
        esac
        shift
    done

    if ! _gpu_load_config; then
        printf "GPU passthrough not configured. Run: hyprconf hardware gpu setup\n" >&2
        return 1
    fi
    if ! _gpu_vm_load_config; then
        printf "Windows VM not configured. Run: hyprconf hardware gpu vm install\n" >&2
        return 1
    fi

    # Create SPICE socket directory
    local spice_dir
    spice_dir=$(_gpu_vm_spice_dir)
    mkdir -p "$spice_dir"

    # Check Looking Glass prerequisites
    if [[ ! -e "$_GPU_VM_KVMFR_DEV" ]]; then
        printf "⚠ %s not found.\n" "$_GPU_VM_KVMFR_DEV" >&2
        printf "  Load kvmfr module: sudo modprobe kvmfr static_size_mb=%s\n" "${VM_IVSHMEM_SIZE:-64}" >&2
        printf "  Continuing without Looking Glass (RDP fallback).\n" >&2
        use_rdp=true
    fi

    # Ensure GPU is bound to vfio-pci
    local current_driver
    current_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR")
    if [[ "$current_driver" != "vfio-pci" ]]; then
        printf "→ Binding GPU to vfio-pci...\n"
        _gpu_mode_vm "$force" || return 1
    fi

    # Regenerate compose (GPU config may have changed)
    _gpu_vm_generate_compose || return 1

    # Check container status
    local container_status
    container_status=$(docker inspect --format='{{.State.Status}}' "$_GPU_VM_CONTAINER" 2>/dev/null || echo "")

    if [[ "$container_status" != "running" ]]; then
        printf "→ Starting Windows VM...\n"
        if ! docker-compose -f "$_GPU_VM_COMPOSE" up -d 2>&1; then
            printf "✘ Failed to start VM. Check: docker logs %s\n" "$_GPU_VM_CONTAINER" >&2
            return 1
        fi

        printf "  Waiting for VM to boot...\n"
        printf "  GPU display should be visible on the monitor connected to the passthrough GPU.\n"

        local wait_count=0
        while ! docker logs "$_GPU_VM_CONTAINER" 2>&1 | grep -qi "windows started successfully\|booting.*qemu"; do
            sleep 2
            wait_count=$((wait_count + 1))
            if (( wait_count > 90 )); then
                printf "\n⚠ VM may still be installing Windows (first boot takes 10-15 min).\n"
                printf "  First boot: Windows installer runs on the GPU-connected display.\n"
                printf "  After install: install GPU drivers, then Looking Glass host app.\n"
                return 0
            fi
        done
    fi

    printf "✔ VM is running.\n"

    # Connect to VM
    local rdp_bin
    rdp_bin=$(_gpu_vm_freerdp_bin 2>/dev/null || echo "")

    if [[ "$use_rdp" == false ]] && command -v looking-glass-client &>/dev/null; then
        printf "→ Launching Looking Glass...\n"
        looking-glass-client -f "$_GPU_VM_KVMFR_DEV" -c "${spice_dir}/spice.sock" &
        printf "  Stop VM: hyprconf hardware gpu vm stop\n"
        if [[ -n "$rdp_bin" ]]; then
            printf "  RDP:     %s /v:127.0.0.1:3389 /u:%s /p:%s\n" "$rdp_bin" "${VM_USERNAME}" "${VM_PASSWORD}"
        fi
    elif [[ -n "$rdp_bin" ]]; then
        printf "→ Connecting via RDP...\n"

        # Wait for RDP port
        local rdp_wait=0
        while ! timeout 1 bash -c 'echo > /dev/tcp/127.0.0.1/3389' 2>/dev/null; do
            sleep 2
            rdp_wait=$((rdp_wait + 1))
            if (( rdp_wait > 30 )); then
                printf "⚠ RDP not yet available. VM may still be installing.\n"
                printf "  Connect manually: %s /v:127.0.0.1:3389 /u:%s /p:%s\n" "$rdp_bin" "${VM_USERNAME}" "${VM_PASSWORD}"
                return 0
            fi
        done

        # Detect Hyprland monitor scale
        local scale_arg=""
        if command -v hyprctl &>/dev/null; then
            local hypr_scale
            hypr_scale=$(hyprctl monitors -j 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(next((m['scale'] for m in d if m.get('focused')), 1.0))" 2>/dev/null || echo "1.0")
            local scale_pct
            scale_pct=$(printf '%.0f' "$(echo "$hypr_scale * 100" | bc 2>/dev/null || echo "100")")
            if (( scale_pct >= 170 )); then
                scale_arg="/scale:180"
            elif (( scale_pct >= 130 )); then
                scale_arg="/scale:140"
            fi
        fi

        "$rdp_bin" /u:"${VM_USERNAME}" /p:"${VM_PASSWORD}" /v:127.0.0.1:3389 \
            /cert:ignore /sound /microphone /clipboard \
            /title:"Windows VM — .hyprconf" /dynamic-resolution \
            /gfx:AVC444 ${scale_arg} +grab-keyboard 2>/dev/null || true

        if [[ "$stop_on_disconnect" == true ]]; then
            printf "→ RDP disconnected. Stopping VM...\n"
            docker-compose -f "$_GPU_VM_COMPOSE" down 2>/dev/null
            printf "✔ VM stopped.\n"
        else
            printf "→ RDP disconnected. VM still running.\n"
            printf "  Stop with: hyprconf hardware gpu vm stop\n"
        fi
    else
        printf "  Install looking-glass-client (AUR) or freerdp for display.\n"
        printf "  Web viewer: http://127.0.0.1:8006\n"
    fi
}

_gpu_vm_stop() {
    if [[ ! -f "$_GPU_VM_COMPOSE" ]]; then
        printf "Windows VM not configured.\n" >&2
        return 1
    fi

    local container_status
    container_status=$(docker inspect --format='{{.State.Status}}' "$_GPU_VM_CONTAINER" 2>/dev/null || echo "")

    if [[ "$container_status" != "running" ]]; then
        printf "VM is not running.\n"
        return 0
    fi

    printf "→ Stopping Windows VM...\n"
    docker-compose -f "$_GPU_VM_COMPOSE" down 2>/dev/null
    printf "✔ VM stopped.\n"
    printf "  Restore GPU: hyprconf hardware gpu mode host\n"
}

_gpu_vm_status() {
    if ! _gpu_load_config; then
        printf "GPU passthrough not configured.\n"
        return 0
    fi

    local gpu_driver
    gpu_driver=$(_gpu_get_pci_driver "$GPU_PCI_ADDR" 2>/dev/null || echo "unknown")

    printf "── GPU VM Status ──\n"
    printf "  GPU:    %s (%s)\n" "${GPU_NAME:-unknown}" "${GPU_PCI_ADDR:-unknown}"
    printf "  Driver: %s\n" "$gpu_driver"

    if _gpu_vm_load_config; then
        printf "  VM:     %s RAM, %s cores, %s disk\n" "${VM_RAM}" "${VM_CPU}" "${VM_DISK}"
    else
        printf "  VM:     not configured (run: hyprconf hardware gpu vm install)\n"
        return 0
    fi

    local container_status
    container_status=$(docker inspect --format='{{.State.Status}}' "$_GPU_VM_CONTAINER" 2>/dev/null || echo "not created")

    if [[ "$container_status" == "running" ]]; then
        printf "  Status: ● running\n"
        printf "  Web:    http://127.0.0.1:8006\n"
        printf "  RDP:    127.0.0.1:3389\n"
    else
        printf "  Status: ○ %s\n" "$container_status"
    fi
}

_gpu_vm_remove() {
    printf "This will stop the VM and remove all VM data.\n"
    printf "Proceed? [y/N]: "
    read -r confirm
    if [[ ! "${confirm:-n}" =~ ^[Yy] ]]; then
        printf "Cancelled.\n"
        return 1
    fi

    # Stop container
    if [[ -f "$_GPU_VM_COMPOSE" ]]; then
        docker-compose -f "$_GPU_VM_COMPOSE" down 2>/dev/null || true
    fi

    # Remove container and image
    docker rm -f "$_GPU_VM_CONTAINER" 2>/dev/null || true
    docker rmi dockurr/windows 2>/dev/null || true

    # Remove config and data
    rm -f "$_GPU_VM_CONF" "$_GPU_VM_COMPOSE"
    rm -rf "$_GPU_VM_STORAGE_DIR" "$_GPU_VM_OEM_DIR"

    printf "✔ Windows VM removed.\n"
    printf "  Shared folder ~/Windows/ was preserved.\n"
}
