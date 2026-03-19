#!/usr/bin/env bash
set -euo pipefail

# sensors is required; hide the module gracefully if it isn't installed.
command -v sensors &>/dev/null || exit 0

# Extract the first "+XX.X°C" token from a sensors output line.
# Works regardless of where on the line the temperature appears.
_extract_temp() {
    awk '{for(i=1;i<=NF;i++) if($i~/^\+[0-9]+(\.[0-9]+)?°C$/) {
        gsub(/[+°C]/,"",$i); printf "%.0f", $i+0; exit }}'
}

# Probe in priority order:
#   Tctl / Tdie  — AMD k10temp
#   Package id 0 — Intel coretemp (overall package)
#   Core 0       — Intel coretemp fallback (first physical core)
cpu_temp=""
for label in "Tctl" "Tdie" "Package id 0" "Core 0"; do
    t=$(sensors 2>/dev/null | grep -m1 "${label}" | _extract_temp) || true
    if [[ -n "$t" ]]; then
        cpu_temp="$t"
        break
    fi
done

# No readable temperature source — hide the module instead of showing N/A.
[[ -n "$cpu_temp" ]] || exit 0

echo "{\"text\":\"${cpu_temp}°\"}"
