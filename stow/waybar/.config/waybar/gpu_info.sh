#!/usr/bin/env bash
set -euo pipefail

_nvidia() {
    command -v nvidia-smi &>/dev/null || return 1
    local out
    out=$(nvidia-smi \
        --query-gpu=utilization.gpu,power.draw,temperature.gpu,memory.used,memory.total \
        --format=csv,noheader,nounits 2>/dev/null | tr -d ' ') || return 1
    [[ -n "$out" ]] || return 1

    local util power temp mem_used mem_total
    IFS=',' read -r util power temp mem_used mem_total <<< "$out"

    local used_gib total_gib pwr
    used_gib=$(awk "BEGIN {printf \"%.1f\", ${mem_used}/1024}")
    total_gib=$(awk "BEGIN {printf \"%.1f\", ${mem_total}/1024}")
    pwr=$(printf "%.0f" "${power}")

    local thermo vram_icon
    thermo=$(printf '\ue350')
    vram_icon=$(printf '\U000F0620')

    echo "{\"text\":\"${util}% ${thermo}${temp}° ${vram_icon} ${used_gib}/${total_gib}G\",\"tooltip\":\"Util: ${util}% | Temp: ${temp}° | VRAM: ${used_gib}/${total_gib} GiB | Power: ${pwr}W\"}"
}

_amd() {
    local card
    for card in /sys/class/drm/card[0-9]*/device; do
        [[ -f "${card}/gpu_busy_percent" ]] || continue

        local util
        util=$(cat "${card}/gpu_busy_percent") || continue

        # Temperature: hwmon stores millidegrees C
        local temp_file temp_str
        temp_file=$(ls "${card}"/hwmon/hwmon*/temp1_input 2>/dev/null | head -1 || true)
        if [[ -n "${temp_file}" ]]; then
            local temp_raw
            temp_raw=$(awk "BEGIN {printf \"%.0f\", $(cat "${temp_file}")/1000}")
            temp_str="${temp_raw}°"
        else
            temp_str=""
        fi

        # VRAM in bytes; iGPU may report 0 (shared system RAM)
        local vram_used vram_total mem_str
        vram_used=$(cat "${card}/mem_info_vram_used" 2>/dev/null || echo 0)
        vram_total=$(cat "${card}/mem_info_vram_total" 2>/dev/null || echo 0)

        if [[ "${vram_total}" -gt 0 ]]; then
            local used_gib total_gib
            used_gib=$(awk "BEGIN {printf \"%.1f\", ${vram_used}/1073741824}")
            total_gib=$(awk "BEGIN {printf \"%.1f\", ${vram_total}/1073741824}")
            mem_str="${used_gib}/${total_gib}G"
        else
            mem_str="shared"
        fi

        local thermo vram_icon
        thermo=$(printf '\ue350')
        vram_icon=$(printf '\U000F0620')

        local text
        if [[ -n "${temp_str}" ]]; then
            text="${util}% ${thermo}${temp_str} ${vram_icon} ${mem_str}"
        else
            text="${util}% ${vram_icon} ${mem_str}"
        fi

        echo "{\"text\":\"${text}\",\"tooltip\":\"Util: ${util}% | Temp: ${temp_str} | VRAM: ${mem_str}\"}"
        return 0
    done
    return 1
}

if ! _nvidia; then
    if ! _amd; then
        # No supported GPU detected (e.g. Intel iGPU only).
        # Emit no output so waybar hides the module rather than showing N/A.
        exit 0
    fi
fi
