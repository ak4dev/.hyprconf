#!/usr/bin/env bash
set -euo pipefail

# ── Palette (degraded gracefully when not a tty) ──────────────────────────────
if [[ -t 1 ]]; then
    AM=$'\033[38;2;255;184;108m'   # amber
    GR=$'\033[38;2;80;250;123m'    # green
    RD=$'\033[38;2;255;85;85m'     # red
    WH=$'\033[38;2;248;248;242m'   # white
    RS=$'\033[0m'                  # reset
else
    AM=''; GR=''; RD=''; WH=''; RS=''
fi

log_step() { printf '%s  ▸ %s%s%s\n' "$AM" "$WH" "$1" "$RS"; }
log_ok()   { printf '%s  ✔ %s%s%s\n' "$GR" "$WH" "$1" "$RS"; }
log_die()  { printf '%s  ✘ %s%s\n'   "$RD" "$1" "$RS" >&2; exit 1; }

readonly CONFIG_DIR="$HOME/.config/hypr"
readonly MONITORS_CONF="$CONFIG_DIR/monitors.conf"

if [[ -z "${1:-}" ]]; then
    printf '%s  Usage: %s <preset>%s\n'   "$AM" "$(basename "$0")" "$RS" >&2
    printf '%s  Example: %s bedroom%s\n' "$AM" "$(basename "$0")" "$RS" >&2
    exit 1
fi

SOURCE="$CONFIG_DIR/pcMonitors.$1"
[[ -f "$SOURCE" ]] || log_die "Preset not found: pcMonitors.$1"

log_step "Switching monitor config to: $1"

# Write directly to monitors.conf, replacing any existing symlink or file.
# This avoids overwriting the stow-tracked pcMonitors.conf source.
cp "$SOURCE" "${MONITORS_CONF}.tmp"
mv "${MONITORS_CONF}.tmp" "$MONITORS_CONF"

hyprctl reload
log_ok "Monitor preset '$1' active — Hyprland reloaded."
