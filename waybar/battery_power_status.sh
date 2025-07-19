#!/bin/bash

battery_info=$(upower -i /org/freedesktop/UPower/devices/battery_BAT0)

power_draw=$(echo "$battery_info" | grep -i "energy-rate" | awk '{print $2}')
battery_percentage=$(echo "$battery_info" | grep -i "percentage" | awk '{print $2}')
state=$(echo "$battery_info" | grep -i "state" | awk '{print $2}')

power_draw=$(printf "%.2f" "$power_draw")
capacity_num=${battery_percentage%\%}

# Pick icon same as before
if (( capacity_num > 90 )); then
    icon="󰁹"
elif (( capacity_num > 80 )); then
    icon="󰁹"
elif (( capacity_num > 60 )); then
    icon="󰁿"
elif (( capacity_num > 40 )); then
    icon="󰁽"
elif (( capacity_num > 20 )); then
    icon="󰁻"
else
    icon="󰂎"
fi

# Assign class for color
if [[ "$state" == "charging" ]]; then
    cls="charging"
elif (( capacity_num <= 15 )); then
    cls="critical"
elif (( capacity_num <= 30 )); then
    cls="warning"
else
    cls="normal"
fi

# Output JSON
echo "{\"text\":\"$icon $battery_percentage ($power_draw W)\", \"class\":\"$cls\"}"
