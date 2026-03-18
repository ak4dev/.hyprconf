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
#    [3] hyprconf binary only  (any existing Hyprland system)
#        Installs the hyprconf CLI/TUI into ~/.local/bin and ~/.local/lib
#        without touching any Hyprland config files.

set -euo pipefail

readonly REPO_URL="https://github.com/ak4dev/.hyprconf"
readonly REPO_DIR="$HOME/.hyprconf"
readonly LUKS_NAME="cryptroot"
readonly BTRFS_OPTS="noatime,compress=zstd,space_cache=v2"

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
#   HYPRCONF_CI_COPY_NETCONF=0         # 0 | 1
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

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
  printf '\033[H\033[2J'
  printf '%s  ▒░▒▓▒░░▒▓░░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░▒▓%s\n' "$NG" "$RS"
  printf '%s         _                                        __%s\n'                        "$DM" "$RS"
  printf '%s        | |__  _   _ _ __  _ __ ___ ___  _ __  / _|%s\n'                       "$WH" "$RS"
  printf "%s        | '_ \\| | | | '_ \\| '__/ __/ _ \\| '_ \\| |_%s\n"                     "$GL" "$RS"
  printf '%s       _| | | | |_| | |_) | | | (_| (_) | | | |  _|%s\n'                       "$WH" "$RS"
  printf '%s     (_)|_| |_|\__, | .__/|_|  \___\___/|_| |_||_|%s\n'                        "$DM" "$RS"
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
  # Prints selected 0-based index to stdout. Display goes to /dev/tty directly
  # so this works correctly inside $() command substitutions.
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
  # Need stdin to be a TTY and /dev/tty to be openable.
  [[ -t 0 ]] || return 1
  { exec 9>/dev/tty; } 2>/dev/null || return 1

  local cur="$default_cur" key rest
  (( cur < 0 )) && cur=0
  (( cur >= n )) && cur=$(( n - 1 ))

  printf '\n%s  %s%s\n' "$WH" "$prompt" "$RS" >&9
  printf '%s  (use ↑/↓ and Enter)%s\n\n' "$DM" "$RS" >&9

  printf '\e[?25l' >&9
  trap 'printf "\e[?25h" >&9; exec 9>&-' RETURN

  while true; do
    local i
    for (( i=0; i<n; i++ )); do
      printf '\033[2K\r' >&9
      if (( i == cur )); then
        printf '%s  > %s%s\n' "$AM" "${items[i]}" "$RS" >&9
      else
        printf '    %s\n' "${items[i]}" >&9
      fi
    done

    IFS= read -rsn1 key || return 1
    case "$key" in
      $'\x1b')
        IFS= read -rsn2 rest || true
        case "$rest" in
          "[A") cur=$(( cur - 1 )) ;;
          "[B") cur=$(( cur + 1 )) ;;
        esac
        ;;
      "")
        printf '\e[?25h' >&9
        exec 9>&-
        trap - RETURN
        printf '%s\n' "$cur"
        return 0
        ;;
      k) cur=$(( cur - 1 )) ;;
      j) cur=$(( cur + 1 )) ;;
    esac

    (( cur < 0 )) && cur=0
    (( cur >= n )) && cur=$(( n - 1 ))

    printf '\033[%dA' "$n" >&9
  done
}

# ── Passive existing-install detection ───────────────────────────────────────
# Reads only — no network, no disk writes, no side effects.
# Returns 0 if any signal of an existing hyprconf/Hyprland install is found.
detect_existing_install() {
  command -v hyprconf            &>/dev/null && return 0
  [[ -f "$HOME/.local/bin/hyprconf"         ]] && return 0
  [[ -d "$REPO_DIR/.git"                    ]] && return 0
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
  if (( rc != 0 || -z "${out:-}" )); then
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

  printf '%s  Copy network config from ISO (keeps WiFi for first boot)? [Y/n]: %s' "$AM" "$RS"
  local net_ans
  read -r net_ans
  if [[ -z "$net_ans" || "${net_ans,,}" == "y" || "${net_ans,,}" == "yes" ]]; then
    COPY_NETCONF=1
  else
    COPY_NETCONF=0
  fi

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

_pick_timezone() {
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
  if (( ${#zones[@]} > 0 )) && command -v fzf &>/dev/null && [[ -t 0 && -t 1 ]]; then
    local picked
    picked=$(printf '%s\n' "${zones[@]}" | fzf \
      --prompt='  Timezone > ' \
      --height=15 \
      --reverse \
      --header='Type to filter  (e.g. Europe, America, Asia)') || true
    if [[ -n "$picked" && -f "/usr/share/zoneinfo/$picked" ]]; then
      TIMEZONE="$picked"
      return 0
    fi
    log_warn "No timezone selected via fzf — falling back."
  fi

  if (( ${#zones[@]} > 0 )) && [[ -t 0 ]]; then
    # Grouped arrow picker: let user pick a region then a city.
    local -a regions=()
    mapfile -t regions < <(printf '%s\n' "${zones[@]}" | cut -d/ -f1 | sort -u)

    if [[ -t 0 && -t 1 ]]; then
      local ridx
      ridx="$(arrow_select 'Select region' "${regions[@]}")" || ridx=""
    fi

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

    local free_bytes
    free_bytes="$(esp_free_bytes "$selected_esp" || true)"
    if [[ -n "${free_bytes:-}" ]]; then
      # Heuristic warnings: systemd-boot + kernel + fallback initramfs can be large.
      if (( free_bytes < 150 * 1024 * 1024 )); then
        log_warn "Low free space on ESP ($(human_bytes "$free_bytes")). Bootloader/kernel updates may fail."
      elif (( free_bytes < 300 * 1024 * 1024 )); then
        log_warn "ESP free space is a bit tight ($(human_bytes "$free_bytes")). Consider creating a new ESP."
      fi
    else
      log_warn "Could not determine free space on $selected_esp (mount failed). Consider creating a new ESP."
    fi

    printf '\n%s  How should we handle EFI?%s\n\n' "$WH" "$RS"
    printf '%s  [1]%s Use existing ESP (%s)\n' "$WH" "$RS" "$selected_esp"
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

    (( do_wipe == 1 )) && wipefs -af "$EFI_PART" || true
    mkfs.fat -F32 -n EFI "$EFI_PART"
    log_ok "EFI: $EFI_PART"
  else
    log_info "Reusing existing ESP: $EFI_PART"
    sgdisk -n "${next_num}:${free_start}:${free_end}" \
           -t "${next_num}:8309" -c "${next_num}:Linux LUKS" "$DISK"

    partprobe "$DISK" && sleep 1
    ROOT_PART=$(part_dev "$DISK" "$next_num")
  fi

  (( do_wipe == 1 )) && wipefs -af "$ROOT_PART" || true
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
  local pkgs=(base base-devel linux linux-firmware btrfs-progs networkmanager openssh git zsh sudo nano)
  [[ -n "$CPU_UCODE" ]] && pkgs+=("$CPU_UCODE")
  pacstrap /mnt "${pkgs[@]}"
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

  log_warn "No ISO network profiles found to copy."
}

configure_in_chroot() {
  log_step "Configuring system in chroot..."

  local root_uuid
  root_uuid=$(blkid -s UUID -o value "$ROOT_PART")

  # Pre-compute the optional ucode initrd line (empty string when no ucode package)
  local ucode_line=""
  [[ -n "$CPU_UCODE" ]] && ucode_line="initrd  /${CPU_UCODE}.img"

  # Write the chroot setup script.
  # Unquoted EOF delimiter: our outer variables (USERNAME, TIMEZONE, etc.) expand here.
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

cat > /boot/loader/entries/arch.conf << ENTRY
title   Arch Linux
linux   /vmlinuz-linux
${ucode_line}
initrd  /initramfs-linux.img
options rd.luks.name=${root_uuid}=${LUKS_NAME} root=/dev/mapper/${LUKS_NAME} rootflags=subvol=@ rw quiet
ENTRY

cat > /boot/loader/entries/arch-fallback.conf << ENTRY2
title   Arch Linux (fallback initramfs)
linux   /vmlinuz-linux
${ucode_line}
initrd  /initramfs-linux-fallback.img
options rd.luks.name=${root_uuid}=${LUKS_NAME} root=/dev/mapper/${LUKS_NAME} rootflags=subvol=@ rw
ENTRY2

# ── User ──────────────────────────────────────────────────────────────────────
useradd -m -G wheel,audio,video,storage,input,network -s /bin/zsh "${USERNAME}"
echo "${USERNAME}:${USER_PASSWORD}" | chpasswd
echo "root:${USER_PASSWORD}" | chpasswd
echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/wheel
chmod 440 /etc/sudoers.d/wheel

# ── Services ──────────────────────────────────────────────────────────────────
systemctl enable NetworkManager
systemctl enable systemd-resolved
systemctl enable sshd

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
  log_ok "Chroot configuration complete."
}

run_setup_in_chroot() {
  log_step "Cloning dotfiles repo into /home/${USERNAME}/.hyprconf ..."
  arch-chroot /mnt /bin/bash -c "
    git clone --depth=1 '${REPO_URL}' /home/${USERNAME}/.hyprconf
    chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.hyprconf
  "
  log_ok "Repo cloned."

  # Grant passwordless sudo for unattended package installation; removed when done.
  # File must sort after "wheel" alphabetically so this NOPASSWD rule wins.
  echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" > /mnt/etc/sudoers.d/zz-hyprconf-setup
  chmod 440 /mnt/etc/sudoers.d/zz-hyprconf-setup

  log_step "Running setup.sh as ${USERNAME} in chroot..."
  arch-chroot /mnt runuser -l "${USERNAME}" -c \
    "export HYPRCONF_CHROOT=1 HYPRCONF_INSTALLER=1; bash /home/${USERNAME}/.hyprconf/setup.sh"

  rm -f /mnt/etc/sudoers.d/zz-hyprconf-setup
  log_ok "Dotfiles configured."
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

  [[ "$PART_MODE" == "full" ]] && partition_full || partition_unallocated

  setup_luks
  setup_btrfs
  mount_filesystems
  install_base_system
  copy_network_config_from_iso
  configure_in_chroot
  run_setup_in_chroot
  unmount_all

  printf '\n%s  ════════════════════════════════════════════════════════════════%s\n' "$DM" "$RS"
  printf '%s  ✔ Arch Linux installed successfully!%s\n'                              "$GR" "$RS"
  printf '%s  · Remove the installation media and reboot.%s\n'                      "$DM" "$RS"
  printf '%s  · Log in as %s — Hyprland starts automatically on tty1.%s\n\n'       "$DM" "$USERNAME" "$RS"
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
  log_step "Installing hyprconf binary..."

  _ensure_git_any

  # Clone or update repo
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

  # Symlink binary and library — do not touch ~/.config/hypr
  _link "$REPO_DIR/stow/hypr/.local/bin/hyprconf" \
        "$HOME/.local/bin/hyprconf"
  _link "$REPO_DIR/stow/hypr/.local/lib/hyprconf" \
        "$HOME/.local/lib/hyprconf"

  log_ok "hyprconf installed → ~/.local/bin/hyprconf"

  # PATH hint
  if ! command -v hyprconf &>/dev/null; then
    log_warn "~/.local/bin is not in your PATH."
    printf '%s  Add this to your shell rc:%s\n'         "$DM" "$RS"
    printf '%s    export PATH="$HOME/.local/bin:$PATH"%s\n\n' "$AM" "$RS"
  fi

  # Python check (required for CLI backend and TUI)
  if ! command -v python3 &>/dev/null; then
    log_warn "python3 not found — CLI backend and TUI will not work."
    log_warn "Install python3 to use 'hyprconf configure', 'hyprconf tui', etc."
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
      "hyprconf binary only      (update existing install) ← recommended"
    )
  else
    _options+=(
      "hyprconf binary only      (any existing Hyprland system)"
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
