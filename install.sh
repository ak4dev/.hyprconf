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

# === Update system & install packages ===
log_info "Updating system and installing dependencies..."

sudo pacman -Syu --noconfirm

packages=(
    git base-devel zsh curl wget unzip
    hyprland kitty waybar wofi dunst fastfetch
    stow
)

for pkg in "${packages[@]}"; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
        log_info "Installing $pkg..."
        sudo pacman -S --noconfirm "$pkg"
    else
        log_info "$pkg already installed, skipping..."
    fi
done

# === Create required directories ===
log_info "Creating required directories..."
mkdir -p ~/.config/{hypr,kitty,waybar,wofi,dunst,fastfetch}
mkdir -p ~/.local/share/zsh/plugins
mkdir -p ~/Pictures ~/Downloads ~/.wallpaper

# === Clone or update hyprconf repo ===
HYPRCONF_DIR="$HOME/.hyprconf"
if [ ! -d "$HYPRCONF_DIR" ]; then
    log_info "Cloning hyprconf repo..."
    git clone https://github.com/ak4dev/.hyprconf "$HYPRCONF_DIR"
else
    log_info "Updating hyprconf repo..."
    git -C "$HYPRCONF_DIR" pull
fi

# === Oh My Zsh Installation ===
if [ ! -d ~/.oh-my-zsh ]; then
    log_info "Installing Oh My Zsh..."
    export RUNZSH=no
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
else
    log_info "Oh My Zsh already installed, skipping..."
fi

# === Powerlevel10k theme ===
P10K_DIR="$HOME/powerlevel10k"
if [ ! -d "$P10K_DIR" ]; then
    log_info "Installing Powerlevel10k..."
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
else
    log_info "Updating Powerlevel10k..."
    git -C "$P10K_DIR" pull
fi

# === Zsh plugins installation ===
ZSH_PLUGINS_DIR="/usr/share/zsh/plugins"
sudo mkdir -p /usr/share/zsh/plugins

ZSH_AUTOSUGGESTIONS_DIR="/usr/share/zsh/plugins/zsh-autosuggestions"
if [ ! -d "$ZSH_AUTOSUGGESTIONS_DIR" ]; then
    log_info "Installing zsh-autosuggestions..."
    sudo git clone https://github.com/zsh-users/zsh-autosuggestions "$ZSH_AUTOSUGGESTIONS_DIR"
elif [ -d "$ZSH_AUTOSUGGESTIONS_DIR/.git" ]; then
    log_info "Updating zsh-autosuggestions..."
    sudo git -C "$ZSH_AUTOSUGGESTIONS_DIR" pull
else
    log_warn "$ZSH_AUTOSUGGESTIONS_DIR exists but is not a git repository, removing and reinstalling..."
    sudo rm -rf "$ZSH_AUTOSUGGESTIONS_DIR"
    sudo git clone https://github.com/zsh-users/zsh-autosuggestions "$ZSH_AUTOSUGGESTIONS_DIR"
fi

ZSH_SYNTAX_HIGHLIGHTING_DIR="/usr/share/zsh/plugins/zsh-syntax-highlighting"
if [ ! -d "$ZSH_SYNTAX_HIGHLIGHTING_DIR" ]; then
    log_info "Installing zsh-syntax-highlighting..."
    sudo git clone https://github.com/zsh-users/zsh-syntax-highlighting "$ZSH_SYNTAX_HIGHLIGHTING_DIR"
elif [ -d "$ZSH_SYNTAX_HIGHLIGHTING_DIR/.git" ]; then
    log_info "Updating zsh-syntax-highlighting..."
    sudo git -C "$ZSH_SYNTAX_HIGHLIGHTING_DIR" pull
else
    log_warn "$ZSH_SYNTAX_HIGHLIGHTING_DIR exists but is not a git repository, removing and reinstalling..."
    sudo rm -rf "$ZSH_SYNTAX_HIGHLIGHTING_DIR"
    sudo git clone https://github.com/zsh-users/zsh-syntax-highlighting "$ZSH_SYNTAX_HIGHLIGHTING_DIR"
fi


# === Update ~/.zshrc safely ===
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

# === Set Zsh as default shell if not already ===
if [ "$SHELL" != "$(command -v zsh)" ]; then
    log_info "Setting Zsh as the default shell..."
    chsh -s "$(command -v zsh)"
else
    log_info "Zsh is already the default shell."
fi

# === Force stow package with safe backup ===
force_stow_package() {
    local package="$1"
    local stow_dir="$2"
    local target_dir="$3"

    # Attempt stow normally
    if stow -d "$stow_dir" -t "$target_dir" "$package" 2>&1 | tee /tmp/stow_output.log | grep -q "existing target is neither a link nor a directory"; then
        log_warn "Conflict detected in $package. Backing up conflicting files and restowing..."

        # Unstow first to clean symlinks
        stow -d "$stow_dir" -t "$target_dir" -D "$package" || true

        # Backup conflicting files
        find "$stow_dir/$package" -type f | while read -r file; do
            rel_path="${file#$stow_dir/$package/}"
            target_file="$target_dir/$rel_path"
            if [ -f "$target_file" ] && [ ! -L "$target_file" ]; then
                backup_file="${target_file}.backup.$(date +%Y%m%d%H%M%S)"
                mv "$target_file" "$backup_file"
                log_info "Backed up $target_file to $backup_file"
            fi
        done

        # Stow again after backup
        stow -d "$stow_dir" -t "$target_dir" "$package"
    fi
}

# === Symlink dotfiles with Stow ===
STOW_DIR="$HYPRCONF_DIR/stow"
if [ -d "$STOW_DIR" ]; then
    for package_path in "$STOW_DIR"/*; do
        if [ -d "$package_path" ]; then
            pkg_name=$(basename "$package_path")
            log_info "Stowing $pkg_name..."
            force_stow_package "$pkg_name" "$STOW_DIR" "$HOME"
        fi
    done
else
    log_warn "Stow directory not found at $STOW_DIR. Skipping stow step."
fi

# === Ensure hyprsync script executable and run ===
if [ -f "$HYPRCONF_DIR/sync.sh" ]; then
    chmod +x "$HYPRCONF_DIR/sync.sh"
    log_info "Running hyprsync..."
    "$HYPRCONF_DIR/sync.sh"
else
    log_warn "hyprsync script not found at $HYPRCONF_DIR/sync.sh"
fi

log_info "Setup complete! Please restart your terminal for changes to take effect."

