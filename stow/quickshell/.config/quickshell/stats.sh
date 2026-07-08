#!/usr/bin/env bash
# Streaming cpu / memory / network stats for the quickshell bar: one JSON
# line per second on stdout. Long-lived so counters can be diffed in-process
# instead of re-forking a sampler every poll.
set -u

# System paths and pacing are env-overridable so the hermetic test suite can
# point them at a fake tree (never readonly — see testing rules).
: "${HYPRCONF_STATS_NET_ROOT:=/sys/class/net}"
: "${HYPRCONF_STATS_PROC_STAT:=/proc/stat}"
: "${HYPRCONF_STATS_PROC_MEMINFO:=/proc/meminfo}"
: "${HYPRCONF_STATS_INTERVAL:=1}"
: "${HYPRCONF_STATS_ITERATIONS:=0}"   # 0 = run forever; N = exit after N samples

# SI-decimal size with an arbitrary unit suffix (e.g. "46.2kB/s", "1.3GB").
human() {
    local b=$1 u=${2:-B/s}
    if   (( b < 1000 ));       then printf '%d%s' "$b" "$u"
    elif (( b < 1000000 ));    then printf '%d.%dk%s' $(( b / 1000 )) $(( (b % 1000) / 100 )) "$u"
    elif (( b < 1000000000 )); then printf '%d.%dM%s' $(( b / 1000000 )) $(( (b % 1000000) / 100000 )) "$u"
    else                            printf '%d.%dG%s' $(( b / 1000000000 )) $(( (b % 1000000000) / 100000000 )) "$u"
    fi
}

# kB -> GiB with one decimal, matching waybar's {used:0.1f}.
gib() {
    local g10=$(( ($1 * 10 + 524288) / 1048576 ))
    printf '%d.%d' $(( g10 / 10 )) $(( g10 % 10 ))
}

prev_total=0 prev_idle=0 prev_rx=0 prev_tx=0
first=1 iter=0

while :; do
    # ---- cpu: aggregate line of /proc/stat
    read -r _ user nice system idle iowait irq softirq steal _ < "$HYPRCONF_STATS_PROC_STAT"
    total=$(( user + nice + system + idle + iowait + irq + softirq + steal ))
    idle_all=$(( idle + iowait ))
    dtotal=$(( total - prev_total ))
    didle=$(( idle_all - prev_idle ))
    cpu=0
    (( dtotal > 0 )) && cpu=$(( (100 * (dtotal - didle) + dtotal / 2) / dtotal ))
    prev_total=$total prev_idle=$idle_all

    # ---- memory: used = MemTotal - MemAvailable (same as waybar)
    mem_total=0 mem_avail=0
    while read -r key val _; do
        case $key in
            MemTotal:)     mem_total=$val ;;
            MemAvailable:) mem_avail=$val; break ;;
        esac
    done < "$HYPRCONF_STATS_PROC_MEMINFO"
    mem="$(gib $(( mem_total - mem_avail )))/$(gib "$mem_total")G"

    # ---- network. Ethernet takes precedence: if any wired interface has a
    # link up, show it (icon + rates); otherwise fall back to the default-
    # route interface (Wi-Fi / other).
    iface="" net=off
    for _d in "$HYPRCONF_STATS_NET_ROOT"/*; do
        _n=${_d##*/}
        [[ $_n == lo ]] && continue
        [[ -d $_d/wireless ]] && continue        # not Wi-Fi
        [[ -e $_d/device ]] || continue          # skip virtual (veth/docker/…)
        # NB: `$(<file 2>/dev/null)` silently captures "" on bash 5.3 (known
        # quirk) — read the file with `read`, which also avoids a fork.
        _op=""
        [[ -r $_d/operstate ]] && read -r _op < "$_d/operstate"
        if [[ $_op == up ]]; then
            iface=$_n net=eth
            break
        fi
    done
    if [[ -z $iface ]]; then
        # The iface is the token after "dev", NOT a fixed field: gateway-less
        # default routes (WireGuard/OpenVPN tunnels — "default dev wg0 scope
        # link") carry no "via <gw>", which shifts a $5-based parse onto
        # "scope"/"link" and made the bar claim "Disconnected" mid-VPN.
        iface=$(ip route show default 2>/dev/null \
            | awk '{for (i = 1; i < NF; i++) if ($i == "dev") { print $(i + 1); exit }}')
        if [[ -n $iface ]]; then
            [[ -d $HYPRCONF_STATS_NET_ROOT/$iface/wireless ]] && net=wifi || net=eth
        fi
    fi
    rx=0 tx=0
    if [[ -n $iface && -r $HYPRCONF_STATS_NET_ROOT/$iface/statistics/rx_bytes ]]; then
        read -r rx < "$HYPRCONF_STATS_NET_ROOT/$iface/statistics/rx_bytes"
        read -r tx < "$HYPRCONF_STATS_NET_ROOT/$iface/statistics/tx_bytes"
    else
        net=off
    fi
    drx=$(( rx - prev_rx )) dtx=$(( tx - prev_tx ))
    (( drx < 0 )) && drx=0
    (( dtx < 0 )) && dtx=0
    prev_rx=$rx prev_tx=$tx

    # First sample has no baseline for the deltas — skip it.
    if (( first )); then
        first=0
    else
        printf '{"cpu":%d,"mem":"%s","net":"%s","down":"%s","up":"%s"}\n' \
            "$cpu" "$mem" "$net" "$(human "$drx")" "$(human "$dtx")"
        if (( HYPRCONF_STATS_ITERATIONS > 0 && ++iter >= HYPRCONF_STATS_ITERATIONS )); then
            exit 0
        fi
    fi

    sleep "$HYPRCONF_STATS_INTERVAL"
done
