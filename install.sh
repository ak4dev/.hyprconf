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
mkdir -p ~/.local/share/zsh/plugins
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

# Install Oh My Zsh
echo -e "${GREEN}==> Installing Oh My Zsh...${RESET}"
export RUNZSH=no
sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Install Powerlevel10k theme
echo -e "${GREEN}==> Installing Powerlevel10k...${RESET}"
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/powerlevel10k

# Install Zsh plugins (system-wide or local as fallback)
echo -e "${GREEN}==> Installing zsh-autosuggestions and zsh-syntax-highlighting...${RESET}"
sudo mkdir -p /usr/share/zsh/plugins
sudo git clone https://github.com/zsh-users/zsh-autosuggestions /usr/share/zsh/plugins/zsh-autosuggestions
sudo git clone https://github.com/zsh-users/zsh-syntax-highlighting /usr/share/zsh/plugins/zsh-syntax-highlighting

# Build .zshrc
echo -e "${GREEN}==> Creating .zshrc...${RESET}"
cat << 'EOF' > ~/.zshrc
fastfetch --logo arch2 --logo-color-1 green --logo-color-2 green

export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"
plugins=(git)

source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

source $ZSH/oh-my-zsh.sh

source ~/powerlevel10k/powerlevel10k.zsh-theme
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

alias hyprsync='~/.hyprconf/sync.sh'
EOF

# Set Zsh as default
if [ "$SHELL" != "/bin/zsh" ]; then
    echo -e "${GREEN}==> Setting Zsh as the default shell...${RESET}"
    chsh -s /bin/zsh
fi


# Add alias for hyprsync
echo -e "${GREEN}==> Adding 'hyprsync' alias to .zshrc...${RESET}"
if ! grep -q "alias hyprsync=" "$ZSHRC"; then
    echo "alias hyprsync='~/.hyprconf/sync.sh'" >> "$ZSHRC"
    echo -e "${GREEN}Alias added.${RESET}"
else
    echo -e "${GREEN}Alias already exists, skipping...${RESET}"
fi

# Make sure sync.sh is executable
chmod +x ~/.hyprconf/sync.sh

# Run the sync script
echo -e "${GREEN}==> Running hyprsync...${RESET}"
source ~/.zshrc && hyprsync



echo -e "${GREEN}==> Setup complete! Please restart your terminal for changes to take effect.${RESET}"

