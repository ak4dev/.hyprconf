#!/usr/bin/env bash
set -euo pipefail

cpu_temp=$(sensors | grep 'Tctl' | awk '{print $2}' | cut -c 2-5)

if [[ -z "$cpu_temp" || "$cpu_temp" == "N/A" ]]; then
    echo '{"cpu_temp": "N/A"}'
else
    echo "{\"cpu_temp\": \"$cpu_temp\"}"
fi
