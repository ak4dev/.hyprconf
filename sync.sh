#!/bin/bash

# Check if the device is a GeForce RTX 4090
GPU_INFO=$(lspci | grep -i "4090")

# Copy the appropriate monitor config to ~/.config/hypr/monitors.conf
if [[ -n "$GPU_INFO" ]]; then
  cp ~/.hyprconf/hypr/pcMonitors.conf ~/.config/hypr/monitors.conf
else
  cp ~/.hyprconf/hypr/bladeMonitors.conf ~/.config/hypr/monitors.conf
fi

# Now sync the rest of the config files
cp -rf ~/.hyprconf/wallpaper/* ~/.wallpaper
cp -rf ~/.hyprconf/kitty/* ~/.config/kitty
cp -rf ~/.hyprconf/waybar/* ~/.config/waybar
cp -rf ~/.hyprconf/wofi/* ~/.config/wofi
cp -rf ~/.hyprconf/dunst/* ~/.config/dunst
cp -rf ~/.hyprconf/hypr/* ~/.config/hypr

echo "Configs synced to ~/.config/"
hyprctl reload
