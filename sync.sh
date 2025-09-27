#!/bin/bash
set -e

# === Colors ===
GREEN="\e[32m"
YELLOW="\e[33m"
RED="\e[31m"
RESET="\e[0m"

# === Logging Functions ===
log_info() { echo -e "${GREEN}==> $1${RESET}"; }
log_warn() { echo -e "${YELLOW}==> $1${RESET}"; }
log_error() { echo -e "${RED}==> $1${RESET}"; }

# === System Update & Packages ===
log_info "Updating system and installing dependencies..."
sudo pacman -Syu --noconfirm

packages=(
    git base-devel zsh curl wget unzip
    hyprland kitty waybar wofi dunst fastfetch
)

for pkg in "${packages[@]}"; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
        log_info "Installing $pkg..."
        sudo pacman -S --noconfirm "$pkg"
    else
        log_info "$pkg already installed, skipping..."
    fi
done

# === Create Required Directories ===
log_info "Creating required directories..."
mkdir -p ~/.config/{hypr,kitty,waybar,wofi,dunst,fastfetch}
mkdir -p ~/.local/share/zsh/plugins
mkdir -p ~/Pictures ~/Downloads ~/.wallpaper

# === Clone or Update hyprconf ===
if [ ! -d ~/.hyprconf ]; then
    log_info "Cloning hyprconf repo..."
    git clone https://github.com/ak4dev/.hyprconf ~/.hyprconf
else
    log_info "hyprconf already cloned, pulling latest changes..."
    git -C ~/.hyprconf pull
fi

# === Oh My Zsh Installation ===
if [ ! -d ~/.oh-my-zsh ]; then
    log_info "Installing Oh My Zsh..."
    export RUNZSH=no
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
else
    log_info "Oh My Zsh already installed, skipping..."
fi

# === Powerlevel10k Theme ===
if [ ! -d ~/powerlevel10k ]; then
    log_info "Installing Powerlevel10k..."
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/powerlevel10k
else
    log_info "Powerlevel10k already installed, pulling updates..."
    git -C ~/powerlevel10k pull
fi

# === Zsh Plugins Installation ===
sudo mkdir -p /usr/share/zsh/plugins

if [ ! -d /usr/share/zsh/plugins/zsh-autosuggestions ]; then
    log_info "Installing zsh-autosuggestions..."
    sudo git clone https://github.com/zsh-users/zsh-autosuggestions /usr/share/zsh/plugins/zsh-autosuggestions
else
    log_info "zsh-autosuggestions already installed, pulling updates..."
    sudo git -C /usr/share/zsh/plugins/zsh-autosuggestions pull
fi

if [ ! -d /usr/share/zsh/plugins/zsh-syntax-highlighting ]; then
    log_info "Installing zsh-syntax-highlighting..."
    sudo git clone https://github.com/zsh-users/zsh-syntax-highlighting /usr/share/zsh/plugins/zsh-syntax-highlighting
else
    log_info "zsh-syntax-highlighting already installed, pulling updates..."
    sudo git -C /usr/share/zsh/plugins/zsh-syntax-highlighting pull
fi

# === Update ~/.zshrc Safely ===
ZSHRC="$HOME/.zshrc"
log_info "Ensuring .zshrc has necessary config..."

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
add_if_missing "alias hyprsync='~/.hyprconf/sync.sh'"

# === Set Zsh as Default Shell Safely ===
current_shell="$(getent passwd "$USER" | cut -d: -f7)"
zsh_path="$(command -v zsh)"

if [ "$current_shell" != "$zsh_path" ]; then
    log_info "Setting Zsh as the default shell..."
    chsh -s "$zsh_path"
else
    log_info "Zsh is already the default shell."
fi

# === Sync Config Files from ~/.hyprconf/configs to ~/.config ===
log_info "Syncing config files from ~/.hyprconf/configs to ~/.config..."

sync_config_file() {
    src="$1"
    dest="$2"

    if [ ! -f "$dest" ]; then
        log_info "Copying new config: $dest"
        cp "$src" "$dest"
    else
        src_hash=$(sha256sum "$src" | awk '{print $1}')
        dest_hash=$(sha256sum "$dest" | awk '{print $1}')
        if [ "$src_hash" != "$dest_hash" ]; then
            log_info "Updating changed config: $dest"
            cp "$src" "$dest"
        else
            log_info "No changes in: $dest"
        fi
    fi
}

HYPRCONF_SOURCE="$HOME/.hyprconf/configs"
if [ -d "$HYPRCONF_SOURCE" ]; then
    find "$HYPRCONF_SOURCE" -type f | while read -r src_file; do
        relative_path="${src_file#$HYPRCONF_SOURCE/}"
        dest_file="$HOME/.config/$relative_path"
        mkdir -p "$(dirname "$dest_file")"
        sync_config_file "$src_file" "$dest_file"
    done
else
    log_warn "No configs directory found in ~/.hyprconf. Skipping config sync."
fi

# === Ensure sync.sh is Executable and Run ===
if [ -f ~/.hyprconf/sync.sh ]; then
    chmod +x ~/.hyprconf/sync.sh
    log_info "Running hyprsync..."
    ~/.hyprconf/sync.sh
else
    log_warn "hyprsync script not found at ~/.hyprconf/sync.sh"
fi

log_info "Setup complete! Please restart your terminal for changes to take effect."

