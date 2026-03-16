#!/usr/bin/env bash
#
#  hyprconf — universal installer
#  hosted at: https://hyprconf.sh
#
#  usage:
#    bash <(curl -fsSL https://hyprconf.sh)
#
#  Presents two modes after the banner:
#    [1] Full Arch Linux install  (run from the Arch ISO)
#        Partitions disk, LUKS2 encrypts, creates btrfs subvolumes, installs
#        base system, configures with systemd-boot, then stages dotfiles for
#        automatic setup on first login.
#    [2] Dotfiles only  (existing Arch installation)
#        Clones the repo and hands off to setup.sh — original behaviour.

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

# ════════════════════════════════════════════════════════════════════════════
#  PHASE 1 — Full Arch Linux Installation
# ════════════════════════════════════════════════════════════════════════════

check_iso_env() {
  log_step "Checking environment..."
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
  log_ok "Username: $USERNAME  Hostname: $USER_HOSTNAME"
}

detect_timezone() {
  log_step "Detecting timezone from IP..."
  local suggested
  suggested=$(curl -fsSL --max-time 5 "https://ipapi.co/timezone" 2>/dev/null || echo "")
  # Fall back to UTC if the response looks wrong
  [[ -z "$suggested" || "$suggested" == *"{"* ]] && suggested="UTC"

  printf '\n%s  Suggested timezone: %s%s%s\n' "$DM" "$WH" "$suggested" "$RS"
  printf '%s  Accept? [Y/n]: %s' "$AM" "$RS"
  read -r tz_ans
  if [[ "${tz_ans,,}" == "n" ]]; then
    printf '%s  Timezone (e.g. Europe/London, America/New_York): %s' "$AM" "$RS"
    read -r TIMEZONE
    [[ -f "/usr/share/zoneinfo/$TIMEZONE" ]] || log_die "Unknown timezone: $TIMEZONE"
  else
    TIMEZONE="$suggested"
  fi
  log_ok "Timezone: $TIMEZONE"
}

select_disk() {
  printf '\n%s  ── Available Disks ─────────────────────────────────────────────%s\n\n' "$DM" "$RS"
  lsblk -d -p -o NAME,SIZE,MODEL -e 7,11
  printf '\n%s  Disk to install on (e.g. /dev/sda, /dev/nvme0n1): %s' "$AM" "$RS"
  read -r DISK
  [[ -b "$DISK" ]] || log_die "Not a valid block device: $DISK"
  local sz; sz=$(lsblk -d -n -o SIZE "$DISK")
  log_ok "Target disk: $DISK ($sz)"
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
  printf '%s  Timezone   :%s %s\n\n'             "$DM" "$RS" "$TIMEZONE"
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

  # Require GPT
  local disk_label
  disk_label=$(parted -s "$DISK" print 2>/dev/null | awk '/Partition Table:/{print $3}')
  [[ "$disk_label" == "gpt" ]] \
    || log_die "Disk must use GPT. Detected: '${disk_label:-unknown}'."

  local sector_size; sector_size=$(blockdev --getss "$DISK")
  local free_start free_end free_gib
  free_start=$(sgdisk -F "$DISK")
  free_end=$(sgdisk   -E "$DISK")
  free_gib=$(( (free_end - free_start) * sector_size / 1024 / 1024 / 1024 ))
  (( free_gib >= 20 )) || log_die "Only ${free_gib} GiB available — need ≥20 GiB."
  log_info "~${free_gib} GiB of free space found."

  # Next available partition number
  local next_num
  next_num=$(sgdisk --print "$DISK" 2>/dev/null \
    | awk '$1+0 > 0 {n=$1} END {print n+0+1}')

  # Reuse an existing EFI System Partition if one is present on this disk
  local existing_efi
  existing_efi=$(lsblk -lno NAME,PARTTYPE "$DISK" 2>/dev/null \
    | awk 'tolower($2)=="c12a7328-f81f-11d2-ba4b-00a0c93ec93b"{print "/dev/"$1}' \
    | head -1 || true)

  if [[ -n "$existing_efi" ]]; then
    log_info "Reusing existing EFI partition: $existing_efi"
    EFI_PART="$existing_efi"
    sgdisk -n "${next_num}:${free_start}:${free_end}" \
           -t "${next_num}:8309" -c "${next_num}:Linux LUKS" "$DISK"
    partprobe "$DISK" && sleep 1
    ROOT_PART=$(part_dev "$DISK" "$next_num")
  else
    log_info "No EFI partition found — carving EFI + root from free space."
    local efi_end=$(( free_start + (512 * 1024 * 1024 / sector_size) - 1 ))
    local root_num=$(( next_num + 1 ))
    sgdisk -n "${next_num}:${free_start}:${efi_end}"           \
           -t "${next_num}:ef00" -c "${next_num}:EFI System"   "$DISK"
    sgdisk -n "${root_num}:$(( efi_end + 1 )):${free_end}"     \
           -t "${root_num}:8309" -c "${root_num}:Linux LUKS"   "$DISK"
    partprobe "$DISK" && sleep 1
    EFI_PART=$(part_dev "$DISK" "$next_num")
    ROOT_PART=$(part_dev "$DISK" "$root_num")
    mkfs.fat -F32 -n EFI "$EFI_PART"
    log_ok "EFI: $EFI_PART"
  fi
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
  local pkgs=(base base-devel linux linux-firmware btrfs-progs networkmanager git zsh sudo nano)
  [[ -n "$CPU_UCODE" ]] && pkgs+=("$CPU_UCODE")
  pacstrap /mnt "${pkgs[@]}"
  genfstab -U /mnt >> /mnt/etc/fstab
  log_ok "Base system installed. fstab generated."
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
  gather_user_input
  detect_timezone
  select_disk
  select_partition_mode
  confirm_install

  [[ "$PART_MODE" == "full" ]] && partition_full || partition_unallocated

  setup_luks
  setup_btrfs
  mount_filesystems
  install_base_system
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
#  Entry
# ════════════════════════════════════════════════════════════════════════════

main() {
  print_banner

  printf '%s  What would you like to do?%s\n\n' "$WH" "$RS"
  printf '%s  [1]%s Full Arch Linux install  %s(from Arch ISO — partition, encrypt, install)%s\n' "$WH" "$RS" "$DM" "$RS"
  printf '%s  [2]%s Dotfiles only             %s(existing Arch system)%s\n\n'                      "$WH" "$RS" "$DM" "$RS"
  printf '%s  Choice [1/2]: %s' "$AM" "$RS"
  read -r install_mode

  case "$install_mode" in
    1) arch_install ;;
    2) dotfiles_install ;;
    *) log_die "Invalid choice." ;;
  esac
}

main "$@"
