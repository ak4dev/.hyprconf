#!/usr/bin/env bash
#
#  hyprconf — universal installer
#  hosted at: https://hyprconf.sh
#
#  usage:
#    bash <(curl -fsSL https://hyprconf.sh)
#
#  Presents three modes after the banner:
#    [1] Full Arch Linux install  (run from the Arch ISO)
#        Partitions disk, LUKS2 encrypts, creates btrfs subvolumes, installs
#        base system, configures with systemd-boot, then stages dotfiles for
#        automatic setup on first login.
#    [2] Dotfiles only  (existing Arch installation)
#        Clones the repo and hands off to setup.sh — original behaviour.
#    [3] hyprconf only  (any existing Hyprland system)
#        Installs the hyprconf CLI/TUI into ~/.local/bin and ~/.local/lib
#        without touching any Hyprland config files.

set -euo pipefail

readonly REPO_URL="https://github.com/ak4dev/.hyprconf"
readonly REPO_DIR="$HOME/.hyprconf"
readonly REPO_STABLE_BRANCH="stable"
readonly REPO_COMPAT_BRANCH="mainline"
readonly LUKS_NAME="cryptroot"
readonly BTRFS_OPTS="noatime,compress=zstd,space_cache=v2"
declare -ra REPO_SPARSE_PATHS=(
  /README.md
  /assets
  /docs
  /infra
  /install
  /packages
  /setup.sh
  /stow
  /theme
)

# Collected during prompts — must remain mutable (not readonly)
DISK=""
EFI_PART=""
ROOT_PART=""
PART_MODE=""
USERNAME=""
USER_PASSWORD=""
USER_HOSTNAME=""
TIMEZONE=""
CPU_UCODE=""

# Installer options (PHASE 1 only)
COPY_NETCONF=1

# ── CI / non-interactive mode ─────────────────────────────────────────────────
# Set HYPRCONF_CI=1 to bypass all interactive prompts.
# All variables can be pre-set via env vars; defaults are shown below.
#
#   HYPRCONF_CI=1
#   HYPRCONF_CI_DISK=/dev/vda          # required — no default
#   HYPRCONF_CI_USERNAME=hyprtest
#   HYPRCONF_CI_PASSWORD=hyprtest
#   HYPRCONF_CI_HOSTNAME=hyprconf-test
#   HYPRCONF_CI_TIMEZONE=UTC
#   HYPRCONF_CI_PART_MODE=full         # full | unallocated
#   HYPRCONF_CI_SSH_PUBKEY=            # optional — inject authorized_keys before unmount
#   HYPRCONF_CI_REPO_TGZ=             # optional — path to repo tar.gz; skips git clone
HYPRCONF_CI="${HYPRCONF_CI:-0}"

# ── Palette ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  WH=$'\e[1;37m' GL=$'\e[1;31m' NG=$'\e[2;32m'
  AM=$'\e[1;33m' GR=$'\e[1;32m' DM=$'\e[2;37m' RS=$'\e[0m'
else
  WH='' GL='' NG='' AM='' GR='' DM='' RS=''
fi

# ── Logging ───────────────────────────────────────────────────────────────────
log_step() { printf '%s  ▸ %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_ok()   { printf '%s  ✔ %s%s%s\n'        "$GR" "$WH" "$1" "$RS"; }
log_warn() { printf '%s  ! %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_info() { printf '%s  · %s%s%s\n'        "$DM" "$WH" "$1" "$RS"; }
log_die()  { printf '%s  ✘ FATAL: %s%s%s\n' "$GL" "$WH" "$1" "$RS" >&2; exit 1; }

apply_sparse_checkout() {
  git -C "$REPO_DIR" sparse-checkout init --no-cone >/dev/null 2>&1 || true
  git -C "$REPO_DIR" sparse-checkout set "${REPO_SPARSE_PATHS[@]}" >/dev/null
}

remote_branch_exists() {
  local branch="$1"
  git -C "$REPO_DIR" show-ref --verify --quiet "refs/remotes/origin/${branch}"
}

maybe_migrate_repo_to_stable() {
  local current_branch upstream

  git -C "$REPO_DIR" fetch --quiet origin \
    "$REPO_STABLE_BRANCH" "$REPO_COMPAT_BRANCH" 2>/dev/null || true

  current_branch="$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  upstream="$(git -C "$REPO_DIR" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"

  if [[ "$current_branch" == "dev" || "$upstream" == "origin/dev" ]]; then
    return 0
  fi

  if [[ "$current_branch" == "$REPO_COMPAT_BRANCH" ]] \
    && remote_branch_exists "$REPO_STABLE_BRANCH"; then
    if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
      log_warn "Local changes detected — leaving branch on ${REPO_COMPAT_BRANCH} for now."
      return 0
    fi

    log_step "Migrating repo checkout from ${REPO_COMPAT_BRANCH} to ${REPO_STABLE_BRANCH}..."
    if git -C "$REPO_DIR" checkout -B "$REPO_STABLE_BRANCH" \
      "origin/${REPO_STABLE_BRANCH}" >/dev/null 2>&1; then
      git -C "$REPO_DIR" branch \
        --set-upstream-to="origin/${REPO_STABLE_BRANCH}" \
        "$REPO_STABLE_BRANCH" >/dev/null 2>&1 || true
      log_ok "Now tracking ${REPO_STABLE_BRANCH}."
    else
      log_warn "Could not switch to ${REPO_STABLE_BRANCH} — staying on ${REPO_COMPAT_BRANCH}."
    fi
  fi
}

clone_repo_branch() {
  local branch="$1"
  git clone --depth=1 --single-branch --branch "$branch" --sparse "$REPO_URL" "$REPO_DIR"
  apply_sparse_checkout
}

clone_preferred_repo() {
  if clone_repo_branch "$REPO_STABLE_BRANCH"; then
    return 0
  fi

  rm -rf "$REPO_DIR"
  log_warn "${REPO_STABLE_BRANCH} is unavailable — falling back to ${REPO_COMPAT_BRANCH}."
  clone_repo_branch "$REPO_COMPAT_BRANCH" \
    || log_die "Clone failed. Check your network connection."
}

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
  printf '\033[H\033[2J'
  printf '%s  ▒░▒▓▒░░▒▓░░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░▒▓%s\n' "$NG" "$RS"
  printf '%s         _                                        __%s\n'                        "$DM" "$RS"
  printf '%s        | |__  _   _ _ __  _ __ ___ ___  _ __  / _|%s      works\n'            "$WH" "$RS"
  printf "%s        | '_ \\| | | | '_ \\| '__/ __/ _ \\| '_ \\| |_%s       on my\n"         "$GL" "$RS"
  printf '%s       _| | | | |_| | |_) | | | (_| (_) | | | |  _|%s      machine\n'          "$WH" "$RS"
  printf '%s     (_)|_| |_|\__, | .__/|_|  \___\___/|_| |_||_|%s       \xc2\xaf\\_(\xe3\x83\x84)_/\xc2\xaf\n' "$DM" "$RS"
  printf '%s               |___/|_|%s\n'                                                    "$DM" "$RS"
  printf '%s  ▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓▒░▒▓░░▒▓░▒▓░▒▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓░░▒▓░▒▓░▒▓%s\n' "$NG" "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────────────%s\n'   "$DM" "$RS"
  printf '%s  [ SYS ] arch linux + hyprland dotfiles bootstrap         hyprconf.sh\n'      "$AM"
  printf    '  [ SYS ] signal: stable   origin: github.com/ak4dev/.hyprconf%s\n'           "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────────────%s\n\n' "$DM" "$RS"
}

# ── Helper: partition device name (handles nvme/mmcblk p-suffix) ──────────────
part_dev() {
  local disk="$1" num="$2"
  [[ "$disk" == *nvme* || "$disk" == *mmcblk* ]] \
    && echo "${disk}p${num}" || echo "${disk}${num}"
}

# ── Helper: humanize bytes (best-effort) ───────────────────────────────────────
human_bytes() {
  local bytes="${1:-0}"
  if command -v numfmt &>/dev/null; then
    numfmt --to=iec-i --suffix=B "$bytes" 2>/dev/null || printf '%sB' "$bytes"
  else
    # Fallback: MiB
    printf '%sMiB' $(( bytes / 1024 / 1024 ))
  fi
}

run_timeout() {
  local seconds="$1"; shift
  if command -v timeout &>/dev/null; then
    timeout "${seconds}s" "$@"
  else
    "$@"
  fi
}

arrow_select() {
  # Prints selected 0-based index to stdout. Display and raw keyboard input
  # both go through /dev/tty directly so this works inside $() substitutions
  # and when stdin is redirected.
  # Optional: first two args may be -d <N> to set the initial cursor position.
  local default_cur=0
  if [[ "${1:-}" == "-d" ]]; then
    default_cur="${2:-0}"
    shift 2
  fi

  local prompt="$1"; shift
  local -a items=("$@")
  local n=${#items[@]}
  (( n > 0 )) || return 1

  # Open /dev/tty for display (fd 9) and for raw keyboard input (fd 8).
  { exec 9>/dev/tty; }  2>/dev/null || return 1
  { exec 8</dev/tty; }  2>/dev/null || { exec 9>&-; return 1; }
  trap 'printf "\e[?25h" >&9 2>/dev/null; exec 9>&- 8>&-' RETURN

  local cur="$default_cur"
  (( cur < 0 )) && cur=0
  (( cur >= n )) && cur=$(( n - 1 ))

  printf '\n%s  %s%s\n' "$WH" "$prompt" "$RS" >&9
  printf '%s  (↑/↓ or j/k, Enter to confirm)%s\n\n' "$DM" "$RS" >&9

  printf '\e[?25l' >&9   # hide cursor

  local first=1 key rest
  while true; do
    if (( first )); then
      first=0
    else
      # Move cursor back to the top of the list before redrawing.
      printf '\e[%dA' "$n" >&9
    fi

    local i
    for (( i=0; i<n; i++ )); do
      printf '\e[2K\r' >&9
      if (( i == cur )); then
        printf '%s  > %s%s\n' "$AM" "${items[i]}" "$RS" >&9
      else
        printf '    %s\n' "${items[i]}" >&9
      fi
    done

    IFS= read -rsn1 -u8 key || return 1
    case "$key" in
      $'\x1b')
        # Read the remainder of the escape sequence with a short timeout so a
        # bare ESC keypress does not block indefinitely.
        IFS= read -rsn2 -t0.15 -u8 rest || rest=""
        case "$rest" in
          "[A") (( cur > 0 ))     && cur=$(( cur - 1 )) ;;
          "[B") (( cur < n - 1 )) && cur=$(( cur + 1 )) ;;
        esac
        ;;
      "")
        printf '\e[?25h' >&9
        exec 9>&- 8>&-
        trap - RETURN
        printf '%s\n' "$cur"
        return 0
        ;;
      k) (( cur > 0 ))     && cur=$(( cur - 1 )) ;;
      j) (( cur < n - 1 )) && cur=$(( cur + 1 )) ;;
    esac
  done
}

# ── Passive existing-install detection ───────────────────────────────────────
# Reads only — no network, no disk writes, no side effects.
# Returns 0 if any signal of an existing hyprconf/Hyprland install is found.
detect_existing_install() {
  command -v hyprconf            &>/dev/null && return 0
  [[ -f "$HOME/.local/bin/hyprconf"         ]] && return 0
  [[ -d "$REPO_DIR/.git"                    ]] && return 0
  [[ -f "$HOME/.config/hypr/hyprland.lua"   ]] && return 0
  [[ -f "$HOME/.config/hypr/hyprland.conf"  ]] && return 0
  return 1
}

esp_candidates_on_disk() {
  local disk="$1"
  # ESP GUID: c12a7328-f81f-11d2-ba4b-00a0c93ec93b
  lsblk -lnpo NAME,PARTTYPE "$disk" 2>/dev/null \
    | awk 'tolower($2)=="c12a7328-f81f-11d2-ba4b-00a0c93ec93b"{print $1}'
}

esp_free_bytes() {
  local dev="$1"
  local mp
  mp="$(lsblk -npo MOUNTPOINT "$dev" 2>/dev/null | head -1 || true)"

  if [[ -n "${mp:-}" ]]; then
    df -B1 --output=avail "$mp" 2>/dev/null | tail -1 | tr -d ' ' || true
    return 0
  fi

  local tmp
  tmp="$(mktemp -d)"
  if run_timeout 4 mount -o ro,umask=0077 "$dev" "$tmp" 2>/dev/null; then
    df -B1 --output=avail "$tmp" 2>/dev/null | tail -1 | tr -d ' ' || true
    umount "$tmp" 2>/dev/null || true
  fi
  rmdir "$tmp" 2>/dev/null || true
}

print_esp_report() {
  local dev="$1"
  local sz fstype label free
  sz="$(lsblk -bno SIZE "$dev" 2>/dev/null | head -1 || echo 0)"
  fstype="$(lsblk -no FSTYPE "$dev" 2>/dev/null | head -1 || true)"
  label="$(lsblk -no LABEL "$dev" 2>/dev/null | head -1 || true)"
  free="$(esp_free_bytes "$dev" || true)"

  if [[ -n "${free:-}" ]]; then
    log_info "ESP: $dev  size=$(human_bytes "$sz")  free=$(human_bytes "$free")  fstype=${fstype:-?}  label=${label:-?}"
  else
    log_info "ESP: $dev  size=$(human_bytes "$sz")  free=?  fstype=${fstype:-?}  label=${label:-?}"
  fi
}

choose_free_region() {
  # Prints: "start end size" in sectors (without the 's' suffix)
  local disk="$1" need_sectors="$2"

  local sector_size
  sector_size="$(blockdev --getss "$disk" 2>/dev/null || echo 512)"

  local out rc
  set +e
  out="$(run_timeout 8 parted -m -s "$disk" unit s print free 2>/dev/null)"
  rc=$?
  set -e

  if (( rc == 124 )); then
    log_warn "Timed out reading free space map (parted) on $disk"
    return 1
  fi
  if (( rc != 0 )) || [[ -z "${out:-}" ]]; then
    log_warn "Failed to read free space map (parted) on $disk"
    return 1
  fi

  local -a regions
  mapfile -t regions < <(
    printf '%s\n' "$out" \
      | awk -F: '
          BEGIN { OFS=" " }
          /^BYT;/ { next }
          $1 ~ /^\// { next }
          {
            isfree=0
            for (i=1;i<=NF;i++) {
              v=tolower($i)
              sub(/;$/, "", v)
              if (v=="free" || v=="free space") isfree=1
            }
            if (!isfree) next
            s=$2; e=$3; z=$4
            gsub(/s/,"",s); gsub(/s/,"",e); gsub(/s/,"",z)
            if (s=="" || e=="" || z=="") next
            print s,e,z
          }'
  )

  local -a viable
  local r
  for r in "${regions[@]}"; do
    local s e z
    read -r s e z <<<"$r"
    (( z >= need_sectors )) || continue
    viable+=("$r")
  done

  (( ${#viable[@]} > 0 )) || return 1

  if (( ${#viable[@]} == 1 )); then
    printf '%s\n' "${viable[0]}"
    return 0
  fi

  # Arrow-able selector when available (dialog/fzf/arrow_select), otherwise numeric.
  local idx=1
  if command -v dialog &>/dev/null && [[ -t 1 ]]; then
    local -a opts
    for r in "${viable[@]}"; do
      local s e z
      read -r s e z <<<"$r"
      opts+=("$idx" "start=${s}s end=${e}s size=$(human_bytes $(( z * sector_size )))")
      idx=$(( idx + 1 ))
    done
    local choice
    choice="$(dialog --stdout --menu "Select unallocated region" 20 80 10 "${opts[@]}")" || return 1
    printf '%s\n' "${viable[$(( choice - 1 ))]}"
    return 0
  fi

  if command -v fzf &>/dev/null && [[ -t 1 ]]; then
    local picked
    picked="$(
      idx=1
      for r in "${viable[@]}"; do
        local s e z
        read -r s e z <<<"$r"
        printf '%d\tstart=%ss end=%ss size=%s\n' "$idx" "$s" "$e" "$(human_bytes $(( z * sector_size )))"
        idx=$(( idx + 1 ))
      done | fzf --prompt='Select unallocated region > ' --with-nth=2.. --height=12 --reverse
    )" || return 1
    local n
    n="$(printf '%s' "$picked" | awk '{print $1}')"
    [[ "$n" =~ ^[0-9]+$ ]] || return 1
    printf '%s\n' "${viable[$(( n - 1 ))]}"
    return 0
  fi

  if [[ -t 1 ]]; then
    local -a desc
    for r in "${viable[@]}"; do
      local s e z
      read -r s e z <<<"$r"
      desc+=("start=${s}s end=${e}s size=$(human_bytes $(( z * sector_size )))")
    done
    local picked_idx
    picked_idx="$(arrow_select 'Select unallocated region' "${desc[@]}")" || return 1
    printf '%s\n' "${viable[$picked_idx]}"
    return 0
  fi

  printf '\n%s  Multiple free regions detected. Choose where to install:%s\n\n' "$DM" "$RS"
  idx=1
  for r in "${viable[@]}"; do
    local s e z
    read -r s e z <<<"$r"
    printf '%s  [%d]%s start=%ss end=%ss size=%s\n' \
      "$WH" "$idx" "$RS" "$s" "$e" "$(human_bytes $(( z * sector_size )))"
    idx=$(( idx + 1 ))
  done

  printf '\n%s  Choice [1-%d]: %s' "$AM" "${#viable[@]}" "$RS"
  local choice
  read -r choice
  [[ "$choice" =~ ^[0-9]+$ ]] || return 1
  (( choice >= 1 && choice <= ${#viable[@]} )) || return 1

  printf '%s\n' "${viable[choice-1]}"
}

# ════════════════════════════════════════════════════════════════════════════
#  PHASE 1 — Full Arch Linux Installation
# ════════════════════════════════════════════════════════════════════════════

ci_load_config() {
  # Populate all install variables from environment variables.
  # Called instead of the interactive gather/select functions when HYPRCONF_CI=1.
  DISK="${HYPRCONF_CI_DISK:-}"
  [[ -n "$DISK" ]] || log_die "CI mode: HYPRCONF_CI_DISK must be set (e.g. /dev/vda)."

  USERNAME="${HYPRCONF_CI_USERNAME:-hyprtest}"
  USER_PASSWORD="${HYPRCONF_CI_PASSWORD:-hyprtest}"
  USER_HOSTNAME="${HYPRCONF_CI_HOSTNAME:-hyprconf-test}"
  TIMEZONE="${HYPRCONF_CI_TIMEZONE:-UTC}"
  PART_MODE="${HYPRCONF_CI_PART_MODE:-full}"
  COPY_NETCONF="${HYPRCONF_CI_COPY_NETCONF:-0}"

  [[ "$PART_MODE" == "full" || "$PART_MODE" == "unallocated" ]] \
    || log_die "CI mode: HYPRCONF_CI_PART_MODE must be 'full' or 'unallocated'."

  log_ok "CI mode: disk=$DISK user=$USERNAME hostname=$USER_HOSTNAME tz=$TIMEZONE part=$PART_MODE"
}

check_iso_env() {
  log_step "Checking environment..."
  if [[ "$HYPRCONF_CI" == "1" ]]; then
    command -v pacstrap &>/dev/null  || log_die "CI mode: pacstrap not found — install arch-install-scripts."
    log_ok "CI mode: environment check passed."
    return
  fi
  command -v pacstrap &>/dev/null  || log_die "pacstrap not found — run this from the Arch Linux ISO."
  [[ -d /sys/firmware/efi/efivars ]] || log_die "UEFI mode required. Reboot with UEFI enabled."
  timedatectl set-ntp true
  log_ok "Arch ISO (UEFI) confirmed, NTP syncing."
}

gather_user_input() {
  printf '\n%s  ── User Configuration ──────────────────────────────────────────%s\n\n' "$DM" "$RS"

  while true; do
    printf '%s  Username: %s' "$AM" "$RS"
    read -r USERNAME
    [[ "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,30}$ ]] && break
    log_warn "Invalid username — lowercase, alphanumeric/underscore/hyphen, ≤31 chars."
  done

  while true; do
    printf '%s  Password (used for account + disk encryption): %s' "$AM" "$RS"
    read -rs USER_PASSWORD; echo
    printf '%s  Confirm password: %s' "$AM" "$RS"
    read -rs pw2; echo
    [[ "$USER_PASSWORD" == "$pw2" && -n "$USER_PASSWORD" ]] && break
    log_warn "Passwords don't match or are empty — try again."
  done

  printf '%s  Hostname [arch]: %s' "$AM" "$RS"
  read -r USER_HOSTNAME
  [[ -z "$USER_HOSTNAME" ]] && USER_HOSTNAME="arch"

  COPY_NETCONF=1

  log_ok "Username: $USERNAME  Hostname: $USER_HOSTNAME"
}

detect_timezone() {
  log_step "Detecting timezone from IP..."
  local suggested
  suggested=$(curl -fsSL --max-time 5 "https://ipapi.co/timezone" 2>/dev/null || true)
  # Fall back to UTC if the response looks wrong (JSON error body, empty, etc.)
  [[ -z "$suggested" || "$suggested" == *"{"* ]] && suggested="UTC"

  printf '\n%s  Suggested timezone: %s%s%s\n' "$DM" "$WH" "$suggested" "$RS"
  printf '%s  Accept? [Y/n]: %s' "$AM" "$RS"
  local tz_ans
  read -r tz_ans
  if [[ "${tz_ans,,}" == "n" ]]; then
    _pick_timezone
  else
    TIMEZONE="$suggested"
  fi
  log_ok "Timezone: $TIMEZONE"
}

_ensure_fzf() {
  # Install fzf on the live environment if not already present.
  # Silently no-ops when fzf is already on PATH or when pacman is unavailable
  # (e.g. running unit tests outside an Arch ISO).
  command -v fzf &>/dev/null && return 0
  command -v pacman &>/dev/null || return 1
  log_step "Installing fzf for interactive selectors..."
  pacman -Sy --noconfirm --needed fzf &>/dev/null && return 0 || true
  log_warn "Could not install fzf — falling back to built-in selector"
  return 1
}

_pick_timezone() {
  # Ensure fzf is available on the live environment before building the list —
  # it provides a far better UX than arrow_select for hundreds of timezones.
  _ensure_fzf || true

  # Build a sorted list of valid timezones from /usr/share/zoneinfo.
  local -a zones=()
  if [[ -d /usr/share/zoneinfo ]]; then
    mapfile -t zones < <(
      find /usr/share/zoneinfo -type f -o -type l \
        | sed 's|/usr/share/zoneinfo/||' \
        | grep -E '^[A-Z][^/]+/[^/]+$' \
        | sort
    )
  fi

  # Try fzf first (most comfortable), then arrow_select, then plain read.
  if (( ${#zones[@]} > 0 )) && command -v fzf &>/dev/null; then
    local picked
    picked=$(printf '%s\n' "${zones[@]}" | fzf \
      --prompt='  Timezone > ' \
      --height=15 \
      --reverse \
      --no-mouse \
      --header='Type to filter  (e.g. Europe, America, Asia)') || true
    if [[ -n "$picked" && -f "/usr/share/zoneinfo/$picked" ]]; then
      TIMEZONE="$picked"
      return 0
    fi
    log_warn "No timezone selected via fzf — falling back."
  fi

  if (( ${#zones[@]} > 0 )); then
    # Grouped arrow picker: let user pick a region then a city.
    local -a regions=()
    mapfile -t regions < <(printf '%s\n' "${zones[@]}" | cut -d/ -f1 | sort -u)

    local ridx
    ridx="$(arrow_select 'Select region' "${regions[@]}")" || ridx=""

    if [[ -n "${ridx:-}" ]]; then
      local region="${regions[$ridx]}"
      local -a cities=()
      mapfile -t cities < <(printf '%s\n' "${zones[@]}" | grep "^${region}/" | sed "s|^${region}/||" | sort)
      local cidx
      cidx="$(arrow_select "Select city  (${region})" "${cities[@]}")" || cidx=""
      if [[ -n "${cidx:-}" ]]; then
        TIMEZONE="${region}/${cities[$cidx]}"
        return 0
      fi
    fi
  fi

  # Plain-text fallback with retry loop.
  while true; do
    printf '%s  Timezone%s (e.g. Europe/London, America/New_York, UTC): %s' "$AM" "$DM" "$RS"
    read -r TIMEZONE
    [[ -z "$TIMEZONE" ]] && { TIMEZONE="UTC"; break; }
    if [[ -f "/usr/share/zoneinfo/$TIMEZONE" ]]; then
      break
    fi
    log_warn "Unknown timezone: $TIMEZONE — check spelling or pick from: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
  done
}

select_disk() {
  printf '\n%s  ── Available Disks ─────────────────────────────────────────────%s\n\n' "$DM" "$RS"

  local -a lines
  mapfile -t lines < <(lsblk -d -p -n -o NAME,SIZE,MODEL -e 7,11)
  (( ${#lines[@]} > 0 )) || log_die "No disks detected."

  DISK="${DISK:-}"

  # Common VM case (e.g. /dev/vda): if there's only one disk, auto-select it.
  if [[ -z "${DISK:-}" && ${#lines[@]} -eq 1 ]]; then
    DISK="$(printf '%s' "${lines[0]}" | awk '{print $1}')"
    log_info "Only one disk detected; selecting $DISK"
  fi

  # Arrow-able selector when available (dialog/fzf/arrow_select), otherwise manual.
  if [[ -z "${DISK:-}" && -t 1 ]] && command -v dialog &>/dev/null; then
    local -a opts
    local l name rest
    for l in "${lines[@]}"; do
      name="$(printf '%s' "$l" | awk '{print $1}')"
      rest="$(printf '%s' "$l" | cut -d' ' -f2- | sed -E 's/[[:space:]]+/ /g')"
      opts+=("$name" "$rest")
    done

    local choice rc
    if choice="$(dialog --stdout --menu 'Select target disk' 20 90 12 "${opts[@]}")"; then
      DISK="$choice"
    else
      rc=$?
      if (( rc == 1 )); then
        log_die "Disk selection cancelled."
      fi
      log_warn "dialog failed (rc=$rc); falling back to other selectors"
    fi
  fi

  if [[ -z "${DISK:-}" && -t 1 ]] && command -v fzf &>/dev/null; then
    local picked rc
    if picked="$(printf '%s\n' "${lines[@]}" | fzf --prompt='Select target disk > ' --height=12 --reverse)"; then
      DISK="$(printf '%s' "$picked" | awk '{print $1}')"
    else
      rc=$?
      log_die "Disk selection cancelled."
    fi
  fi

  if [[ -z "${DISK:-}" && -t 1 ]]; then
    local idx
    if idx="$(arrow_select 'Select target disk' "${lines[@]}")"; then
      DISK="$(printf '%s' "${lines[$idx]}" | awk '{print $1}')"
    else
      log_warn "Arrow selector unavailable; falling back to manual entry"
    fi
  fi

  if [[ -z "${DISK:-}" ]]; then
    lsblk -d -p -o NAME,SIZE,MODEL -e 7,11
    printf '\n%s  Disk to install on (e.g. /dev/sda, /dev/vda, /dev/nvme0n1): %s' "$AM" "$RS"
    read -r DISK
  fi

  [[ -b "$DISK" ]] || log_die "Not a valid block device: $DISK"
  local sz; sz=$(lsblk -d -n -o SIZE "$DISK")
  log_ok "Target disk: $DISK ($sz)"

  log_info "Current layout:"
  lsblk -p -o NAME,SIZE,FSTYPE,TYPE,MOUNTPOINT "$DISK" 2>/dev/null || true
}

select_partition_mode() {
  printf '\n%s  ── Partition Mode ───────────────────────────────────────────────%s\n\n' "$DM" "$RS"
  printf '%s  [1]%s Full disk         %s— wipes all data on %s%s\n'           "$WH" "$RS" "$GL" "$DISK" "$RS"
  printf '%s  [2]%s Unallocated space %s— preserves existing partitions%s\n\n' "$WH" "$RS" "$DM" "$RS"
  printf '%s  Choice [1/2]: %s' "$AM" "$RS"
  read -r choice
  case "$choice" in
    1) PART_MODE="full" ;;
    2) PART_MODE="unallocated" ;;
    *) log_die "Invalid choice." ;;
  esac
}

confirm_install() {
  printf '\n%s  ══ Install Summary ══════════════════════════════════════════════%s\n' "$DM" "$RS"
  printf '%s  Disk       :%s %s\n'               "$DM" "$RS" "$DISK"
  printf '%s  Mode       :%s %s\n'               "$DM" "$RS" "$PART_MODE"
  printf '%s  Encryption :%s LUKS2 + btrfs\n'   "$DM" "$RS"
  printf '%s  Bootloader :%s systemd-boot\n'     "$DM" "$RS"
  printf '%s  Username   :%s %s\n'               "$DM" "$RS" "$USERNAME"
  printf '%s  Hostname   :%s %s\n'               "$DM" "$RS" "$USER_HOSTNAME"
  printf '%s  Timezone   :%s %s\n'               "$DM" "$RS" "$TIMEZONE"
  printf '%s  Net config :%s %s\n\n'             "$DM" "$RS" "$([[ "$COPY_NETCONF" -eq 1 ]] && echo 'copy from ISO' || echo 'do not copy')"
  [[ "$PART_MODE" == "full" ]] && \
    printf '%s  !! ALL DATA ON %s WILL BE PERMANENTLY ERASED !!%s\n\n' "$GL" "$DISK" "$RS"
  printf '%s  Type "yes" to begin: %s' "$AM" "$RS"
  read -r ans
  [[ "$ans" == "yes" ]] || log_die "Installation cancelled."
}

partition_full() {
  log_step "Wiping and partitioning $DISK (full disk)..."
  wipefs -af "$DISK"
  sgdisk --zap-all "$DISK"
  sgdisk -n 1:0:+512M -t 1:ef00 -c 1:"EFI System"  "$DISK"
  sgdisk -n 2:0:0     -t 2:8309 -c 2:"Linux LUKS"   "$DISK"
  partprobe "$DISK" && sleep 1
  EFI_PART=$(part_dev "$DISK" 1)
  ROOT_PART=$(part_dev "$DISK" 2)
  mkfs.fat -F32 -n EFI "$EFI_PART"
  log_ok "EFI: $EFI_PART   Root: $ROOT_PART"
}

partition_unallocated() {
  log_step "Detecting free space on $DISK..."

  # Require GPT (avoid silent exit under set -euo pipefail if parted fails)
  local parted_out parted_rc disk_label
  set +e
  parted_out="$(run_timeout 8 parted -s "$DISK" print 2>&1)"
  parted_rc=$?
  set -e

  if (( parted_rc == 124 )); then
    log_die "Timed out reading partition table (parted) for $DISK"
  fi

  if (( parted_rc != 0 )); then
    if [[ "${parted_out:-}" == *"unrecognised disk label"* ]]; then
      log_warn "No partition table detected on $DISK."
      printf '\n%s  Create a new GPT partition table on %s?%s\n' "$WH" "$DISK" "$RS"
      printf '%s  This overwrites any existing partition table metadata (partitions will be lost).%s\n' "$DM" "$RS"
      printf '%s  Continue? [Y/n]: %s' "$AM" "$RS"
      local mklabel_ans
      read -r mklabel_ans
      if [[ "${mklabel_ans,,}" == "n" ]]; then
        log_die "Disk must use GPT."
      fi

      log_step "Initializing GPT partition table on $DISK..."
      run_timeout 8 parted -s "$DISK" mklabel gpt >/dev/null 2>&1 \
        || log_die "Failed to create GPT partition table on $DISK"

      set +e
      parted_out="$(run_timeout 8 parted -s "$DISK" print 2>&1)"
      parted_rc=$?
      set -e

      if (( parted_rc != 0 )); then
        log_die "Failed reading partition table for $DISK after GPT init: ${parted_out:-unknown error}"
      fi
    else
      log_die "Failed reading partition table for $DISK: ${parted_out:-unknown error}"
    fi
  fi

  disk_label="$(printf '%s\n' "$parted_out" | awk '/Partition Table:/{print $3; exit}')"
  [[ "$disk_label" == "gpt" ]] \
    || log_die "Disk must use GPT. Detected: '${disk_label:-unknown}'."

  local sector_size
  sector_size=$(blockdev --getss "$DISK")

  local root_min_gib=10
  local total_min_gib=10
  local efi_mib=512

  local root_need_sectors=$(( root_min_gib * 1024 * 1024 * 1024 / sector_size ))
  local total_need_sectors=$(( total_min_gib * 1024 * 1024 * 1024 / sector_size ))
  local efi_need_sectors=$(( efi_mib * 1024 * 1024 / sector_size ))

  # Detect existing ESP(s)
  local -a esp_parts
  mapfile -t esp_parts < <(esp_candidates_on_disk "$DISK" || true)

  local create_new_efi=1
  local selected_esp=""

  if (( ${#esp_parts[@]} > 0 )); then
    printf '\n%s  ── EFI System Partition (ESP) ───────────────────────────────────%s\n\n' "$DM" "$RS"
    log_info "Existing ESP(s) detected on $DISK:"

    local i
    for i in "${!esp_parts[@]}"; do
      print_esp_report "${esp_parts[$i]}"
    done

    # Default to the first ESP, but allow choosing if multiple.
    selected_esp="${esp_parts[0]}"
    if (( ${#esp_parts[@]} > 1 )); then
      if command -v dialog &>/dev/null && [[ -t 1 ]]; then
        local -a opts
        local i
        for i in "${!esp_parts[@]}"; do
          opts+=("$(( i + 1 ))" "${esp_parts[$i]}")
        done
        local esp_choice
        esp_choice="$(dialog --stdout --menu 'Select existing ESP' 20 80 10 "${opts[@]}")" || log_die "Selection cancelled."
        selected_esp="${esp_parts[$(( esp_choice - 1 ))]}"
      elif command -v fzf &>/dev/null && [[ -t 1 ]]; then
        local picked
        picked="$(printf '%s\n' "${esp_parts[@]}" | fzf --prompt='Select existing ESP > ' --height=10 --reverse)" || log_die "Selection cancelled."
        selected_esp="$picked"
      elif [[ -t 1 ]]; then
        local picked_idx
        picked_idx="$(arrow_select 'Select existing ESP' "${esp_parts[@]}")" || log_die "Selection cancelled."
        selected_esp="${esp_parts[$picked_idx]}"
      else
        printf '\n%s  Use which existing ESP? [1-%d] (default 1): %s' "$AM" "${#esp_parts[@]}" "$RS"
        local esp_choice
        read -r esp_choice
        if [[ -n "${esp_choice:-}" ]]; then
          [[ "$esp_choice" =~ ^[0-9]+$ ]] || log_die "Invalid choice."
          (( esp_choice >= 1 && esp_choice <= ${#esp_parts[@]} )) || log_die "Invalid choice."
          selected_esp="${esp_parts[$(( esp_choice - 1 ))]}"
        fi
      fi
    fi

    local esp_size_bytes
    esp_size_bytes="$(lsblk -bno SIZE "$selected_esp" 2>/dev/null | head -1 || echo 0)"

    local free_bytes
    free_bytes="$(esp_free_bytes "$selected_esp" || true)"
    if [[ -n "${free_bytes:-}" ]]; then
      # Heuristic warnings: systemd-boot + kernel + fallback initramfs can be large.
      if (( free_bytes < 150 * 1024 * 1024 )); then
        log_warn "Low free space on ESP ($(human_bytes "$free_bytes")). Bootloader/kernel updates may fail."
      elif (( free_bytes < 300 * 1024 * 1024 )); then
        log_warn "ESP free space is a bit tight ($(human_bytes "$free_bytes"))."
      fi
    fi

    # Automatically create a new ESP when the existing one is under 1 GiB —
    # that is too small for a kernel + initramfs + systemd-boot over time.
    if (( esp_size_bytes < 1024 * 1024 * 1024 )); then
      log_warn "Existing ESP is $(human_bytes "$esp_size_bytes") (< 1 GiB) — a new ESP will be created automatically."
      create_new_efi=1
    else
      printf '\n%s  How should we handle EFI?%s\n\n' "$WH" "$RS"
      printf '%s  [1]%s Use existing ESP (%s, %s)\n' "$WH" "$RS" "$selected_esp" "$(human_bytes "$esp_size_bytes")"
      printf '%s  [2]%s Create a new %dMiB ESP in the selected unallocated space\n\n' "$WH" "$RS" "$efi_mib"
      printf '%s  Choice [1/2] (default 1): %s' "$AM" "$RS"
      local efi_choice
      read -r efi_choice
      if [[ "${efi_choice:-1}" == "2" ]]; then
        create_new_efi=1
      else
        create_new_efi=0
        EFI_PART="$selected_esp"
      fi
    fi
  else
    log_info "No ESP detected on this disk — a new ESP will be created in free space."
    create_new_efi=1
  fi

  local need_sectors="$root_need_sectors"
  local need_desc="${root_min_gib}GiB"
  if (( create_new_efi == 1 )); then
    # When creating a new ESP, treat the minimum as TOTAL space, not root+ESP.
    # This allows small VM disks (e.g. ~10GiB total) to proceed with ~9.5GiB root.
    need_sectors="$total_need_sectors"
    need_desc="${total_min_gib}GiB total (incl ${efi_mib}MiB ESP)"
  fi

  # Choose which free region to use (handles multiple unallocated regions)
  local region
  region="$(choose_free_region "$DISK" "$need_sectors")" \
    || log_die "No unallocated region large enough. Need at least ${need_desc} on $DISK (must be unallocated disk space, not free space inside a partition)."

  local free_start free_end free_sectors
  read -r free_start free_end free_sectors <<<"$region"

  local free_gib
  free_gib=$(( free_sectors * sector_size / 1024 / 1024 / 1024 ))
  log_info "Using ~${free_gib} GiB free region (start=${free_start}s end=${free_end}s)."

  printf '\n%s  Before formatting, wipe any existing filesystem signatures on the NEW partition(s)?%s\n' "$WH" "$RS"
  printf '%s  This is recommended when installing into previously-used unallocated space.%s\n' "$DM" "$RS"
  printf '%s  Wipe signatures (wipefs)? [Y/n]: %s' "$AM" "$RS"
  local wipe_ans
  read -r wipe_ans
  local do_wipe=1
  [[ "${wipe_ans,,}" == "n" ]] && do_wipe=0

  # Next available partition number
  local next_num
  next_num=$(sgdisk --print "$DISK" 2>/dev/null \
    | awk '$1+0 > 0 {n=$1} END {print n+0+1}')

  if (( create_new_efi == 1 )); then
    log_info "Creating new ${efi_mib}MiB ESP + root in free space."
    local efi_num="$next_num"
    local root_num=$(( next_num + 1 ))

    local efi_end=$(( free_start + efi_need_sectors - 1 ))
    (( efi_end < free_end )) || log_die "Selected free region is too small for a new ESP + root."

    sgdisk -n "${efi_num}:${free_start}:${efi_end}" \
           -t "${efi_num}:ef00" -c "${efi_num}:EFI System" "$DISK"
    sgdisk -n "${root_num}:$(( efi_end + 1 )):${free_end}" \
           -t "${root_num}:8309" -c "${root_num}:Linux LUKS" "$DISK"

    partprobe "$DISK" && sleep 1

    EFI_PART=$(part_dev "$DISK" "$efi_num")
    ROOT_PART=$(part_dev "$DISK" "$root_num")

    (( do_wipe == 1 )) && { wipefs -af "$EFI_PART" || log_warn "wipefs failed on $EFI_PART"; }
    mkfs.fat -F32 -n EFI "$EFI_PART"
    log_ok "EFI: $EFI_PART"
  else
    log_info "Reusing existing ESP: $EFI_PART"
    sgdisk -n "${next_num}:${free_start}:${free_end}" \
           -t "${next_num}:8309" -c "${next_num}:Linux LUKS" "$DISK"

    partprobe "$DISK" && sleep 1
    ROOT_PART=$(part_dev "$DISK" "$next_num")
  fi

  (( do_wipe == 1 )) && { wipefs -af "$ROOT_PART" || log_warn "wipefs failed on $ROOT_PART"; }
  log_ok "Root: $ROOT_PART"
}

setup_luks() {
  log_step "Encrypting $ROOT_PART with LUKS2..."
  cryptsetup close "$LUKS_NAME" 2>/dev/null || true
  echo -n "$USER_PASSWORD" | cryptsetup luksFormat \
    --type luks2 --cipher aes-xts-plain64 --key-size 512 \
    --hash sha512 --iter-time 3000 "$ROOT_PART" -d -
  echo -n "$USER_PASSWORD" | cryptsetup open "$ROOT_PART" "$LUKS_NAME" -d -
  log_ok "LUKS2 container open at /dev/mapper/$LUKS_NAME"
}

setup_btrfs() {
  log_step "Creating btrfs filesystem and subvolumes..."
  mkfs.btrfs -f -L archroot /dev/mapper/"$LUKS_NAME"
  mount /dev/mapper/"$LUKS_NAME" /mnt
  btrfs subvolume create /mnt/@
  btrfs subvolume create /mnt/@home
  btrfs subvolume create /mnt/@snapshots
  btrfs subvolume create /mnt/@var_log
  umount /mnt
  log_ok "Subvolumes: @  @home  @snapshots  @var_log"
}

mount_filesystems() {
  log_step "Mounting filesystems..."
  umount -R /mnt 2>/dev/null || true
  mount -o "${BTRFS_OPTS},subvol=@"          /dev/mapper/"$LUKS_NAME" /mnt
  mkdir -p /mnt/{boot,home,.snapshots,var/log}
  mount -o "${BTRFS_OPTS},subvol=@home"      /dev/mapper/"$LUKS_NAME" /mnt/home
  mount -o "${BTRFS_OPTS},subvol=@snapshots" /dev/mapper/"$LUKS_NAME" /mnt/.snapshots
  mount -o "${BTRFS_OPTS},subvol=@var_log"   /dev/mapper/"$LUKS_NAME" /mnt/var/log
  mount -o umask=0077 "$EFI_PART" /mnt/boot
  log_ok "All filesystems mounted."
}

install_base_system() {
  # Detect CPU for microcode
  if grep -q "GenuineIntel" /proc/cpuinfo; then
    CPU_UCODE="intel-ucode"
  elif grep -q "AuthenticAMD" /proc/cpuinfo; then
    CPU_UCODE="amd-ucode"
  fi
  [[ -n "$CPU_UCODE" ]] \
    && log_step "CPU microcode: $CPU_UCODE" \
    || log_info "No microcode package required."

  log_step "Installing base system via pacstrap (this takes a few minutes)..."
  local pkgs=(base base-devel linux linux-firmware btrfs-progs networkmanager iwd openssh git zsh sudo nano)
  [[ -n "$CPU_UCODE" ]] && pkgs+=("$CPU_UCODE")

  local attempt
  for attempt in 1 2 3; do
    if pacstrap /mnt "${pkgs[@]}"; then
      break
    fi
    (( attempt < 3 )) || log_die "pacstrap failed after 3 attempts — check network/mirror connectivity."
    log_warn "pacstrap attempt $attempt failed (mirror error?) — retrying in 10s..."
    sleep 10
  done

  genfstab -U /mnt >> /mnt/etc/fstab
  log_ok "Base system installed. fstab generated."
}

copy_network_config_from_iso() {
  (( COPY_NETCONF == 1 )) || { log_info "Skipping network config copy."; return 0; }

  log_step "Copying network config from ISO..."

  local target_dir="/mnt/etc/NetworkManager/system-connections"
  mkdir -p "$target_dir"
  chmod 700 "$target_dir"
  chown root:root "$target_dir"

  # Prefer copying existing NetworkManager profiles if they exist on the ISO.
  if [[ -d /etc/NetworkManager/system-connections ]] \
    && compgen -G "/etc/NetworkManager/system-connections/*" >/dev/null; then
    cp -a /etc/NetworkManager/system-connections/. "$target_dir/"
    chmod 600 "$target_dir"/* 2>/dev/null || true
    chown root:root "$target_dir"/* 2>/dev/null || true
    log_ok "NetworkManager profiles copied."
    return 0
  fi

  # Common Arch ISO WiFi path: iwctl/iwd stores networks in /var/lib/iwd/*.psk
  if [[ -d /var/lib/iwd ]]; then
    local imported=0 skipped=0
    local f ssid psk uuid file_safe out

    shopt -s nullglob
    local -a psk_files=(/var/lib/iwd/*.psk)
    local -a open_files=(/var/lib/iwd/*.open)
    local -a eap_files=(/var/lib/iwd/*.8021x)
    shopt -u nullglob

    for f in "${open_files[@]}"; do
      ssid="$(basename "$f")"
      ssid="${ssid%.open}"

      uuid="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || true)"
      [[ -n "$uuid" ]] || uuid="$(uuidgen 2>/dev/null || true)"
      [[ -n "$uuid" ]] || uuid="00000000-0000-0000-0000-000000000000"

      file_safe="$(printf '%s' "$ssid" | sed -E 's#[/\\]#_#g; s/[[:space:]]+$//')"
      [[ -n "$file_safe" ]] || file_safe="wifi-${imported}"

      out="$target_dir/${file_safe}.nmconnection"
      cat > "$out" << EOF
[connection]
id=${ssid}
uuid=${uuid}
type=wifi
autoconnect=true

[wifi]
mode=infrastructure
ssid=${ssid}

[ipv4]
method=auto

[ipv6]
method=auto
EOF
      chmod 600 "$out"
      chown root:root "$out"
      imported=$(( imported + 1 ))
    done

    for f in "${psk_files[@]}"; do
      ssid="$(basename "$f")"
      ssid="${ssid%.psk}"

      # Prefer PreSharedKey (hex) when present; it avoids special-char escaping issues.
      psk="$(sed -n 's/^PreSharedKey=//p' "$f" | head -n1)"
      [[ -z "$psk" ]] && psk="$(sed -n 's/^Passphrase=//p' "$f" | head -n1)"

      if [[ -z "$psk" ]]; then
        skipped=$(( skipped + 1 ))
        continue
      fi

      uuid="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || true)"
      [[ -n "$uuid" ]] || uuid="$(uuidgen 2>/dev/null || true)"
      [[ -n "$uuid" ]] || uuid="00000000-0000-0000-0000-000000000000"

      file_safe="$(printf '%s' "$ssid" | sed -E 's#[/\\]#_#g; s/[[:space:]]+$//')"
      [[ -n "$file_safe" ]] || file_safe="wifi-${imported}"

      out="$target_dir/${file_safe}.nmconnection"
      cat > "$out" << EOF
[connection]
id=${ssid}
uuid=${uuid}
type=wifi
autoconnect=true

[wifi]
mode=infrastructure
ssid=${ssid}

[wifi-security]
key-mgmt=wpa-psk
psk=${psk}

[ipv4]
method=auto

[ipv6]
method=auto
EOF
      chmod 600 "$out"
      chown root:root "$out"
      imported=$(( imported + 1 ))
    done

    if (( imported > 0 )); then
      log_ok "Imported ${imported} WiFi network(s) from ISO."
      (( skipped > 0 )) && log_warn "Skipped ${skipped} iwd PSK profile(s) missing PSK/passphrase."
      return 0
    fi

    if (( ${#eap_files[@]} > 0 )); then
      log_warn "Detected iwd enterprise WiFi profile(s) (.8021x) which are not auto-imported."
    fi
  fi

  log_warn "No ISO network profiles found to copy — connect to wifi after first boot with: nmtui"
}

configure_in_chroot() {
  log_step "Configuring system in chroot..."

  local root_uuid
  root_uuid=$(blkid -s UUID -o value "$ROOT_PART")

  # Pre-compute the optional ucode initrd line (empty string when no ucode package)
  local ucode_line=""
  [[ -n "$CPU_UCODE" ]] && ucode_line="initrd  /${CPU_UCODE}.img"

  # Pre-compute the LUKS keyfile boot option (CI only — empty string for desktop installs)
  local luks_key_opt=""
  [[ "${HYPRCONF_CI:-0}" == "1" ]] && luks_key_opt=" rd.luks.key=/etc/crypto_keyfile.bin"

  # Write the chroot setup script.
  # Unquoted EOF delimiter: our outer variables (USERNAME, TIMEZONE, etc.) expand here.
  # SECURITY: USER_PASSWORD is deliberately NEVER expanded into this script — it
  # would land in plaintext on the target disk (and survive forensically even
  # after rm). chpasswd and the CI luksAddKey run from the ISO side via stdin
  # after the chroot script completes.
  # Inner heredoc markers (LOADER, ENTRY, ENTRY2) are written verbatim and function
  # normally when the chroot script is executed.
  # The AUTOLOGIN block uses a quoted inner delimiter (<< 'AUTOLOGIN') to preserve \u
  # literally; a subsequent sed replaces __USERNAME__ with the already-expanded value.
  cat > /mnt/hyprconf-chroot.sh << EOF
#!/bin/bash
set -euo pipefail

# ── Locale ────────────────────────────────────────────────────────────────────
echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
locale-gen
echo "LANG=en_US.UTF-8" > /etc/locale.conf

# ── Timezone ──────────────────────────────────────────────────────────────────
ln -sf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
hwclock --systohc

# ── Hostname ──────────────────────────────────────────────────────────────────
echo "${USER_HOSTNAME}" > /etc/hostname
{
  echo "127.0.0.1  localhost"
  echo "::1        localhost"
  echo "127.0.1.1  ${USER_HOSTNAME}.localdomain ${USER_HOSTNAME}"
} > /etc/hosts

# ── Console keymap (required by sd-vconsole hook) ────────────────────────────
echo "KEYMAP=us" > /etc/vconsole.conf

# ── Initramfs — systemd + sd-encrypt hooks for LUKS ──────────────────────────
sed -i 's/^HOOKS=.*/HOOKS=(base systemd autodetect microcode modconf keyboard sd-vconsole block sd-encrypt filesystems fsck)/' /etc/mkinitcpio.conf

# CI only: embed a LUKS keyfile so the VM boots unattended (no console to type
# password). The keyfile is REGISTERED as a LUKS key from the ISO side after this
# script finishes (needs the password, which never appears in this file).
if [[ "${HYPRCONF_CI:-0}" == "1" ]]; then
  dd bs=512 count=4 if=/dev/urandom of=/etc/crypto_keyfile.bin 2>/dev/null
  chmod 000 /etc/crypto_keyfile.bin
  sed -i 's|^FILES=.*|FILES=(/etc/crypto_keyfile.bin)|' /etc/mkinitcpio.conf
fi

mkinitcpio -P

# ── systemd-boot ──────────────────────────────────────────────────────────────
bootctl install
mkdir -p /boot/loader/entries

cat > /boot/loader/loader.conf << 'LOADER'
default arch.conf
timeout 4
console-mode max
editor no
LOADER

# Boot options (luks_key_opt already expanded by outer shell when writing this script)
cat > /boot/loader/entries/arch.conf << ENTRY
title   Arch Linux
linux   /vmlinuz-linux
${ucode_line}
initrd  /initramfs-linux.img
options rd.luks.name=${root_uuid}=${LUKS_NAME} root=/dev/mapper/${LUKS_NAME} rootflags=subvol=@ rw quiet${luks_key_opt}
ENTRY

cat > /boot/loader/entries/arch-fallback.conf << ENTRY2
title   Arch Linux (fallback initramfs)
linux   /vmlinuz-linux
${ucode_line}
initrd  /initramfs-linux-fallback.img
options rd.luks.name=${root_uuid}=${LUKS_NAME} root=/dev/mapper/${LUKS_NAME} rootflags=subvol=@ rw${luks_key_opt}
ENTRY2

# ── User ──────────────────────────────────────────────────────────────────────
# (The account password is set from the ISO side via stdin after this script —
# never expanded into this on-disk file.)
useradd -m -G wheel,audio,video,storage,input,network -s /bin/zsh "${USERNAME}"
# Admin is sudo-only: the wheel member above gets full sudo, and the root account
# is LOCKED so there is no separate root credential to reuse, guess, or leak (the
# install password is now the user account + LUKS only). Lock explicitly with
# `passwd -l` — never just skip setting it, which could leave root with an EMPTY
# password (passwordless root on the console). Trade-off: single-user/rescue mode
# (sulogin) refuses a locked root, so recover a broken sudo/PAM via the Arch live
# USB + arch-chroot (see docs/security-hardening.md).
echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/wheel
chmod 440 /etc/sudoers.d/wheel
passwd -l root

# ── Services ──────────────────────────────────────────────────────────────────
systemctl enable NetworkManager
command -v iwctl &>/dev/null && systemctl enable iwd || true
systemctl enable systemd-resolved
# Enable sshd only in CI (VM tests need it; not appropriate for desktop installs)
[[ "${HYPRCONF_CI:-0}" == "1" ]] && systemctl enable sshd || true

# ── NetworkManager wifi backend ───────────────────────────────────────────────
# Configure NetworkManager to use iwd as its wifi backend.  iwd handles wifi
# association more reliably than wpa_supplicant; NM still manages DHCP and
# connection profiles.  This must be written before first boot.
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/wifi-backend.conf << 'NMCONF'
[device]
wifi.backend=iwd
NMCONF

# ── TTY1 auto-login ───────────────────────────────────────────────────────────
# Uses a quoted inner heredoc so \u (agetty format specifier) is preserved literally.
# __USERNAME__ is then replaced by sed with the real username.
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -f -- \u' --noclear --autologin __USERNAME__ %I xterm-256color
Type=simple
AUTOLOGIN
sed -i 's/__USERNAME__/${USERNAME}/' /etc/systemd/system/getty@tty1.service.d/autologin.conf
EOF

  chmod +x /mnt/hyprconf-chroot.sh
  arch-chroot /mnt /bin/bash /hyprconf-chroot.sh
  rm -f /mnt/hyprconf-chroot.sh

  # SECURITY: secrets travel via stdin only (printf/echo are shell builtins, so
  # the password never appears on any argv or inside an on-disk file).
  printf '%s:%s\n' "$USERNAME" "$USER_PASSWORD" | arch-chroot /mnt chpasswd

  # CI only: register the keyfile embedded above as a LUKS key slot.
  if [[ "${HYPRCONF_CI:-0}" == "1" ]]; then
    echo -n "$USER_PASSWORD" \
      | cryptsetup luksAddKey "$ROOT_PART" /mnt/etc/crypto_keyfile.bin -
  fi

  log_ok "Chroot configuration complete."
}

run_setup_in_chroot() {
  if [[ -n "${HYPRCONF_CI_REPO_TGZ:-}" ]]; then
    # CI/Packer path: use the bundled repo tar instead of cloning from GitHub.
    # This avoids a network dependency inside the VM and ensures the exact code
    # under test is installed. After extraction we initialise a git repo and set
    # the origin remote so that _sync_vm_to_dev (used by the test suite) works.
    log_step "Extracting bundled repo into /home/${USERNAME}/.hyprconf ..."
    # NOTE: arch-chroot mounts a fresh tmpfs at /tmp inside the chroot, so
    # anything copied to /mnt/tmp/ beforehand is shadowed. Use /mnt/root/
    # (root's home dir) which arch-chroot never overlays.
    cp "${HYPRCONF_CI_REPO_TGZ}" /mnt/root/hyprconf-repo.tar.gz
    arch-chroot /mnt /bin/bash -c "
      mkdir -p /home/${USERNAME}
      tar -xzf /root/hyprconf-repo.tar.gz -C /home/${USERNAME}/
      rm -f /root/hyprconf-repo.tar.gz
      git -C /home/${USERNAME}/.hyprconf init --quiet
      git -C /home/${USERNAME}/.hyprconf remote add origin '${REPO_URL}'
      chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.hyprconf
    "
    log_ok "Repo extracted."
  else
    log_step "Cloning dotfiles repo into /home/${USERNAME}/.hyprconf ..."
    local sparse_paths="${REPO_SPARSE_PATHS[*]}"
    arch-chroot /mnt /bin/bash -c "
      if git clone --depth=1 --single-branch --branch '${REPO_STABLE_BRANCH}' --sparse '${REPO_URL}' /home/${USERNAME}/.hyprconf; then
        git -C /home/${USERNAME}/.hyprconf sparse-checkout init --no-cone >/dev/null 2>&1 || true
        git -C /home/${USERNAME}/.hyprconf sparse-checkout set ${sparse_paths} >/dev/null
      else
        rm -rf /home/${USERNAME}/.hyprconf
        git clone --depth=1 --single-branch --branch '${REPO_COMPAT_BRANCH}' --sparse '${REPO_URL}' /home/${USERNAME}/.hyprconf
        git -C /home/${USERNAME}/.hyprconf sparse-checkout init --no-cone >/dev/null 2>&1 || true
        git -C /home/${USERNAME}/.hyprconf sparse-checkout set ${sparse_paths} >/dev/null
      fi
      chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.hyprconf
    "
    log_ok "Repo cloned."
  fi

  # Grant passwordless sudo for unattended package installation.
  # File must sort after "wheel" alphabetically so this NOPASSWD rule wins.
  # In CI mode the rule is also written inside the installed system so that
  # SSH test sessions can run sudo commands without a terminal.
  echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" > /mnt/etc/sudoers.d/zz-hyprconf-setup
  chmod 440 /mnt/etc/sudoers.d/zz-hyprconf-setup
  if [[ "${HYPRCONF_CI:-0}" == "1" ]]; then
    cp /mnt/etc/sudoers.d/zz-hyprconf-setup /mnt/etc/sudoers.d/zz-ci-nopasswd
  fi

  log_step "Running setup.sh as ${USERNAME} in chroot..."
  # SECURITY: the temporary NOPASSWD drop-in must be removed whether setup.sh
  # succeeds OR fails. Capturing the status (instead of letting `set -e` abort
  # here) guarantees the rm runs — otherwise a mid-setup failure would strand a
  # permanent `NOPASSWD: ALL` sudoers file in the freshly installed system.
  local _setup_rc=0
  arch-chroot /mnt runuser -l "${USERNAME}" -c \
    "export HYPRCONF_CHROOT=1 HYPRCONF_INSTALLER=1; bash /home/${USERNAME}/.hyprconf/setup.sh" \
    || _setup_rc=$?

  rm -f /mnt/etc/sudoers.d/zz-hyprconf-setup
  (( _setup_rc == 0 )) || log_die "setup.sh failed in chroot (exit ${_setup_rc}) — temporary NOPASSWD sudo removed."
  log_ok "Dotfiles configured."
}

offer_yubikey_setup() {
  [[ "${HYPRCONF_CI:-0}" == "1" ]] && return 0

  printf '\n%s  ────────────────────────────────────────────────────────────────%s\n' "$DM" "$RS"
  printf '%s  YubiKey FIDO2 setup (optional)%s\n'                                       "$GR" "$RS"
  printf '%s  · Adds 2FA to sudo, TTY login, display manager, and SSH.%s\n'             "$DM" "$RS"
  printf '%s  · Can also enroll the key as a LUKS unlock factor%s\n'                    "$DM" "$RS"
  printf '%s    (your passphrase keeps working as a fallback).%s\n'                     "$DM" "$RS"
  printf '%s  Insert a FIDO2 YubiKey now if you want to configure it.%s\n\n'            "$DM" "$RS"

  printf '%s  Set up YubiKey now? [y/N]: %s' "$AM" "$RS"
  read -r ans
  [[ "$ans" =~ ^[Yy]$ ]] || return 0

  # Temp NOPASSWD sudo so yubikey-fido2-setup's pacman/systemctl calls succeed
  # non-interactively inside the chroot (mirrors run_setup_in_chroot).
  echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" > /mnt/etc/sudoers.d/zz-hyprconf-setup
  chmod 440 /mnt/etc/sudoers.d/zz-hyprconf-setup

  log_step "Launching YubiKey FIDO2 setup in chroot..."
  arch-chroot /mnt env SUDO_USER="${USERNAME}" HYPRCONF_CHROOT=1 HYPRCONF_INSTALLER=1 \
    bash "/home/${USERNAME}/.hyprconf/stow/hypr/.local/bin/yubikey-fido2-setup" setup \
    || log_warn "YubiKey setup didn't finish — run yubikey-fido2-setup after first boot to retry."

  rm -f /mnt/etc/sudoers.d/zz-hyprconf-setup
}

offer_secureboot_setup() {
  [[ "${HYPRCONF_CI:-0}" == "1" ]] && return 0

  printf '\n%s  ────────────────────────────────────────────────────────────────%s\n' "$DM" "$RS"
  printf '%s  Secure Boot setup (optional)%s\n'                                          "$GR" "$RS"
  printf '%s  · Converts the boot chain to a signed Unified Kernel Image and signs%s\n'  "$DM" "$RS"
  printf '%s    it with your own sbctl keys.%s\n'                                        "$DM" "$RS"
  printf '%s  · Closes the evil-maid gap a YubiKey alone does NOT: a tampered%s\n'        "$DM" "$RS"
  printf '%s    initramfs cannot run once Secure Boot is enabled.%s\n'                    "$DM" "$RS"
  printf '%s  · You still finish in firmware: set an admin password + enable Secure%s\n'  "$DM" "$RS"
  printf '%s    Boot. If the next boot fails, disable Secure Boot in firmware to%s\n'     "$DM" "$RS"
  printf '%s    recover (the UKI still boots with SB off).%s\n'                           "$DM" "$RS"
  printf '%s  · Best done AFTER YubiKey setup so the FIDO2 cmdline is captured.%s\n'      "$DM" "$RS"

  printf '\n%s  Set up Secure Boot (signed UKI) now? [y/N]: %s' "$AM" "$RS"
  read -r ans
  [[ "$ans" =~ ^[Yy]$ ]] || return 0

  # Temp NOPASSWD sudo so the helper's pacman/systemctl calls succeed
  # non-interactively inside the chroot (mirrors offer_yubikey_setup).
  echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" > /mnt/etc/sudoers.d/zz-hyprconf-setup
  chmod 440 /mnt/etc/sudoers.d/zz-hyprconf-setup

  log_step "Launching Secure Boot setup in chroot..."
  arch-chroot /mnt env SUDO_USER="${USERNAME}" HYPRCONF_CHROOT=1 HYPRCONF_INSTALLER=1 \
    bash "/home/${USERNAME}/.hyprconf/stow/hypr/.local/bin/hyprconf-secureboot" setup \
    || log_warn "Secure Boot setup didn't finish — run hyprconf-secureboot setup after first boot to retry."

  rm -f /mnt/etc/sudoers.d/zz-hyprconf-setup
}

unmount_all() {
  log_step "Unmounting filesystems..."
  umount -R /mnt
  cryptsetup close "$LUKS_NAME"
  log_ok "All filesystems unmounted."
}

arch_install() {
  check_iso_env
  if [[ "$HYPRCONF_CI" == "1" ]]; then
    ci_load_config
  else
    gather_user_input
    detect_timezone
    select_disk
    select_partition_mode
    confirm_install
  fi

  if [[ "$PART_MODE" == "full" ]]; then
    partition_full
  else
    partition_unallocated
  fi

  setup_luks
  setup_btrfs
  mount_filesystems
  install_base_system
  copy_network_config_from_iso
  configure_in_chroot
  run_setup_in_chroot
  offer_yubikey_setup
  offer_secureboot_setup

  # Inject test SSH public key before unmounting (CI only)
  if [[ "${HYPRCONF_CI:-0}" == "1" && -n "${HYPRCONF_CI_SSH_PUBKEY:-}" ]]; then
    local ssh_dir="/mnt/home/${USERNAME}/.ssh"
    mkdir -p "$ssh_dir"
    echo "${HYPRCONF_CI_SSH_PUBKEY}" >> "${ssh_dir}/authorized_keys"
    chmod 700 "$ssh_dir"
    chmod 600 "${ssh_dir}/authorized_keys"
    arch-chroot /mnt chown -R "${USERNAME}:${USERNAME}" "/home/${USERNAME}/.ssh"
  fi

  unmount_all

  printf '\n%s  ════════════════════════════════════════════════════════════════%s\n' "$DM" "$RS"
  printf '%s  ✔ Arch Linux installed successfully!%s\n'                              "$GR" "$RS"
  printf '%s  · Remove the installation media and reboot.%s\n'                      "$DM" "$RS"
  printf '%s  · Log in as %s — Hyprland starts automatically on tty1.%s\n'         "$DM" "$USERNAME" "$RS"
  printf '%s  · The root account is locked — use "sudo" for admin (recover a broken sudo%s\n' "$DM" "$RS"
  printf '%s    via the Arch live USB + arch-chroot; rescue mode cannot log in to locked root).%s\n' "$DM" "$RS"
  printf '%s  · Run "yubikey-fido2-setup setup" anytime to add FIDO2 login 2FA / LUKS unlock.%s\n' "$DM" "$RS"
  printf '%s  · Once FIDO2 LUKS unlock is verified, "yubikey-fido2-setup harden-luks" removes%s\n' "$DM" "$RS"
  printf '%s    the passphrase for key-only unlock (one-way — read the docs first).%s\n'        "$DM" "$RS"
  printf '%s  · "hyprconf-secureboot setup" signs the boot chain (UKI); then enable Secure%s\n' "$DM" "$RS"
  printf '%s    Boot + set a firmware password in UEFI. "hyprconf-secureboot status" checks it.%s\n\n' "$DM" "$RS"
}

# ════════════════════════════════════════════════════════════════════════════
#  PHASE 2 — Dotfiles Bootstrap  (original behaviour, unchanged)
# ════════════════════════════════════════════════════════════════════════════

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
    maybe_migrate_repo_to_stable
    log_step "Existing repo found — pulling latest..."
    git -C "$REPO_DIR" pull --ff-only \
      || log_warn "Fast-forward failed — continuing with existing files."
    apply_sparse_checkout
  else
    log_step "Cloning $REPO_URL → $REPO_DIR ..."
    clone_preferred_repo
  fi
  log_ok "Repository ready."
}

run_setup() {
  log_step "Handing off to setup.sh ..."
  printf '\n'
  HYPRCONF_INSTALLER=1 bash "$REPO_DIR/setup.sh"
}

dotfiles_install() {
  check_arch
  ensure_git
  get_repo
  run_setup
}

# ════════════════════════════════════════════════════════════════════════════
#  PHASE 3 — Binary-only install  (any existing Hyprland system)
# ════════════════════════════════════════════════════════════════════════════

_ensure_git_any() {
  command -v git &>/dev/null && return 0
  log_step "git not found — attempting to install..."
  if command -v pacman &>/dev/null; then
    sudo pacman -Sy --noconfirm --needed git \
      || log_die "pacman could not install git."
  elif command -v apt-get &>/dev/null; then
    sudo apt-get install -y git \
      || log_die "apt-get could not install git."
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y git \
      || log_die "dnf could not install git."
  else
    log_die "git is required. Install it manually and re-run."
  fi
  log_ok "git installed."
}

_link() {
  local src="$1" dst="$2"
  local dst_dir; dst_dir="$(dirname "$dst")"
  mkdir -p "$dst_dir"
  if [[ -L "$dst" ]]; then
    local existing; existing="$(readlink "$dst")"
    if [[ "$existing" == "$src" ]]; then
      log_info "$(basename "$dst") already linked — skipping"
      return 0
    fi
    log_info "Updating symlink: $dst → $src"
  fi
  ln -sfn "$src" "$dst"
}

binary_install() {
  log_step "Installing hyprconf..."

  _ensure_git_any

  # Clone or update repo
  if [[ -d "$REPO_DIR/.git" ]]; then
    maybe_migrate_repo_to_stable
    log_step "Existing repo found — pulling latest..."
    git -C "$REPO_DIR" pull --ff-only \
      || log_warn "Fast-forward failed — continuing with existing files."
    apply_sparse_checkout
  else
    log_step "Cloning $REPO_URL → $REPO_DIR ..."
    clone_preferred_repo
  fi
  log_ok "Repository ready."

  # Symlink script and library — do not touch ~/.config/hypr
  _link "$REPO_DIR/stow/hypr/.local/bin/hyprconf" \
        "$HOME/.local/bin/hyprconf"
  _link "$REPO_DIR/stow/hypr/.local/lib/hyprconf" \
        "$HOME/.local/lib/hyprconf"

  # Symlink scripts that the binary depends on at runtime
  local _scripts_src="$REPO_DIR/stow/hypr/.config/hypr/scripts"
  local _scripts_dst="$HOME/.config/hypr/scripts"
  mkdir -p "$_scripts_dst"
  for _item in "hyprconf-tui" "theme-switcher" "switch_monitor.sh" "toggle-native-display"; do
    [[ -e "$_scripts_src/$_item" ]] && \
      _link "$_scripts_src/$_item" "$_scripts_dst/$_item"
  done

  log_ok "hyprconf installed → ~/.local/bin/hyprconf"

  # PATH hint
  if ! command -v hyprconf &>/dev/null; then
    # shellcheck disable=SC2088  # literal ~ is intentional in this user-facing hint
    log_warn "~/.local/bin is not in your PATH."
    printf '%s  Add this to your shell rc:%s\n'         "$DM" "$RS"
    printf '%s    export PATH="$HOME/.local/bin:$PATH"%s\n\n' "$AM" "$RS"
  fi

  # Python check (required for CLI backend and TUI)
  if ! command -v python3 &>/dev/null; then
    log_warn "python3 not found — CLI backend and TUI will not work."
    log_warn "Install python3 to use the hyprconf TUI."
  else
    log_ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"
    if ! python3 -c "import textual" &>/dev/null; then
      log_warn "python-textual not installed — TUI unavailable."
      log_info "Install with: sudo pacman -S python-textual  (or pip install textual)"
    else
      log_ok "python-textual available."
    fi
  fi

  printf '\n%s  hyprconf is ready.%s\n'             "$GR" "$RS"
  printf '%s  Run:%s hyprconf help\n\n'              "$DM" "$RS"
}

# ════════════════════════════════════════════════════════════════════════════
#  Entry
# ════════════════════════════════════════════════════════════════════════════

main() {
  print_banner

  # CI mode: skip menu entirely and jump straight to the full Arch install.
  if [[ "$HYPRCONF_CI" == "1" ]]; then
    arch_install
    return
  fi

  # Passive detection — no writes, no network calls.
  local _existing=0
  detect_existing_install && _existing=1

  local -a _options=(
    "Full Arch Linux install   (from Arch ISO — partition, encrypt, install)"
    "Dotfiles only             (existing Arch system)"
  )

  if (( _existing )); then
    _options+=(
      "hyprconf only             (update existing install) ← recommended"
    )
  else
    _options+=(
      "hyprconf only             (any existing Hyprland system)"
    )
  fi

  local _default=$(( _existing ? 2 : 0 ))
  local _choice

  if [[ -t 0 && -t 1 ]]; then
    _choice="$(arrow_select -d "$_default" 'What would you like to do?' "${_options[@]}")" \
      || { printf '\n'; log_die "No selection made."; }
  else
    printf '%s  What would you like to do?%s\n\n' "$WH" "$RS"
    local _i=1
    for _opt in "${_options[@]}"; do
      printf '%s  [%d]%s %s\n' "$WH" "$_i" "$RS" "$_opt"
      (( _i++ ))
    done
    if (( _existing )); then
      printf '\n%s  Existing install detected — default: [3]%s\n' "$DM" "$RS"
    fi
    printf '%s  Choice [1/2/3]: %s' "$AM" "$RS"
    read -r _raw
    # Accept empty input → default
    [[ -z "$_raw" ]] && _raw=$(( _default + 1 ))
    _choice=$(( _raw - 1 ))
  fi

  case "$_choice" in
    0) arch_install ;;
    1) dotfiles_install ;;
    2) binary_install ;;
    *) log_die "Invalid choice." ;;
  esac
}

main "$@"
