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
cp -r ~/.hyprconf/wallpaper ~/.wallpaper
cp -r ~/.hyprconf/kitty ~/.config/kitty
cp -r ~/.hyprconf/waybar ~/.config/waybar
cp -r ~/.hyprconf/wofi ~/.config/wofi
cp -r ~/.hyprconf/dunst ~/.config/dunst
cp -r ~/.hyprconf/hypr ~/.config/hypr

echo "Configs synced to ~/.config/"
