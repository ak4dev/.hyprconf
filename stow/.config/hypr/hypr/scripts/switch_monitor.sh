#!/usr/bin/env bash

set -e

CONFIG_DIR="$HOME/.config/hypr"
TARGET="$CONFIG_DIR/pcMonitors.conf"

if [ -z "$1" ]; then
    echo "Usage: $0 <config-extension>"
    echo "Example: $0 bedroom"
    exit 1
fi

SOURCE="$CONFIG_DIR/pcMonitors.$1"

if [ ! -f "$SOURCE" ]; then
    echo "Error: Config '$SOURCE' does not exist."
    exit 1
fi

cp "$SOURCE" "$TARGET"

# Reload Hyprland config
hyprctl reload

echo "Switched monitor config to: $1"
