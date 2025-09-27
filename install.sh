#!/bin/bash
set -e

# Colors
GREEN="\e[32m"
RESET="\e[0m"

echo -e "${GREEN}==> Updating system and installing dependencies...${RESET}"
sudo pacman -Syu --noconfirm

# Packages to install
packages=(
    git base-devel zsh curl wget unzip
    hyprland kitty waybar wofi dunst fastfetch
)

for pkg in "${packages[@]}"; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
        echo -e "${GREEN}Installing $pkg...${RESET}"
        sudo pacman -S --noconfirm "$pkg"
    else
        echo -e "${GREEN}$pkg already installed, skipping...${RESET}"
    fi
done

# Ensure directories exist
echo -e "${GREEN}==> Creating required directories...${RESET}"
mkdir -p ~/.config/{hypr,kitty,waybar,wofi,dunst,fastfetch}
mkdir -p ~/.local/share/zsh/plugins
mkdir -p ~/Pictures ~/Downloads ~/.wallpaper

# Clone hyprconf if not already
if [ ! -d ~/.hyprconf ]; then
    echo -e "${GREEN}==> Cloning hyprconf repo...${RESET}"
    git clone https://github.com/ak4dev/.hyprconf ~/.hyprconf
else
    echo -e "${GREEN}hyprconf already cloned, pulling latest changes...${RESET}"
    git -C ~/.hyprconf pull
fi

# Install Oh My Zsh if not already
if [ ! -d ~/.oh-my-zsh ]; then
    echo -e "${GREEN}==> Installing Oh My Zsh...${RESET}"
    export RUNZSH=no
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
else
    echo -e "${GREEN}Oh My Zsh already installed, skipping...${RESET}"
fi

# Install Powerlevel10k theme
if [ ! -d ~/powerlevel10k ]; then
    echo -e "${GREEN}==> Installing Powerlevel10k...${RESET}"
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/powerlevel10k
else
    echo -e "${GREEN}Powerlevel10k already installed, skipping...${RESET}"
fi

# Install Zsh plugins
sudo mkdir -p /usr/share/zsh/plugins

if [ ! -d /usr/share/zsh/plugins/zsh-autosuggestions ]; then
    sudo git clone https://github.com/zsh-users/zsh-autosuggestions /usr/share/zsh/plugins/zsh-autosuggestions
else
    echo -e "${GREEN}zsh-autosuggestions already installed, skipping...${RESET}"
fi

if [ ! -d /usr/share/zsh/plugins/zsh-syntax-highlighting ]; then
    sudo git clone https://github.com/zsh-users/zsh-syntax-highlighting /usr/share/zsh/plugins/zsh-syntax-highlighting
else
    echo -e "${GREEN}zsh-syntax-highlighting already installed, skipping...${RESET}"
fi

# Build or update .zshrc
ZSHRC="$HOME/.zshrc"
echo -e "${GREEN}==> Ensuring .zshrc has necessary config...${RESET}"

add_if_missing() {
    local line="$1"
    grep -qxF "$line" "$ZSHRC" || echo "$line" >> "$ZSHRC"
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

# Set Zsh as default
if [ "$SHELL" != "/bin/zsh" ]; then
    echo -e "${GREEN}==> Setting Zsh as the default shell...${RESET}"
    chsh -s /bin/zsh
fi

# Ensure sync.sh is executable
if [ -f ~/.hyprconf/sync.sh ]; then
    chmod +x ~/.hyprconf/sync.sh
fi

# Run the sync script
echo -e "${GREEN}==> Running hyprsync...${RESET}"
~/.hyprconf/sync.sh || echo -e "${GREEN}hyprsync script failed or not present.${RESET}"

echo -e "${GREEN}==> Setup complete! Please restart your terminal for changes to take effect.${RESET}"

