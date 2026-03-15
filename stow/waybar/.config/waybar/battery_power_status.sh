#!/usr/bin/env bash
set -euo pipefail

battery_path=$(upower -e | grep battery_BAT || true)

if [[ -z "$battery_path" ]]; then
    echo '{"text":"󱐋", "class":"ac"}'
    exit 0
fi

battery_info=$(upower -i "$battery_path")

power_draw=$(echo "$battery_info"        | grep -i "energy-rate"  | awk '{print $2}')
battery_percentage=$(echo "$battery_info" | grep -i "percentage"  | awk '{print $2}')
state=$(echo "$battery_info"              | grep -i "state"        | awk '{print $2}')

power_draw=$(printf "%.2f" "${power_draw:-0}")
capacity_num=${battery_percentage%\%}

if   (( capacity_num > 90 )); then icon="󰁹"
elif (( capacity_num > 80 )); then icon="󰂁"
elif (( capacity_num > 60 )); then icon="󰁿"
elif (( capacity_num > 40 )); then icon="󰁽"
elif (( capacity_num > 20 )); then icon="󰁻"
else                               icon="󰂎"
fi

if   [[ "$state" == "charging" ]]; then cls="charging"
elif (( capacity_num <= 15 ));     then cls="critical"
elif (( capacity_num <= 30 ));     then cls="warning"
else                                    cls="normal"
fi

echo "{\"text\":\"$icon $battery_percentage ($power_draw W)\", \"class\":\"$cls\"}"
