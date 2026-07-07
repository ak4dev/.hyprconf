#!/usr/bin/env bash
set -euo pipefail

# CPU temperature for the quickshell bar. Polled every 2s, so keep it to a single
# `sensors` invocation and one awk pass (the old version re-ran sensors for
# each label probe — up to four times per poll).
command -v sensors &>/dev/null || exit 0

# Probe priority (first match on the FIRST line carrying each label wins):
#   Tctl / Tdie  — AMD k10temp
#   Package id 0 — Intel coretemp (overall package)
#   Core 0       — Intel coretemp fallback (first physical core)
cpu_temp="$(sensors 2>/dev/null | awk '
    BEGIN { best = 99 }
    function temp(line,    i, n, f) {
        n = split(line, f, /[[:space:]]+/)
        for (i = 1; i <= n; i++)
            if (f[i] ~ /^\+[0-9]+(\.[0-9]+)?°C$/) {
                gsub(/[+°C]/, "", f[i])
                return sprintf("%.0f", f[i] + 0)
            }
        return ""
    }
    function take(rank,    t) {
        if (best <= rank) return
        t = temp($0)
        if (t != "") { v = t; best = rank }
    }
    /Tctl/         { take(1) }
    /Tdie/         { take(2) }
    /Package id 0/ { take(3) }
    /Core 0/       { take(4) }
    END { if (best < 99) print v }
')"

# No readable temperature source — hide the module instead of showing N/A.
[[ -n "$cpu_temp" ]] || exit 0

echo "{\"text\":\"${cpu_temp}°\"}"
