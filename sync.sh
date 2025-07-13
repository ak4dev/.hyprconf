#!/bin/bash

# From .hyprconf to actual config

cp -r ~/.hyprconf/kitty ~/.config/kitty
cp -r ~/.hyprconf/waybar ~/.config/waybar
cp -r ~/.hyprconf/wofi ~/.config/wofi
cp -r ~/.hyprconf/hypr ~/.config/hypr

echo "Configs synced to ~/.config/"
