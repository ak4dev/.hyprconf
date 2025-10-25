#!/bin/bash
set -e

# === Colors for logging ===
GREEN="\e[32m"
YELLOW="\e[33m"
RED="\e[31m"
RESET="\e[0m"

log_info()  { echo -e "${GREEN}==> $1${RESET}"; }
log_warn()  { echo -e "${YELLOW}==> $1${RESET}"; }
log_error() { echo -e "${RED}==> $1${RESET}"; }

HYPRCONF_DIR="$HOME/.hyprconf"
STOW_DIR="$HYPRCONF_DIR/stow"
ZSHRC="$HOME/.zshrc"
P10K_DIR="$HOME/powerlevel10k"
ZSH_PLUGIN_DIR="$HOME/.zsh/plugins"

install_packages() {
    log_info "Installing required packages..."
    sudo pacman -Syu --noconfirm

    # Check if the packages file exists
    if [[ ! -f "packages" ]]; then
        log_info "Error: 'packages' file not found!"
        exit 1
    fi

    # Read packages from the file, ignoring empty lines and comments
    mapfile -t packages < <(grep -v '^\s*#' packages | grep -v '^\s*$')

    for pkg in "${packages[@]}"; do
        if [[ "$pkg" == "nerd-fonts" ]]; then
            # Check if nerd-fonts is in the upgrade list
            if pacman -Qu | grep -q "^$pkg"; then
                log_info "Installing $pkg..."
                sudo pacman -S --noconfirm "$pkg"
            else
                log_info "$pkg already installed, skipping..."
            fi
        else
            if ! pacman -Qi "$pkg" &>/dev/null; then
                log_info "Installing $pkg..."
                sudo pacman -S --noconfirm "$pkg"
            else
                log_info "$pkg already installed, skipping..."
            fi
        fi
    done
}

create_directories() {
    log_info "Creating required directories..."
    mkdir -p ~/.config
    mkdir -p ~/.vscode-oss/extensions
    mkdir -p ~/.local/share/zsh/plugins
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

    add_if_missing "fastfetch --logo arch2 --logo-color-1 green --logo-color-2 green"
    add_if_missing 'export ZSH="$HOME/.oh-my-zsh"'
    add_if_missing 'ZSH_THEME="robbyrussell"'
    add_if_missing 'plugins=(git)'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh'
    add_if_missing 'source $ZSH/oh-my-zsh.sh'
    add_if_missing 'source ~/powerlevel10k/powerlevel10k.zsh-theme'
    add_if_missing '[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh'
    add_if_missing "alias hyprsync='~/.hyprconf/setup.sh --sync'"
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

    log_info "Preparing to stow package: $package"

    # Remove existing symlink or empty dir for clean re-stow
    local package_target="$target_dir/$package"
    if [ -L "$package_target" ]; then
        log_info "Removing existing symlink at $package_target"
        rm -f "$package_target"
    elif [ -d "$package_target" ]; then
        log_info "Removing existing directory at $package_target"
        rm -rf "$package_target"
    fi

    # Attempt to stow
    if ! stow -d "$stow_dir" -t "$target_dir" "$package" 2>/dev/null; then
        log_warn "Conflict detected while stowing $package. Backing up conflicting files and retrying..."

        # Unstow in case of partial success
        stow -d "$stow_dir" -t "$target_dir" -D "$package" || true

        # Backup conflicting files
        find "$stow_dir/$package" -type f | while read -r file; do
            rel_path="${file#$stow_dir/$package/}"
            target_file="$target_dir/$rel_path"
            if [ -e "$target_file" ] && [ ! -L "$target_file" ]; then
                backup_file="${target_file}.backup.$(date +%Y%m%d%H%M%S)"
                mv "$target_file" "$backup_file"
                log_info "Backed up $target_file to $backup_file"
            fi
        done

        # Retry stowing
        stow -d "$stow_dir" -t "$target_dir" "$package"
    else
        log_info "Successfully stowed $package"
    fi
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


detect_gpu_and_link_monitor_config() {
    log_info "Detecting GPU for monitor config..."

    GPU_INFO=$(lspci | grep -i vga || true)

    MONITORS_CONF="$HOME/.config/hypr/monitors.conf"
    HYPR_CONFIG_DIR="$STOW_DIR/.config/hypr"

    rm -f "$MONITORS_CONF"

    if echo "$GPU_INFO" | grep -qi "4090"; then
        log_info "RTX 4090 detected, using pcMonitors.conf"
        ln -sf "$HYPR_CONFIG_DIR/hypr/pcMonitors.conf" "$MONITORS_CONF"
    else
        log_info "No 4090; probably a laptop, using laptopMonitors.conf"
        ln -sf "$HYPR_CONFIG_DIR/hypr/laptopMonitors.conf" "$MONITORS_CONF"
        log_info "Enabling power-profiles-daemon"
        sudo systemctl enable --now power-profiles-daemon
    fi
}

stow_all_packages() {
    if [ ! -d "$STOW_DIR/.config" ]; then
        log_warn "Stow directory not found at $STOW_DIR/.config. Skipping."
        return
    fi

    while IFS= read -r -d '' config_pkg; do
        pkg_name=$(basename "$config_pkg")
        log_info "Stowing .config/$pkg_name..."
        force_stow_package "$pkg_name" "$STOW_DIR/.config" "$HOME/.config"
    done < <(find "$STOW_DIR/.config" -mindepth 1 -maxdepth 1 -type d -print0)

    if [ -d "$STOW_DIR/wallpaper" ]; then
        log_info "Stowing wallpaper to ~..."
        force_stow_package "wallpaper" "$STOW_DIR" "$HOME"
    fi

    if [ -d "$STOW_DIR/firefox" ]; then
        log_info "Stowing firefox configs..."
        force_stow_package "firefox" "$STOW_DIR" "$HOME"
    fi

    detect_gpu_and_link_monitor_config
}

main() {
    if [[ "$1" == "--sync" ]]; then
        log_info "Syncing configs..."
        clone_or_update_repo
        sync_vscode_theme_extensions
        stow_all_packages
        hyprctl reload
        log_info "Sync complete!"
        exit 0
    fi

    install_packages
    sudo pacman -Syu --noconfirm nerd-fonts
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
