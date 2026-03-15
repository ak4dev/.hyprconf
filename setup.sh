#!/usr/bin/env bash
set -euo pipefail

# ── Palette (matches deploy.sh / teardown.sh / install.sh) ───────────────────
if [[ -t 1 ]]; then
  WH=$'\e[1;37m' GL=$'\e[1;31m' AM=$'\e[1;33m'
  GR=$'\e[1;32m' DM=$'\e[2;37m' RS=$'\e[0m'
else
  WH='' GL='' AM='' GR='' DM='' RS=''
fi

log_step() { printf '%s  ▸ %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_ok()   { printf '%s  ✔ %s%s%s\n'        "$GR" "$WH" "$1" "$RS"; }
log_warn() { printf '%s  ! %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_die()  { printf '%s  ✘ FATAL: %s%s%s\n' "$GL" "$WH" "$1" "$RS" >&2; exit 1; }

readonly HYPRCONF_DIR="$HOME/.hyprconf"
readonly STOW_DIR="$HYPRCONF_DIR/stow"
readonly ZSHRC="$HOME/.zshrc"
readonly P10K_DIR="$HOME/powerlevel10k"

print_header() {
  local mode="${1:-setup}"
  printf '\n%s  ──────────────────────────────────────────────────────────────%s\n' "$DM" "$RS"
  printf '%s  .hyprconf  ▸  %s%s\n' "$WH" "$mode" "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────%s\n\n' "$DM" "$RS"
}

configure_pacman() {
    log_step "Configuring pacman..."
    local conf="/etc/pacman.conf"
    local modified=0

    # Uncomment a standalone flag (e.g., Color, ILoveCandy, VerbosePkgLists)
    _pac_flag() {
        grep -q "^${1}$" "$conf" && return
        if grep -q "^#${1}$" "$conf"; then
            sudo sed -i "0,/^#${1}$/s/^#${1}$/${1}/" "$conf"
        else
            sudo sed -i "/^\[options\]/a ${1}" "$conf"
        fi
        (( modified++ )) || true
    }

    # Ensure a key = value option is set (uncomment or insert)
    _pac_kv() {
        local key="$1" val="$2"
        grep -q "^${key} = " "$conf" && return
        if grep -q "^#${key} = " "$conf"; then
            sudo sed -i "0,/^#${key} = .*/s/^#${key} = .*/${key} = ${val}/" "$conf"
        else
            sudo sed -i "/^\[options\]/a ${key} = ${val}" "$conf"
        fi
        (( modified++ )) || true
    }

    _pac_flag "Color"           # coloured output
    _pac_flag "ILoveCandy"      # Pac-Man progress bar
    _pac_flag "VerbosePkgLists" # table view when installing many packages
    _pac_flag "CheckSpace"      # pre-flight disk-space check
    _pac_kv   "ParallelDownloads" "5"

    # Enable [multilib] repo (32-bit libraries, required by Steam and friends)
    if ! grep -q '^\[multilib\]' "$conf"; then
        sudo sed -i 's/^#\[multilib\]$/[multilib]/' "$conf"
        sudo sed -i '/^\[multilib\]$/{n; s/^#Include/Include/}' "$conf"
        (( modified++ )) || true
        log_step "Refreshing package databases (multilib enabled)..."
        sudo pacman -Sy --noconfirm
    fi

    if [[ $modified -gt 0 ]]; then
        log_ok "pacman.conf updated (${modified} change(s))."
    else
        log_ok "pacman.conf already configured."
    fi
}


install_packages() {
    log_step "Installing required packages..."
    sudo pacman -Syu --noconfirm

    if [[ ! -f "$HYPRCONF_DIR/packages" ]]; then
        log_die "packages file not found at $HYPRCONF_DIR/packages"
    fi

    mapfile -t packages < <(grep -v '^\s*#' "$HYPRCONF_DIR/packages" | grep -v '^\s*$')

    local missing=()
    for pkg in "${packages[@]}"; do
        pacman -Qi "$pkg" &>/dev/null || missing+=("$pkg")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_step "Installing ${#missing[@]} missing package(s)..."
        sudo pacman -S --noconfirm --needed "${missing[@]}"
    fi
    log_ok "All packages installed."
}

create_directories() {
    log_step "Creating required directories..."
    mkdir -p ~/.config ~/.local/bin ~/.vscode-oss/extensions
    mkdir -p ~/Pictures ~/Downloads ~/wallpaper
    log_ok "Directories ready."
}

clone_or_update_repo() {
    if [ ! -d "$HYPRCONF_DIR/.git" ]; then
        log_step "Cloning hyprconf repo..."
        git clone https://github.com/ak4dev/.hyprconf "$HYPRCONF_DIR"
    else
        log_step "Updating hyprconf repo..."
        git -C "$HYPRCONF_DIR" pull --ff-only || log_warn "Fast-forward pull failed — using existing files."
    fi
    log_ok "Repository ready."
}

install_oh_my_zsh() {
    if [ ! -d ~/.oh-my-zsh ]; then
        log_step "Installing Oh My Zsh..."
        export RUNZSH=no
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
        log_ok "Oh My Zsh installed."
    else
        log_ok "Oh My Zsh already installed."
    fi
}

install_powerlevel10k() {
    if [ ! -d "$P10K_DIR" ]; then
        log_step "Installing Powerlevel10k..."
        git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
        log_ok "Powerlevel10k installed."
    else
        log_step "Updating Powerlevel10k..."
        git -C "$P10K_DIR" pull --ff-only || true
        log_ok "Powerlevel10k up to date."
    fi
}

update_zshrc() {
    log_step "Configuring ~/.zshrc..."

    touch "$ZSHRC"

    add_if_missing() {
        local line="$1"
        grep -qxF "$line" "$ZSHRC" 2>/dev/null || echo "$line" >> "$ZSHRC"
    }

    if grep -q '^ZSH_THEME=' "$ZSHRC" 2>/dev/null; then
        sed -i 's|^ZSH_THEME=.*|ZSH_THEME="powerlevel10k/powerlevel10k"|' "$ZSHRC"
    else
        add_if_missing 'ZSH_THEME="powerlevel10k/powerlevel10k"'
    fi

    add_if_missing 'export ZSH="$HOME/.oh-my-zsh"'
    add_if_missing 'plugins=(git)'
    add_if_missing 'source $ZSH/oh-my-zsh.sh'

    add_if_missing 'source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh'
    add_if_missing 'source ~/powerlevel10k/powerlevel10k.zsh-theme'
    add_if_missing '[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh'

    add_if_missing 'export PATH="$HOME/.local/bin:$PATH"'
    add_if_missing "alias hyprsync='~/.hyprconf/setup.sh --sync'"
    add_if_missing "fastfetch --logo arch2 --logo-color-1 green --logo-color-2 green"

    log_ok "~/.zshrc configured."
}

configure_zprofile() {
    log_step "Configuring ~/.zprofile..."
    local zprofile="$HOME/.zprofile"
    local autostart='[[ $(tty) == /dev/tty1 ]] && exec Hyprland'
    grep -qxF "$autostart" "$zprofile" 2>/dev/null || echo "$autostart" >> "$zprofile"
    log_ok "Hyprland auto-start configured in ~/.zprofile"
}

setup_user_dirs() {
    log_step "Initialising XDG user directories..."
    xdg-user-dirs-update
    log_ok "XDG user directories ready."
}

force_stow_package() {
    local package="$1"
    local stow_dir="$2"
    local target_dir="$3"

    log_step "Stowing $package..."

    if ! stow -d "$stow_dir" -t "$target_dir" --restow "$package" 2>/dev/null; then
        log_warn "Conflict in $package — backing up and retrying..."

        stow -d "$stow_dir" -t "$target_dir" -D "$package" || true

        find "$stow_dir/$package" -type f | while read -r file; do
            local rel_path="${file#$stow_dir/$package/}"
            local target_file="$target_dir/$rel_path"
            if [[ -L "$target_file" ]]; then
                rm "$target_file"
            elif [[ -e "$target_file" ]]; then
                mv "$target_file" "${target_file}.backup.$(date +%Y%m%d%H%M%S)"
            fi
        done

        stow -d "$stow_dir" -t "$target_dir" --restow "$package"
    fi

    log_ok "Stowed $package."
}

sync_vscode_theme_extensions() {
    local force_copy="${1:-false}"
    local theme_source="$HYPRCONF_DIR/theme/.vscode-oss/extensions"
    local extensions_dir="$HOME/.vscode-oss/extensions"

    if [ ! -d "$theme_source" ]; then
        log_warn "VS Code theme source not found — skipping."
        return
    fi

    mkdir -p "$extensions_dir"

    while IFS= read -r -d '' theme_pkg; do
        local pkg_name; pkg_name=$(basename "$theme_pkg")
        local dest_pkg="$extensions_dir/$pkg_name"

        if [ -d "$dest_pkg" ] && [ "$force_copy" != "true" ]; then
            log_ok "VS Code extension $pkg_name already present."
            continue
        fi

        [ -d "$dest_pkg" ] && rm -rf "$dest_pkg"
        log_step "Copying VS Code extension $pkg_name..."
        cp -a "$theme_pkg" "$dest_pkg"
        log_ok "Copied $pkg_name."
    done < <(find "$theme_source" -mindepth 1 -maxdepth 1 -type d -print0)
}

purge_broken_symlinks() {
    log_step "Pruning broken symlinks..."

    local pruned=0
    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME/.config" -maxdepth 2 -xtype l -print0)

    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME/.local/bin" -maxdepth 1 -xtype l -print0 2>/dev/null)

    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME" -maxdepth 1 -xtype l -print0)

    log_ok "Pruned $pruned broken symlink(s)."
}

detect_gpu_and_link_monitor_config() {
    log_step "Detecting GPU for monitor config..."

    local gpu_info; gpu_info=$(lspci | grep -i vga || true)
    local monitors_conf="$HOME/.config/hypr/monitors.conf"
    local hypr_conf_dir="$STOW_DIR/hypr/.config/hypr"

    rm -f "$monitors_conf"

    if echo "$gpu_info" | grep -qi "5090"; then
        ln -sf "$hypr_conf_dir/pcMonitors.conf" "$monitors_conf"
        log_ok "RTX 5090 detected — using pcMonitors.conf"
    else
        ln -sf "$hypr_conf_dir/laptopMonitors.conf" "$monitors_conf"
        log_ok "Using laptopMonitors.conf"
        log_step "Enabling power-profiles-daemon..."
        sudo systemctl enable --now power-profiles-daemon
    fi
}

stow_all_packages() {
    log_step "Stowing all config packages..."

    while IFS= read -r -d '' pkg; do
        local pkg_name; pkg_name=$(basename "$pkg")
        force_stow_package "$pkg_name" "$STOW_DIR" "$HOME"
    done < <(find "$STOW_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

    detect_gpu_and_link_monitor_config
    log_ok "All packages stowed."
}

enable_services() {
    log_step "Configuring firewall (ufw)..."
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw enable
    sudo systemctl enable --now ufw

    log_step "Disabling display manager (sddm)..."
    sudo systemctl disable --now sddm 2>/dev/null \
        || log_warn "sddm not found or already disabled — skipping."
    log_ok "Security services configured."
}

sync_services() {
    log_step "Enabling system services..."
    sudo systemctl enable --now NetworkManager
    sudo systemctl enable --now bluetooth
    sudo systemctl enable --now ufw
    log_ok "Services running."
}

reload_hyprland() {
    if hyprctl reload 2>/dev/null; then
        log_ok "Hyprland reloaded."
    else
        log_warn "Hyprland not running — reload skipped."
    fi
}

main() {
    if [[ "${1:-}" == "--sync" ]]; then
        print_header "sync"
        log_step "Syncing configs..."
        clone_or_update_repo
        purge_broken_symlinks
        sync_vscode_theme_extensions
        stow_all_packages
        update_zshrc
        configure_zprofile
        sync_services
        reload_hyprland
        printf '\n%s  ✔ Sync complete.%s\n\n' "$GR" "$RS"
        return 0
    fi

    # Show full banner only when invoked directly (not from install.sh)
    if [[ -z "${HYPRCONF_INSTALLER:-}" ]]; then
        local banner_src="$HYPRCONF_DIR/assets/banner.sh"
        if [[ -f "$banner_src" ]]; then
            # shellcheck source=assets/banner.sh
            source "$banner_src"
            print_banner
        else
            print_header "setup"
        fi
    fi

    configure_pacman
    install_packages
    create_directories
    clone_or_update_repo
    sync_vscode_theme_extensions
    install_oh_my_zsh
    install_powerlevel10k
    update_zshrc
    configure_zprofile
    setup_user_dirs
    purge_broken_symlinks
    stow_all_packages
    enable_services
    sync_services
    reload_hyprland

    printf '\n%s  ✔ Setup complete. Restart your terminal or source your ~/.zshrc.%s\n\n' "$GR" "$RS"
}

main "$@"
