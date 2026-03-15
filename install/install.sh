#!/usr/bin/env bash
#
#  hyprconf — bootstrap installer
#  hosted at: https://hyprconf.ak4.io
#
#  usage:
#    bash <(curl -fsSL https://hyprconf.ak4.io)
#
#  This file is intentionally static. It clones the repo once, then hands
#  off entirely to setup.sh — which owns all install logic. As long as
#  REPO_URL below stays valid, this file will never need to be re-uploaded.

set -euo pipefail

# ── The only value this file will ever contain that could become stale ────────
# (The canonical banner lives in assets/banner.sh; this file embeds it inline
#  so install.sh stays a single self-contained script suitable for curl piping.
#  Keep them in sync when modifying the banner.)
readonly REPO_URL="https://github.com/ak4dev/.hyprconf"
readonly REPO_DIR="$HOME/.hyprconf"

# ── Palette: digital phosphor glitch ─────────────────────────────────────────
#   WH  bright white   — main logo body
#   GL  bright red     — corrupted scanline artifact
#   NG  dim green      — noise / static borders
#   AM  amber          — sys info text
#   GR  bright green   — ok / success
#   DM  dim white      — fading / low-power
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

  # — top noise line
  printf '%s  ▒░▒▓▒░░▒▓░░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░▒▓%s\n' "$NG" "$RS"

  # — .hyprconf logo in standard ASCII-art lowercase font
  #   The (_) glyph on rows 4-5 is the figlet rendering of the leading '.'
  #   Row 3 is intentionally glitch-red — corrupted scanline artifact
  printf '%s         _                                        __%s\n'                        "$DM" "$RS"
  printf '%s        | |__  _   _ _ __  _ __ ___ ___  _ __  / _|%s\n'                       "$WH" "$RS"
  printf "%s        | '_ \\| | | | '_ \\| '__/ __/ _ \\| '_ \\| |_%s\n"                     "$GL" "$RS"
  printf '%s  _     | | | | |_| | |_) | | | (_| (_) | | | |  _|%s\n'                       "$WH" "$RS"
  printf '%s (_)    |_| |_|\__, | .__/|_|  \___\___/|_| |_||_|%s\n'                        "$DM" "$RS"
  printf '%s               |___/|_|%s\n'                                                    "$DM" "$RS"

  # — bottom noise line + sys info
  printf '%s  ▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓▒░▒▓░░▒▓░▒▓░▒▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓░░▒▓░▒▓░▒▓%s\n' "$NG" "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────────────%s\n'   "$DM" "$RS"
  printf '%s  [ SYS ] arch linux + hyprland dotfiles bootstrap              ak4.io\n'      "$AM"
  printf    '  [ SYS ] signal: stable   origin: github.com/ak4dev/.hyprconf%s\n'           "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────────────%s\n\n' "$DM" "$RS"
}

# ── Logging ───────────────────────────────────────────────────────────────────
log_step() { printf '%s  ▸ %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_ok()   { printf '%s  ✔ %s%s%s\n'        "$GR" "$WH" "$1" "$RS"; }
log_warn() { printf '%s  ! %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_die()  { printf '%s  ✘ FATAL: %s%s%s\n' "$GL" "$WH" "$1" "$RS" >&2; exit 1; }

# ── Steps ─────────────────────────────────────────────────────────────────────
check_arch() {
  log_step "Verifying system..."
  [[ -f /etc/arch-release ]] \
    || log_die "Arch Linux required. Detected: $(uname -s -r)."
  log_ok "Arch Linux confirmed."
}

ensure_git() {
  if command -v git &>/dev/null; then
    log_ok "git $(git --version | awk '{print $3}')"
    return 0
  fi
  log_step "Installing git..."
  sudo pacman -Sy --noconfirm --needed git \
    || log_die "pacman could not install git."
  log_ok "git installed."
}

get_repo() {
  if [[ -d "$REPO_DIR/.git" ]]; then
    log_step "Existing repo found — pulling latest..."
    git -C "$REPO_DIR" pull --ff-only \
      || log_warn "Fast-forward failed — continuing with existing files."
  else
    log_step "Cloning $REPO_URL → $REPO_DIR ..."
    git clone --depth=1 "$REPO_URL" "$REPO_DIR" \
      || log_die "Clone failed. Check your network connection."
  fi
  log_ok "Repository ready."
}

run_setup() {
  log_step "Handing off to setup.sh ..."
  printf '\n'
  HYPRCONF_INSTALLER=1 bash "$REPO_DIR/setup.sh"
}

# ── Entry ─────────────────────────────────────────────────────────────────────
main() {
  print_banner
  check_arch
  ensure_git
  get_repo
  run_setup
}

main "$@"
