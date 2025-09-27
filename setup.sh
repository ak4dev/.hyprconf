#!/bin/bash
set -e

# === Color Logging ===
GREEN="\e[32m"
YELLOW="\e[33m"
RED="\e[31m"
RESET="\e[0m"

log_info()  { echo -e "${GREEN}==> $1${RESET}"; }
log_warn()  { echo -e "${YELLOW}==> $1${RESET}"; }
log_error() { echo -e "${RED}==> $1${RESET}"; }

# === Variables ===
HYPRCONF_DIR="$HOME/.hyprconf"
STOW_DIR="$HYPRCONF_DIR/stow"
ZSHRC="$HOME/.zshrc"
P10K_DIR="$HOME/powerlevel10k"
ZSH_PLUGINS_DIR="/usr/share/zsh/plugins"

# === Core Functions ===

install_packages() {
    log_info "Installing required packages..."
    sudo pacman -Syu --noconfirm

    local packages=(
        git base-devel zsh curl wget unzip
        hyprland kitty waybar wofi dunst fastfetch
        stow
    )

    for pkg in "${packages[@]}"; do
        if ! pacman -Qi "$pkg" &>/dev/null; then
            log_info "Installing $pkg..."
            sudo pacman -S --noconfirm "$pkg"
        else
            log_info "$pkg already installed."
        fi
    done
}

create_directories() {
    log_info "Creating required directories..."
    mkdir -p ~/.config/{hypr,kitty,waybar,wofi,dunst,fastfetch}
    mkdir -p ~/.local/share/zsh/plugins
    mkdir -p ~/Pictures ~/Downloads ~/.wallpaper
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
        log_info "Oh My Zsh already installed."
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

install_zsh_plugins() {
    sudo mkdir -p "$ZSH_PLUGINS_DIR"

    local plugins=(
        "zsh-users/zsh-autosuggestions"
        "zsh-users/zsh-syntax-highlighting"
    )

    for plugin_repo in "${plugins[@]}"; do
        plugin_name=$(basename "$plugin_repo")
        plugin_path="$ZSH_PLUGINS_DIR/$plugin_name"

        if [ -d "$plugin_path/.git" ]; then
            log_info "Updating $plugin_name..."
            sudo git -C "$plugin_path" pull
        else
            log_info "Installing $plugin_name..."
            sudo rm -rf "$plugin_path"
            sudo git clone "https://github.com/$plugin_repo" "$plugin_path"
        fi
    done
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
    add_if_missing "alias hyprsync='$0 --sync'"
}

set_default_shell() {
    if [ "$SHELL" != "$(command -v zsh)" ]; then
        log_info "Setting Zsh as default shell..."
        chsh -s "$(command -v zsh)"
    else
        log_info "Zsh is already the default shell."
    fi
}

force_stow_package() {
    local package="$1"
    local stow_dir="$2"
    local target_dir="$3"

    if stow -d "$stow_dir" -t "$target_dir" "$package" 2>&1 | grep -q "existing target is"; then
        log_warn "Conflicts detected in $package. Cleaning up..."
        stow -d "$stow_dir" -t "$target_dir" -D "$package" || true
        find "$stow_dir/$package" -type f | while read -r file; do
            local rel="${file#$stow_dir/$package/}"
            local tgt="$target_dir/$rel"
            if [ -f "$tgt" ] && [ ! -L "$tgt" ]; then
                mv "$tgt" "$tgt.backup.$(date +%Y%m%d%H%M%S)"
                log_info "Backed up $tgt"
            fi
        done
        stow -d "$stow_dir" -t "$target_dir" "$package"
    fi
}

stow_all_packages() {
    if [ ! -d "$STOW_DIR" ]; then
        log_warn "No stow directory found. Skipping stow step."
        return
    fi

    # Stow .config/* folders
    if [ -d "$STOW_DIR/.config" ]; then
        for config_pkg in "$STOW_DIR/.config"/*; do
            [ -d "$config_pkg" ] || continue
            local pkg_name=$(basename "$config_pkg")
            log_info "Stowing .config/$pkg_name..."
            force_stow_package "$pkg_name" "$STOW_DIR/.config" "$HOME/.config"
        done
    fi

    # Stow top-level stow/* packages
    for package_path in "$STOW_DIR"/*; do
        [ -d "$package_path" ] || continue
        [ "$(basename "$package_path")" != ".config" ] || continue
        local pkg_name=$(basename "$package_path")
        log_info "Stowing $pkg_name to ~..."
        force_stow_package "$pkg_name" "$STOW_DIR" "$HOME"
    done
}

sync_configs() {
    log_info "Syncing configs..."
    clone_or_update_repo
    stow_all_packages
    log_info "Sync complete!"
}

main() {
    if [[ "$1" == "--sync" ]]; then
        sync_configs
        exit 0
    fi

    install_packages
    create_directories
    clone_or_update_repo
    install_oh_my_zsh
    install_powerlevel10k
    install_zsh_plugins
    update_zshrc
    set_default_shell
    stow_all_packages
    sync_configs

    log_info "Setup complete. Restart your terminal or source your ~/.zshrc."
}

main "$@"
