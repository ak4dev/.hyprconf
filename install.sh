#!/bin/bash
set -e

# Colors
GREEN="\e[32m"
RESET="\e[0m"

echo -e "${GREEN}==> Updating system and installing dependencies...${RESET}"
sudo pacman -Syu --noconfirm
sudo pacman -S --noconfirm git base-devel zsh curl wget unzip \
    hyprland kitty waybar wofi dunst fastfetch

# Ensure directories exist
echo -e "${GREEN}==> Creating required directories...${RESET}"
mkdir -p ~/.config
mkdir -p ~/.local/share
mkdir -p ~/Pictures
mkdir -p ~/Downloads

# Clone hyprconf
echo -e "${GREEN}==> Cloning hyprconf repo...${RESET}"
git clone https://github.com/ak4dev/.hyprconf ~/.hyprconf

# Create config folders referenced in hyprconf
echo -e "${GREEN}==> Ensuring all necessary config folders exist...${RESET}"
mkdir -p ~/.config/hypr
mkdir -p ~/.config/kitty
mkdir -p ~/.config/waybar
mkdir -p ~/.config/wofi
mkdir -p ~/.config/dunst
mkdir -p ~/.config/fastfetch
mkdir -p ~/.config/wallpaper

# Install Powerlevel10k
echo -e "${GREEN}==> Installing Powerlevel10k...${RESET}"
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.local/share/powerlevel10k

# Set Zsh as default shell
if [ "$SHELL" != "/bin/zsh" ]; then
    echo -e "${GREEN}==> Setting Zsh as the default shell...${RESET}"
    chsh -s /bin/zsh
fi

# Ensure Powerlevel10k is sourced in .zshrc
if ! grep -q 'powerlevel10k/powerlevel10k.zsh-theme' ~/.zshrc; then
    echo 'source ~/.local/share/powerlevel10k/powerlevel10k.zsh-theme' >> ~/.zshrc
    echo -e "${GREEN}Powerlevel10k sourced in .zshrc${RESET}"
else
    echo -e "${GREEN}Powerlevel10k already sourced, skipping...${RESET}"
fi

# Create alias for hyprsync
echo -e "${GREEN}==> Adding 'hyprsync' alias to .zshrc...${RESET}"
if ! grep -q "alias hyprsync=" ~/.zshrc; then
    echo "alias hyprsync='~/.hyprconf/sync.sh'" >> ~/.zshrc
    echo -e "${GREEN}Alias added.${RESET}"
else
    echo -e "${GREEN}Alias already exists, skipping...${RESET}"
fi

# Make sure sync.sh is executable
chmod +x ~/.hyprconf/sync.sh

# Run the sync script
echo -e "${GREEN}==> Running hyprsync...${RESET}"
~/.hyprconf/sync.sh

echo -e "${GREEN}==> Setup complete!${RESET}"
