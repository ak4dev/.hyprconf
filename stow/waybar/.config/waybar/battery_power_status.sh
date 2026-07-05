#!/usr/bin/env bash
set -euo pipefail

# Battery status for waybar. Polled every second, so it must stay cheap: reads
# /sys/class/power_supply directly in pure bash — zero subprocesses per poll
# (the old upower version spawned ~12 processes and two D-Bus round trips).
# Root is env-overridable so hermetic tests can point it at a fake tree.
_PS_ROOT="${HYPRCONF_PS_ROOT:-/sys/class/power_supply}"

battery=""
for d in "$_PS_ROOT"/BAT*; do
    [[ -r "$d/capacity" ]] && battery="$d" && break
done

if [[ -z "$battery" ]]; then
    echo '{"text":"󱐋", "class":"ac"}'
    exit 0
fi

capacity_num="$(< "$battery/capacity")"
state=""
[[ -r "$battery/status" ]] && state="$(< "$battery/status")"
state="${state,,}"

# Power draw in W: power_now is µW; older ACPI batteries expose only
# current_now (µA) × voltage_now (µV) instead. Sign varies by driver — use the
# magnitude, like upower's energy-rate did.
pw=0
if [[ -r "$battery/power_now" ]]; then
    pw="$(< "$battery/power_now")"
elif [[ -r "$battery/current_now" && -r "$battery/voltage_now" ]]; then
    pw=$(( $(< "$battery/current_now") * $(< "$battery/voltage_now") / 1000000 ))
fi
(( pw < 0 )) && pw=$(( -pw ))
# Round µW to two decimals of W without spawning printf-external tools.
pw=$(( (pw + 5000) / 10000 ))
printf -v power_draw '%d.%02d' $(( pw / 100 )) $(( pw % 100 ))

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

echo "{\"text\":\"$icon ${capacity_num}% ($power_draw W)\", \"class\":\"$cls\"}"
