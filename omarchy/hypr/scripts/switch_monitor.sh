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
readonly MONITORS_CONF="$CONFIG_DIR/monitors.lua"

if [[ -z "${1:-}" ]]; then
    printf '%s  Usage: %s <preset>%s\n'   "$AM" "$(basename "$0")" "$RS" >&2
    printf '%s  Example: %s bedroom%s\n' "$AM" "$(basename "$0")" "$RS" >&2
    exit 1
fi

# Whitelist preset names to prevent path traversal via $1.
if [[ ! "$1" =~ ^[A-Za-z0-9_-]+$ ]]; then
    log_die "Invalid preset name: '$1' (allowed: A-Z, a-z, 0-9, _, -)"
fi

# Prefer the Lua preset; fall back to the (pre-0.57-deprecation) hyprlang
# variant for any custom preset a user made before this migration.
SOURCE="$CONFIG_DIR/pcMonitors.$1.lua"
[[ -f "$SOURCE" ]] || SOURCE="$CONFIG_DIR/pcMonitors.$1"
[[ -f "$SOURCE" ]] || log_die "Preset not found: pcMonitors.$1(.lua)"

log_step "Switching monitor config to: $1"

# Symlink monitors.lua → preset file so the TUI writes go directly to the
# tracked preset (edits persist when the preset is re-selected later).
ln -sf "$SOURCE" "$MONITORS_CONF"

hyprctl reload

# An output flipping disabled→enabled through this same reload path can hit
# the identical failed-CRTC-restore bug documented in hyprland-wake-restore
# (aquamarine/nvidia-open: ATOMIC modeset commit rejected with EINVAL) —
# Hyprland's config believes the panel is on, but the physical display never
# got a real modeset and stays dark until unplug/replug forces a fresh HPD
# probe. Verify against the kernel's own connector state and force a dpms
# off/on cycle while any output that should be lit isn't.
is_lit() {
    local name=$1 f found=0
    for f in /sys/class/drm/card*-"$name"/enabled; do
        [[ -e "$f" ]] || continue
        found=1
        [[ "$(<"$f")" == "enabled" ]] && return 0
    done
    ((found == 0))
}

all_lit() {
    local mons name
    mons=$(hyprctl monitors 2>/dev/null | awk '/^Monitor /{print $2}')
    [[ -n "$mons" ]] || return 1
    while IFS= read -r name; do
        is_lit "$name" || return 1
    done <<<"$mons"
}

# Only verify when hyprctl actually reports monitors — an empty/absent IPC
# (or a test double) means there's nothing meaningful to check.
if hyprctl monitors 2>/dev/null | grep -q "^Monitor " && ! all_lit; then
    log_step "Output(s) still dark after reload — forcing a fresh modeset"
    for delay in 1 2 3; do
        hyprctl dispatch dpms off >/dev/null 2>&1 || true
        sleep 0.3
        hyprctl dispatch dpms on >/dev/null 2>&1 || true
        sleep "$delay"
        all_lit && break
    done
    all_lit || log_step "Warning: some output(s) may still be dark — check hyprland.log"
fi

log_ok "Monitor preset '$1' active — Hyprland reloaded."
