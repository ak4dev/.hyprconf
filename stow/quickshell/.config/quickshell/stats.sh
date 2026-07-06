#!/usr/bin/env bash
# Streaming cpu / memory / network stats for the quickshell bar: one JSON
# line per second on stdout. Long-lived so counters can be diffed in-process
# instead of re-forking a sampler every poll.
set -u

# SI-decimal bandwidth, matching waybar's {bandwidthDownBytes} rendering
# (e.g. "46.2kB/s").
human() {
    local b=$1
    if   (( b < 1000 ));       then printf '%dB/s' "$b"
    elif (( b < 1000000 ));    then printf '%d.%dkB/s' $(( b / 1000 )) $(( (b % 1000) / 100 ))
    elif (( b < 1000000000 )); then printf '%d.%dMB/s' $(( b / 1000000 )) $(( (b % 1000000) / 100000 ))
    else                            printf '%d.%dGB/s' $(( b / 1000000000 )) $(( (b % 1000000000) / 100000000 ))
    fi
}

# kB -> GiB with one decimal, matching waybar's {used:0.1f}.
gib() {
    local g10=$(( ($1 * 10 + 524288) / 1048576 ))
    printf '%d.%d' $(( g10 / 10 )) $(( g10 % 10 ))
}

prev_total=0 prev_idle=0 prev_rx=0 prev_tx=0
first=1

while :; do
    # ---- cpu: aggregate line of /proc/stat
    read -r _ user nice system idle iowait irq softirq steal _ < /proc/stat
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
    done < /proc/meminfo
    mem="$(gib $(( mem_total - mem_avail )))/$(gib "$mem_total")G"

    # ---- network: default-route interface
    iface=$(ip route show default 2>/dev/null | awk '{print $5; exit}')
    net=off rx=0 tx=0
    if [[ -n $iface && -r /sys/class/net/$iface/statistics/rx_bytes ]]; then
        rx=$(< "/sys/class/net/$iface/statistics/rx_bytes")
        tx=$(< "/sys/class/net/$iface/statistics/tx_bytes")
        if [[ -d /sys/class/net/$iface/wireless ]]; then net=wifi; else net=eth; fi
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
    fi

    sleep 1
done
