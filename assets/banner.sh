#!/usr/bin/env bash
#
#  assets/banner.sh — reusable .hyprconf project banner
#
#  Source this file to get the print_banner() function and the shared
#  colour palette used across all hyprconf scripts.
#
#  Usage:
#    source "$(git rev-parse --show-toplevel)/assets/banner.sh"
#    print_banner
#
#  The hosted installer (install/install.sh) embeds this function inline
#  so it stays a single self-contained file.  Keep both in sync when
#  changing the banner.

# ── Palette: digital phosphor glitch ─────────────────────────────────────────
#   WH  bright white   — main logo body
#   GL  bright red     — corrupted scanline artifact
#   NG  dim green      — noise / static borders
#   AM  amber          — sys info text / step prompts
#   GR  bright green   — ok / success
#   DM  dim white      — fading / low-power rows
#   RS  reset
if [[ -t 1 ]]; then
  WH=$'\e[1;37m' GL=$'\e[1;31m' NG=$'\e[2;32m'
  AM=$'\e[1;33m' GR=$'\e[1;32m' DM=$'\e[2;37m' RS=$'\e[0m'
else
  WH='' GL='' NG='' AM='' GR='' DM='' RS=''
fi

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
  printf '\033[H\033[2J'   # clear + cursor home

  # top noise line
  printf '%s  ▒░▒▓▒░░▒▓░░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░▒▓%s\n' "$NG" "$RS"

  # .hyprconf logo — standard ASCII-art lowercase font
  # The (_) glyph on rows 4–5 is the figlet rendering of the leading '.'
  # Row 3 is glitch-red: the corrupted-scanline artifact
  printf '%s         _                                        __%s\n'                   "$DM" "$RS"
  printf '%s        | |__  _   _ _ __  _ __ ___ ___  _ __  / _|%s\n'                  "$WH" "$RS"
  printf "%s        | '_ \\| | | | '_ \\| '__/ __/ _ \\| '_ \\| |_%s\n"                "$GL" "$RS"
  printf '%s       _| | | | |_| | |_) | | | (_| (_) | | | |  _|%s\n'                  "$WH" "$RS"
  printf '%s     (_)|_| |_|\__, | .__/|_|  \___\___/|_| |_||_|%s\n'                   "$DM" "$RS"
  printf '%s               |___/|_|%s\n'                                               "$DM" "$RS"

  # bottom noise line + sys info
  printf '%s  ▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓▒░▒▓░░▒▓░▒▓░▒▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓░░▒▓░▒▓░▒▓%s\n' "$NG" "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────────────%s\n'   "$DM" "$RS"
  printf '%s  [ SYS ] arch linux + hyprland dotfiles bootstrap         hyprconf.sh\n'      "$AM"
  printf    '  [ SYS ] signal: stable   origin: github.com/ak4dev/.hyprconf%s\n'           "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────────────%s\n\n' "$DM" "$RS"
}
