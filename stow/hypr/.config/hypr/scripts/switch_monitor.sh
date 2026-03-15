#!/usr/bin/env bash
set -euo pipefail

readonly CONFIG_DIR="$HOME/.config/hypr"
readonly TARGET="$CONFIG_DIR/pcMonitors.conf"

if [[ -z "${1:-}" ]]; then
    echo "Usage: $0 <config-extension>" >&2
    echo "Example: $0 bedroom" >&2
    exit 1
fi

SOURCE="$CONFIG_DIR/pcMonitors.$1"

if [[ ! -f "$SOURCE" ]]; then
    echo "Error: Config '$SOURCE' does not exist." >&2
    exit 1
fi

cp "$SOURCE" "$TARGET"
hyprctl reload
echo "Switched monitor config to: $1"
