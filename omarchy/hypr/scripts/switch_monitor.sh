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
# The script is reached from a hotkey, so stdout/stderr go nowhere a human can
# see. printf stays (it is the journal record when run by hand) and Omarchy's
# own channels are added: a notification for anything the user must act on, and
# the OSD for the one-line "which preset am I on now" confirmation.
log_die()  { printf '%s  ✘ %s%s\n'   "$RD" "$1" "$RS" >&2
             omarchy-notification-send -g 󰍹 -u critical "Monitor preset" "$1" >/dev/null 2>&1 || true
             exit 1; }
log_warn() { printf '%s  ! %s%s%s\n' "$AM" "$WH" "$1" "$RS" >&2
             omarchy-notification-send -g 󰍹 "Monitor preset" "$1" >/dev/null 2>&1 || true; }
osd()      { omarchy-osd -i display -m "$1" -d 2000 >/dev/null 2>&1 || true; }

readonly CONFIG_DIR="$HOME/.config/hypr"
readonly MONITORS_CONF="$CONFIG_DIR/monitors.lua"

if [[ -z "${1:-}" ]]; then
    printf '%s  Usage: %s <preset>%s\n'   "$AM" "$(basename "$0")" "$RS" >&2
    printf '%s  Presets: bedroom, kitchen, K, pc, laptop, stock%s\n' "$AM" "$RS" >&2
    printf '%s  Example: %s bedroom%s\n' "$AM" "$(basename "$0")" "$RS" >&2
    exit 1
fi

# Whitelist preset names to prevent path traversal via $1.
if [[ ! "$1" =~ ^[A-Za-z0-9_-]+$ ]]; then
    log_die "Invalid preset name: '$1' (allowed: A-Z, a-z, 0-9, _, -)"
fi

# `stock` (or `omarchy`) puts Omarchy's own monitors.lua back — the last real
# monitors.lua, saved just before a preset replaced it. Restored as a
# real file, not a link: Omarchy owns that path and its own tooling writes to
# it. Written via a temp file + mv so monitors.lua is never momentarily absent.
if [[ "$1" == stock || "$1" == omarchy ]]; then
    SOURCE="$CONFIG_DIR/monitors.lua.stock"
    [[ -f "$SOURCE" ]] ||
        log_die "No saved monitors.lua at $SOURCE — restore Omarchy's own default with: omarchy refresh config hypr/monitors.lua"

    log_step "Restoring Omarchy's own monitor layout"
    cp -- "$SOURCE" "$MONITORS_CONF.tmp"
    mv -f -- "$MONITORS_CONF.tmp" "$MONITORS_CONF"
    hyprctl reload
    log_ok "Omarchy's monitors.lua restored"
    osd "Monitor: stock"
    exit 0
fi

# Preset resolution, in order:
#   pcMonitors.<name>.lua  — the named presets (bedroom, kitchen, K)
#   <name>Monitors.lua     — hyprconf's two whole-machine presets, reached as
#                            `pc` and `laptop`. hyprconf's own setup.sh picked
#                            between them by chassis detection at install time;
#                            the overlay never touches the active layout, so
#                            they are selected by name here instead.
#   pcMonitors.<name>      — pre-0.57-deprecation hyprlang custom presets
SOURCE="$CONFIG_DIR/pcMonitors.$1.lua"
[[ -f "$SOURCE" ]] || SOURCE="$CONFIG_DIR/${1}Monitors.lua"
[[ -f "$SOURCE" ]] || SOURCE="$CONFIG_DIR/pcMonitors.$1"
[[ -f "$SOURCE" ]] || log_die "Preset not found: pcMonitors.$1(.lua)"

log_step "Switching monitor config to: $1"

# Re-take the stock snapshot HERE, at the one moment the real monitors.lua is
# about to be unlinked. The installer's snapshot is taken once, on first
# install, and monitors.lua drifts after it: Omarchy keeps writing to that path
# (omarchy-hyprland-monitor-scaling seds the scale lines in place), so by the
# time a preset is first chosen the installer's copy can be missing outputs
# that are live right now. Taking it at the point of destruction is the only
# timing that cannot go stale. Temp file + mv so a failed copy can never leave
# a truncated .stock behind.
if [[ -f "$MONITORS_CONF" && ! -L "$MONITORS_CONF" ]]; then
    cp -- "$MONITORS_CONF" "$MONITORS_CONF.stock.tmp"
    mv -f -- "$MONITORS_CONF.stock.tmp" "$MONITORS_CONF.stock"
    log_ok "Saved the live monitors.lua -> monitors.lua.stock"
fi

# Symlink monitors.lua → preset file so later edits land on the tracked preset
# and persist when it is re-selected.
ln -sfn "$SOURCE" "$MONITORS_CONF"

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
    log_step "Output(s) still dark after reload — re-issuing a dpms wake"
    for delay in 1 2 3; do
        # `hyprctl dispatch dpms on` is a Hyprland 0.55-ism: under the Lua
        # parser the two-token form is a syntax error (exit 7) and this
        # recovery never ran at all. This is the form Omarchy itself uses
        # (omarchy-hyprland-monitor-internal). The off half is dropped — a
        # wake is what re-drives the modeset, and blanking first risked
        # leaving a genuinely dead output dark.
        hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })' >/dev/null 2>&1 || true
        sleep "$delay"
        all_lit && break
    done
    all_lit || log_warn "Some outputs may still be dark — check hyprland.log"
fi

log_ok "Monitor preset '$1' active — Hyprland reloaded."
osd "Monitor: $1"
