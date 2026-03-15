#!/usr/bin/env bash
set -euo pipefail

cpu_temp=$(sensors | grep 'Tctl' | awk '{print $2}' | cut -c 2-5)

if [[ -z "$cpu_temp" || "$cpu_temp" == "N/A" ]]; then
    echo '{"text":"N/A"}'
else
    temp_int=$(printf "%.0f" "${cpu_temp}")
    echo "{\"text\":\"${temp_int}°\"}"
fi
