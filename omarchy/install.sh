#!/bin/bash
# Installs the hyprconf-on-Omarchy overlay: theme, hotkeys, and the
# resource-usage bar widget. Run from inside a checkout of this branch:
#
#   git clone <hyprconf-repo-url> ~/.hyprconf && cd ~/.hyprconf
#   git checkout omarchy
#   bash omarchy/install.sh
#
# Idempotent — safe to re-run after a `git pull` to pick up changes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Theme: hyprconf (Dracula)"
mkdir -p ~/.config/omarchy/themes
ln -sfn "$HERE/themes/hyprconf" ~/.config/omarchy/themes/hyprconf
omarchy theme set hyprconf

echo "==> Hotkeys"
mkdir -p ~/.config/hypr/scripts
if [[ -e ~/.config/hypr/bindings.lua && ! -L ~/.config/hypr/bindings.lua ]]; then
    cp ~/.config/hypr/bindings.lua ~/.config/hypr/bindings.lua.stock
    echo "    backed up stock bindings.lua -> ~/.config/hypr/bindings.lua.stock"
fi
ln -sfn "$HERE/hypr/bindings.lua" ~/.config/hypr/bindings.lua
for f in switch_monitor.sh adjust-gaps toggle-native-display; do
    install -m 755 "$HERE/hypr/scripts/$f" ~/.config/hypr/scripts/"$f"
done

echo "==> PATH tools (hyprconf-brightness, hyprconf-stats, hyprconf-gpu-info)"
mkdir -p ~/.local/bin
for f in hyprconf-brightness hyprconf-stats hyprconf-gpu-info; do
    install -m 755 "$HERE/bin/$f" ~/.local/bin/"$f"
done
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "    WARNING: ~/.local/bin is not on PATH — hotkeys that call these tools will fail" ;;
esac

echo "==> Resource-usage bar widget"
mkdir -p ~/.config/omarchy/plugins
rm -rf ~/.config/omarchy/plugins/hyprconf.resources
cp -r "$HERE/plugins/hyprconf-resources" ~/.config/omarchy/plugins/hyprconf.resources
omarchy-shell shell rescanPlugins >/dev/null
if omarchy-plugin-list --json 2>/dev/null | jq -e 'any(.[]; .id == "hyprconf.resources" and .enabled)' >/dev/null 2>&1; then
    echo "    already enabled"
else
    omarchy-plugin-enable hyprconf.resources --section right
fi

hyprctl reload >/dev/null 2>&1 || true

echo "==> Done. SUPER+D still opens Omarchy's menu; hyprconf's other hotkeys are now live."
