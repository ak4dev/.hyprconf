#!/usr/bin/env bash
set -euo pipefail

# gpu-passthrough.sh — GPU detection, VFIO binding, and passthrough management
#
# Sourced by the hyprconf binary (hyprconf hardware gpu …).
# All functions prefixed with _gpu_ to avoid namespace collisions.

readonly _GPU_CONF_DIR="${HOME}/.config/hyprconf"
readonly _GPU_CONF="${_GPU_CONF_DIR}/gpu-passthrough.conf"
readonly _GPU_LOG="/tmp/hyprconf-gpu-passthrough.log"

# GPU passthrough always uses system-level QEMU/KVM (qemu:///system).
# Wrap virsh so every call targets the right URI.
_gpu_virsh() { virsh -c qemu:///system "$@"; }

# ── Logging ────────────────────────────────────────────────────────────────────

_gpu_log() {
    local level="$1"; shift
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" >> "$_GPU_LOG" 2>/dev/null || true
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

# ── VFIO Bind / Unbind ────────────────────────────────────────────────────────

_gpu_bind_vfio() {
    # Bind all devices in the GPU's IOMMU group to vfio-pci.
    # Pass "force" as $2 to skip the display-GPU safety check.
    local pci_addr="$1"
    local force="${2:-}"
    local full_addr="0000:${pci_addr}"

    if [[ "$force" != "force" ]] && _gpu_is_display_gpu "$pci_addr"; then
        echo "Refusing to unbind GPU at ${pci_addr} — it has an active display connector." >&2
        echo "Unbinding this GPU will freeze your desktop." >&2
        echo "Use --force to override: hyprconf hardware gpu bind --force ${pci_addr}" >&2
        return 1
    fi

    _gpu_log "INFO" "Binding GPU at ${pci_addr} to vfio-pci"

    # Ensure vfio-pci module is loaded
    if ! lsmod | grep -q "^vfio_pci"; then
        _gpu_log "INFO" "Loading vfio-pci module"
        printf "  Loading vfio-pci module...\n"
        sudo modprobe vfio-pci || {
            _gpu_log "ERROR" "Failed to load vfio-pci module"
            return 1
        }
    fi

    # Bind all devices in the IOMMU group
    local devs
    devs=$(_gpu_iommu_devices "$pci_addr") || {
        echo "Cannot determine IOMMU group for ${pci_addr}." >&2
        return 1
    }

    # Prefer virsh nodedev-detach — it handles NVIDIA FLR quirks and avoids
    # raw sysfs writes that can hang on GPUs left in a bad state.
    if command -v virsh &>/dev/null; then
        local dev nodedev_name
        while IFS= read -r dev; do
            [[ -z "$dev" ]] && continue
            if [[ "$(_gpu_current_driver "$dev")" == "vfio-pci" ]]; then
                _gpu_log "INFO" "${dev} already bound to vfio-pci"
                continue
            fi
            nodedev_name="pci_0000_$(echo "$dev" | tr ':.' '_')"
            printf "  Detaching %s (%s)...\n" "$dev" "$nodedev_name"
            _gpu_log "INFO" "_gpu_virsh nodedev-detach ${nodedev_name}"
            _gpu_virsh nodedev-detach "$nodedev_name" 2>/dev/null || {
                _gpu_log "WARN" "_gpu_virsh nodedev-detach failed for ${dev}, trying sysfs"
                printf "  ⚠ virsh failed for %s — falling back to sysfs bind.\n" "$dev"
                _gpu_sysfs_bind_one "$dev"
            }
        done <<< "$devs"
    else
        local dev
        while IFS= read -r dev; do
            [[ -z "$dev" ]] && continue
            _gpu_sysfs_bind_one "$dev"
        done <<< "$devs"
    fi

    _gpu_log "SUCCESS" "All IOMMU group devices bound to vfio-pci"
    return 0
}

_gpu_sysfs_bind_one() {
    # Bind a single PCI device to vfio-pci via direct sysfs writes.
    local dev="$1"
    local full_dev="0000:${dev}"
    local current_driver
    current_driver=$(_gpu_current_driver "$dev")

    if [[ "$current_driver" == "vfio-pci" ]]; then
        _gpu_log "INFO" "${dev} already bound to vfio-pci"
        return 0
    fi

    # Unbind from current driver
    if [[ "$current_driver" != "none" ]]; then
        printf "  Unbinding %s from %s...\n" "$dev" "$current_driver"
        _gpu_log "INFO" "Unbinding ${dev} from ${current_driver}"
        echo "$full_dev" | sudo tee "/sys/bus/pci/devices/${full_dev}/driver/unbind" > /dev/null 2>&1 || true
    fi

    # Override driver to vfio-pci
    printf "  Binding %s to vfio-pci...\n" "$dev"
    _gpu_log "INFO" "Binding ${dev} to vfio-pci"
    echo "vfio-pci" | sudo tee "/sys/bus/pci/devices/${full_dev}/driver_override" > /dev/null
    echo "$full_dev" | sudo tee /sys/bus/pci/drivers/vfio-pci/bind > /dev/null 2>&1 || {
        # Try probing instead
        echo "$full_dev" | sudo tee /sys/bus/pci/drivers_probe > /dev/null
    }

    _gpu_log "INFO" "Bound ${dev} to vfio-pci"
}

_gpu_unbind_vfio() {
    # Unbind all devices in the GPU's IOMMU group from vfio-pci
    # and restore them to their original drivers.
    local pci_addr="$1"

    _gpu_log "INFO" "Unbinding GPU at ${pci_addr} from vfio-pci"

    local devs
    devs=$(_gpu_iommu_devices "$pci_addr") || {
        echo "Cannot determine IOMMU group for ${pci_addr}." >&2
        return 1
    }

    local dev full_dev current_driver
    while IFS= read -r dev; do
        [[ -z "$dev" ]] && continue
        full_dev="0000:${dev}"
        current_driver=$(_gpu_current_driver "$dev")

        if [[ "$current_driver" != "vfio-pci" ]]; then
            _gpu_log "INFO" "${dev} not bound to vfio-pci (driver: ${current_driver}), skipping"
            continue
        fi

        # Unbind from vfio-pci
        _gpu_log "INFO" "Unbinding ${dev} from vfio-pci"
        echo "$full_dev" | sudo tee "/sys/bus/pci/devices/${full_dev}/driver/unbind" > /dev/null 2>&1 || true

        # Clear driver override so the original driver can claim the device
        echo "" | sudo tee "/sys/bus/pci/devices/${full_dev}/driver_override" > /dev/null

        # Trigger driver probe to re-bind the original driver
        echo "$full_dev" | sudo tee /sys/bus/pci/drivers_probe > /dev/null

        local new_driver
        new_driver=$(_gpu_current_driver "$dev")
        _gpu_log "INFO" "${dev} now bound to ${new_driver}"
    done <<< "$devs"

    _gpu_log "SUCCESS" "GPU at ${pci_addr} returned to host"
    return 0
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
    for pkg in libvirt virt-manager qemu-desktop edk2-ovmf dnsmasq swtpm; do
        if pacman -Qi "$pkg" &>/dev/null; then
            printf "  ✔ %s installed\n" "$pkg"
        else
            printf "  ✘ %s not installed\n" "$pkg"
            errors=$((errors + 1))
        fi
    done

    # 4. Services
    printf "\nServices\n"
    local svc
    for svc in libvirtd virtlogd; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            printf "  ✔ %s running\n" "$svc"
        elif systemctl is-enabled --quiet "$svc" 2>/dev/null; then
            printf "  ⚠ %s enabled but not running\n" "$svc"
            warnings=$((warnings + 1))
        else
            printf "  ✘ %s not enabled\n" "$svc"
            errors=$((errors + 1))
        fi
    done

    # 5. User groups
    printf "\nUser Groups\n"
    local grp
    for grp in libvirt kvm; do
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

    # 5. Detect GPUs and let user choose
    printf "\nDetected GPUs:\n\n"
    _gpu_detect

    printf "Run 'hyprconf hardware gpu pass <gpu> <vm>' to pass a GPU to a VM.\n"
    printf "Run 'hyprconf hardware gpu audit' to verify system readiness.\n"
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

    mkdir -p "$_GPU_CONF_DIR"
    {
        printf '# Generated by hyprconf hardware gpu setup — %s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf 'GPU_PCI_ADDR="%s"\n' "$pci_addr"
        printf 'GPU_NAME="%s"\n' "$name"
        printf 'GPU_VENDOR_DEVICE="%s"\n' "$vendor_device"
        printf 'GPU_DRIVER_ORIGINAL="%s"\n' "$driver"
        printf 'GPU_IOMMU_GROUP="%s"\n' "$iommu_group"
        printf 'GPU_IOMMU_DEVICES="%s"\n' "$iommu_devs"
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

        printf "[LIBVIRT STATUS]\n"
        systemctl status libvirtd 2>/dev/null | head -5 || printf "libvirtd not found\n"
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
            local cfg_driver
            cfg_driver=$(_gpu_current_driver "$GPU_PCI_ADDR")
            if [[ "$cfg_driver" == "vfio-pci" ]]; then
                printf "  Binding:     active (vfio-pci)\n"
            else
                printf "  Binding:     host (%s)\n" "$cfg_driver"
            fi
        fi
    else
        printf "  Configured:  none (run: hyprconf hardware gpu setup)\n"
    fi
}

# ── VM GPU Attach / SMBIOS ─────────────────────────────────────────────────────

_gpu_host_smbios() {
    # Read host SMBIOS system info via dmidecode.
    # Returns manufacturer, product, serial as tab-separated values.
    local mfg product serial
    mfg=$(sudo dmidecode -t system 2>/dev/null | grep 'Manufacturer:' | head -1 | sed 's/.*Manufacturer:\s*//')
    product=$(sudo dmidecode -t system 2>/dev/null | grep 'Product Name:' | head -1 | sed 's/.*Product Name:\s*//')
    serial=$(sudo dmidecode -t system 2>/dev/null | grep 'Serial Number:' | head -1 | sed 's/.*Serial Number:\s*//')
    printf '%s\t%s\t%s\n' "$mfg" "$product" "$serial"
}

_gpu_attach_to_vm() {
    # Attach a GPU and its IOMMU group devices to a libvirt VM.
    # Also configures SMBIOS passthrough for OEM license activation.
    local pci_addr="$1" vm_name="$2"

    _gpu_log "INFO" "Attaching GPU at ${pci_addr} to VM ${vm_name}"

    # Verify VM exists
    if ! _gpu_virsh dominfo "$vm_name" &>/dev/null; then
        printf "VM '%s' not found. Available VMs:\n" "$vm_name" >&2
        _gpu_virsh list --all --name 2>/dev/null | grep -v '^$' | sed 's/^/  /' >&2
        return 1
    fi

    # Attach all IOMMU group PCI devices
    local devs
    devs=$(_gpu_iommu_devices "$pci_addr") || {
        echo "Cannot determine IOMMU group for ${pci_addr}." >&2
        return 1
    }

    local dev attached=0
    while IFS= read -r dev; do
        [[ -z "$dev" ]] && continue
        local domain bus slot func
        domain="0x0000"
        bus="0x${dev%%:*}"
        local slot_func="${dev#*:}"
        slot="0x${slot_func%%.*}"
        func="0x${slot_func##*.}"

        # Check if already attached
        if _gpu_virsh dumpxml "$vm_name" 2>/dev/null | grep -q "bus='${bus}'" && \
           _gpu_virsh dumpxml "$vm_name" 2>/dev/null | grep -q "slot='${slot}'" && \
           _gpu_virsh dumpxml "$vm_name" 2>/dev/null | grep -q "function='${func}'"; then
            _gpu_log "INFO" "PCI ${dev} already attached to ${vm_name}"
            continue
        fi

        local xml
        xml=$(printf '<hostdev mode="subsystem" type="pci" managed="yes">\n  <source>\n    <address domain="%s" bus="%s" slot="%s" function="%s"/>\n  </source>\n</hostdev>\n' \
            "$domain" "$bus" "$slot" "$func")

        printf "  → Attaching PCI %s...\n" "$dev"
        echo "$xml" | _gpu_virsh attach-device "$vm_name" /dev/stdin --config 2>/dev/null \
            || echo "$xml" | _gpu_virsh attach-device "$vm_name" /dev/stdin --persistent 2>/dev/null \
            || {
                _gpu_log "WARN" "Failed to attach ${dev} via virsh, trying virt-xml"
                virt-xml "$vm_name" --add-device --hostdev "$dev" 2>/dev/null || {
                    printf "  ⚠ Could not attach %s — add manually in virt-manager.\n" "$dev"
                    _gpu_log "WARN" "Could not attach ${dev} to ${vm_name}"
                    continue
                }
            }

        attached=$((attached + 1))
        _gpu_log "INFO" "Attached PCI ${dev} to ${vm_name}"
    done <<< "$devs"

    # Configure SMBIOS passthrough for OEM license activation
    _gpu_configure_smbios "$vm_name"

    if (( attached > 0 )); then
        printf "  ✔ Attached %d PCI device(s) to %s.\n" "$attached" "$vm_name"
    else
        printf "  ℹ All IOMMU group devices already attached to %s.\n" "$vm_name"
    fi

    return 0
}

_gpu_configure_smbios() {
    # Configure SMBIOS passthrough on a VM for OEM Windows license activation.
    local vm_name="$1"

    _gpu_log "INFO" "Configuring SMBIOS passthrough for ${vm_name}"

    # Check if SMBIOS already configured
    if _gpu_virsh dumpxml "$vm_name" 2>/dev/null | grep -q '<sysinfo type="smbios"'; then
        printf "  ✔ SMBIOS already configured on %s.\n" "$vm_name"
        return 0
    fi

    # Read host SMBIOS
    local smbios_data mfg product serial
    smbios_data=$(_gpu_host_smbios)
    mfg=$(echo "$smbios_data" | cut -f1)
    product=$(echo "$smbios_data" | cut -f2)
    serial=$(echo "$smbios_data" | cut -f3)

    if [[ -z "$mfg" || "$mfg" == "Not Specified" ]]; then
        printf "  ⚠ Could not read host SMBIOS data. Skipping SMBIOS passthrough.\n"
        _gpu_log "WARN" "Empty SMBIOS data, skipping"
        return 0
    fi

    printf "  → Configuring SMBIOS: %s %s\n" "$mfg" "$product"

    # Use virt-xml to add sysinfo if available
    if command -v virt-xml &>/dev/null; then
        virt-xml "$vm_name" --edit --sysinfo type=smbios,bios.vendor="$mfg",system.manufacturer="$mfg",system.product="$product",system.serial="$serial" 2>/dev/null && {
            # Also set smbios mode
            virt-xml "$vm_name" --edit --os-info smbios_mode=sysinfo 2>/dev/null || true
            _gpu_log "INFO" "SMBIOS configured via virt-xml"
            printf "  ✔ SMBIOS passthrough configured for OEM license activation.\n"
            return 0
        }
    fi

    # Fallback: edit XML directly
    local tmp_xml
    tmp_xml=$(mktemp /tmp/hyprconf-smbios-XXXXXX.xml)
    _gpu_virsh dumpxml "$vm_name" > "$tmp_xml" 2>/dev/null || {
        rm -f "$tmp_xml"
        printf "  ⚠ Could not dump VM XML. Add SMBIOS manually in virt-manager.\n"
        return 0
    }

    # Insert sysinfo block before </domain>
    local sysinfo_xml
    sysinfo_xml=$(printf '  <sysinfo type="smbios">\n    <system>\n      <entry name="manufacturer">%s</entry>\n      <entry name="product">%s</entry>\n      <entry name="serial">%s</entry>\n    </system>\n  </sysinfo>' \
        "$mfg" "$product" "$serial")

    if ! grep -q '<sysinfo' "$tmp_xml"; then
        sed -i "/<\/domain>/i\\${sysinfo_xml}" "$tmp_xml"
    fi

    # Set smbios mode on <os>
    if ! grep -q 'smbios mode' "$tmp_xml"; then
        sed -i 's|</os>|  <smbios mode="sysinfo"/>\n  </os>|' "$tmp_xml"
    fi

    _gpu_virsh define "$tmp_xml" > /dev/null 2>&1 && {
        _gpu_log "INFO" "SMBIOS configured via XML edit"
        printf "  ✔ SMBIOS passthrough configured for OEM license activation.\n"
    } || {
        printf "  ⚠ Could not apply SMBIOS XML. Add manually in virt-manager.\n"
        _gpu_log "WARN" "Failed to define SMBIOS XML"
    }

    rm -f "$tmp_xml"
    return 0
}

_gpu_detach_from_vm() {
    # Remove GPU PCI devices from a libvirt VM.
    local pci_addr="$1" vm_name="$2"

    _gpu_log "INFO" "Detaching GPU at ${pci_addr} from VM ${vm_name}"

    local devs
    devs=$(_gpu_iommu_devices "$pci_addr") || return 1

    local dev detached=0
    while IFS= read -r dev; do
        [[ -z "$dev" ]] && continue
        local bus slot func
        bus="0x${dev%%:*}"
        local slot_func="${dev#*:}"
        slot="0x${slot_func%%.*}"
        func="0x${slot_func##*.}"

        local xml
        xml=$(printf '<hostdev mode="subsystem" type="pci" managed="yes">\n  <source>\n    <address domain="0x0000" bus="%s" slot="%s" function="%s"/>\n  </source>\n</hostdev>\n' \
            "$bus" "$slot" "$func")

        echo "$xml" | _gpu_virsh detach-device "$vm_name" /dev/stdin --config 2>/dev/null && {
            detached=$((detached + 1))
            _gpu_log "INFO" "Detached PCI ${dev} from ${vm_name}"
        } || true
    done <<< "$devs"

    printf "Detached %d PCI device(s) from %s.\n" "$detached" "$vm_name"
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

    # libvirt status
    if systemctl is-active --quiet libvirtd 2>/dev/null; then
        printf "libvirtd: running ✔\n"
    elif pacman -Qi libvirt &>/dev/null; then
        printf "libvirtd: installed but not running\n"
    else
        printf "libvirtd: not installed (run: hyprconf addon vfio)\n"
    fi

    printf "\nGPUs:\n"
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        gpu_count=$((gpu_count + 1))

        local pci_addr name driver
        pci_addr=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | sed -E 's/^[0-9a-f:.]+\s+[^:]+:\s+//' | sed -E 's/\s*\[[0-9a-f]{4}:[0-9a-f]{4}\]//g' | sed -E 's/\s*\(rev [^)]+\)//')
        if [[ "$driver" == "vfio-pci" ]]; then
            status_icon="🔒 VM-ready"
        elif [[ "$driver" == "none" ]]; then
            status_icon="⚪ unbound"
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
