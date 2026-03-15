#!/usr/bin/env bash
set -euo pipefail

# === Colors for logging ===
readonly GREEN="\e[32m"
readonly YELLOW="\e[33m"
readonly RED="\e[31m"
readonly RESET="\e[0m"

log_info()  { echo -e "${GREEN}==> $1${RESET}"; }
log_warn()  { echo -e "${YELLOW}==> $1${RESET}"; }
log_error() { echo -e "${RED}==> $1${RESET}" >&2; }

readonly HYPRCONF_DIR="$HOME/.hyprconf"
readonly STOW_DIR="$HYPRCONF_DIR/stow"
readonly ZSHRC="$HOME/.zshrc"
readonly P10K_DIR="$HOME/powerlevel10k"

install_packages() {
    log_info "Installing required packages..."
    sudo pacman -Syu --noconfirm

    if [[ ! -f "$HYPRCONF_DIR/packages" ]]; then
        log_error "packages file not found at $HYPRCONF_DIR/packages"
        return 1
    fi

    # Read packages from file, ignoring empty lines and comments
    mapfile -t packages < <(grep -v '^\s*#' "$HYPRCONF_DIR/packages" | grep -v '^\s*$')

    for pkg in "${packages[@]}"; do
        if ! pacman -Qi "$pkg" &>/dev/null; then
            log_info "Installing $pkg..."
            sudo pacman -S --noconfirm "$pkg"
        else
            log_info "$pkg already installed, skipping..."
        fi
    done
}

create_directories() {
    log_info "Creating required directories..."
    mkdir -p ~/.config
    mkdir -p ~/.vscode-oss/extensions
    mkdir -p ~/Pictures ~/Downloads ~/wallpaper
}

clone_or_update_repo() {
    if [ ! -d "$HYPRCONF_DIR" ]; then
        log_info "Cloning hyprconf repo..."
        git clone https://github.com/ak4dev/.hyprconf "$HYPRCONF_DIR"
    else
        log_info "Updating hyprconf repo..."
        git -C "$HYPRCONF_DIR" pull
    fi
}

install_oh_my_zsh() {
    if [ ! -d ~/.oh-my-zsh ]; then
        log_info "Installing Oh My Zsh..."
        export RUNZSH=no
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
    else
        log_info "Oh My Zsh already installed, skipping..."
    fi
}

install_powerlevel10k() {
    if [ ! -d "$P10K_DIR" ]; then
        log_info "Installing Powerlevel10k..."
        git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
    else
        log_info "Updating Powerlevel10k..."
        git -C "$P10K_DIR" pull
    fi
}

update_zshrc() {
    log_info "Ensuring .zshrc is configured..."

    add_if_missing() {
        local line="$1"
        grep -qxF "$line" "$ZSHRC" 2>/dev/null || echo "$line" >> "$ZSHRC"
    }

    add_if_missing 'export ZSH="$HOME/.oh-my-zsh"'
    add_if_missing 'ZSH_THEME="powerlevel10k/powerlevel10k"'
    add_if_missing 'plugins=(git)'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh'
    add_if_missing 'source $ZSH/oh-my-zsh.sh'
    add_if_missing 'source ~/powerlevel10k/powerlevel10k.zsh-theme'
    add_if_missing '[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh'
    add_if_missing "alias hyprsync='~/.hyprconf/setup.sh --sync'"
    add_if_missing "fastfetch --logo arch2 --logo-color-1 green --logo-color-2 green"
}

enable_services() {
    log_info "Enabling firewalld"
    sudo systemctl enable firewalld
    log_info "Disabling sddm"
    sudo systemctl disable sddm
}

force_stow_package() {
    local package="$1"
    local stow_dir="$2"
    local target_dir="$3"

    log_info "Stowing package: $package"

    # --restow = unstow then restow; idempotent and handles stale links cleanly
    if ! stow -d "$stow_dir" -t "$target_dir" --restow "$package" 2>/dev/null; then
        log_warn "Conflict detected while stowing $package. Backing up conflicting files and retrying..."

        stow -d "$stow_dir" -t "$target_dir" -D "$package" || true

        find "$stow_dir/$package" -type f | while read -r file; do
            local rel_path="${file#$stow_dir/$package/}"
            local target_file="$target_dir/$rel_path"
            if [[ -e "$target_file" && ! -L "$target_file" ]]; then
                local backup_file="${target_file}.backup.$(date +%Y%m%d%H%M%S)"
                mv "$target_file" "$backup_file"
                log_info "Backed up $target_file to $backup_file"
            fi
        done

        stow -d "$stow_dir" -t "$target_dir" --restow "$package"
    fi

    log_info "Stowed $package"
}

sync_vscode_theme_extensions() {
    local force_copy="${1:-false}"
    local theme_source="$HYPRCONF_DIR/theme/.vscode-oss/extensions"
    local extensions_dir="$HOME/.vscode-oss/extensions"

    if [ ! -d "$theme_source" ]; then
        log_warn "VS Code theme source not found at $theme_source. Skipping copy."
        return
    fi

    mkdir -p "$extensions_dir"

    while IFS= read -r -d '' theme_pkg; do
        local pkg_name
        pkg_name=$(basename "$theme_pkg")
        local dest_pkg="$extensions_dir/$pkg_name"

        if [ -d "$dest_pkg" ] && [ "$force_copy" != "true" ]; then
            log_info "VS Code theme $pkg_name already present, skipping copy."
            continue
        fi

        if [ -d "$dest_pkg" ]; then
            rm -rf "$dest_pkg"
        fi

        log_info "Copying VS Code theme $pkg_name into $extensions_dir..."
        cp -a "$theme_pkg" "$dest_pkg"
    done < <(find "$theme_source" -mindepth 1 -maxdepth 1 -type d -print0)
}


purge_broken_symlinks() {
    log_info "Pruning broken symlinks..."

    local pruned=0
    while IFS= read -r -d '' link; do
        rm "$link"
        log_info "  Removed broken symlink: $link"
        (( pruned++ )) || true
    done < <(find "$HOME/.config" -maxdepth 2 -xtype l -print0)

    while IFS= read -r -d '' link; do
        rm "$link"
        log_info "  Removed broken symlink: $link"
        (( pruned++ )) || true
    done < <(find "$HOME" -maxdepth 1 -xtype l -print0)

    log_info "Pruned $pruned broken symlink(s)."
}


detect_gpu_and_link_monitor_config() {
    log_info "Detecting GPU for monitor config..."

    local gpu_info
    gpu_info=$(lspci | grep -i vga || true)

    local monitors_conf="$HOME/.config/hypr/monitors.conf"
    local hypr_conf_dir="$STOW_DIR/hypr/.config/hypr"

    rm -f "$monitors_conf"

    if echo "$gpu_info" | grep -qi "4090"; then
        log_info "RTX 4090 detected, using pcMonitors.conf"
        ln -sf "$hypr_conf_dir/pcMonitors.conf" "$monitors_conf"
    else
        log_info "No RTX 4090 detected; using laptopMonitors.conf"
        ln -sf "$hypr_conf_dir/laptopMonitors.conf" "$monitors_conf"
        log_info "Enabling power-profiles-daemon"
        sudo systemctl enable --now power-profiles-daemon
    fi
}

stow_all_packages() {
    log_info "Stowing all packages..."

    while IFS= read -r -d '' pkg; do
        local pkg_name
        pkg_name=$(basename "$pkg")
        force_stow_package "$pkg_name" "$STOW_DIR" "$HOME"
    done < <(find "$STOW_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

    detect_gpu_and_link_monitor_config
}

main() {
    if [[ "${1:-}" == "--sync" ]]; then
        log_info "Syncing configs..."
        clone_or_update_repo
        purge_broken_symlinks
        sync_vscode_theme_extensions
        stow_all_packages
        hyprctl reload
        log_info "Sync complete!"
        return 0
    fi

    install_packages
    create_directories
    clone_or_update_repo
    sync_vscode_theme_extensions
    install_oh_my_zsh
    install_powerlevel10k
    update_zshrc
    stow_all_packages
    enable_services
    hyprctl reload
    log_info "Setup complete. Restart your terminal or source your ~/.zshrc."
}

main "$@"
