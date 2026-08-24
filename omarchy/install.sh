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

echo "==> Monitor presets (bedroom / kitchen — SUPER+SHIFT+B / SUPER+SHIFT+K)"
# Presets only; whichever monitors.lua is already active (Omarchy's own
# auto-layout default, or a previous preset) is left alone until one of
# these hotkeys is actually pressed.
for f in pcMonitors.bedroom.lua pcMonitors.kitchen.lua; do
    install -m 644 "$HERE/hypr/$f" ~/.config/hypr/"$f"
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

echo "==> Shell: Oh My Zsh + Powerlevel10k"
# Not installed by Omarchy by default. Mirrors ~/.hyprconf's own
# install_oh_my_zsh/install_powerlevel10k/update_zshrc (setup.sh) — plain git
# clones into $HOME, no sudo — with the managed ~/.zshrc block kept under the
# same "# >>> hyprconf zsh >>>" markers so re-running this script (or, later,
# hyprconf's own setup.sh on a machine that has both) stays idempotent.
P10K_DIR="$HOME/.oh-my-zsh/custom/themes/powerlevel10k"

if command -v zsh >/dev/null 2>&1; then
    for pkg in zsh-autosuggestions zsh-syntax-highlighting; do
        pacman -Qi "$pkg" >/dev/null 2>&1 || \
            echo "    WARNING: pacman package '$pkg' not installed — run: sudo pacman -S $pkg"
    done

    if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
        echo "    Installing Oh My Zsh..."
        git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
        if [[ "${SHELL:-}" != */zsh && -t 0 ]]; then
            chsh -s "$(command -v zsh)" || echo "    WARNING: could not change login shell — run: chsh -s $(command -v zsh)"
        fi
    fi

    mkdir -p "$(dirname "$P10K_DIR")"
    if [[ ! -d "$P10K_DIR" ]]; then
        echo "    Installing Powerlevel10k..."
        git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
    else
        git -C "$P10K_DIR" pull --ff-only >/dev/null 2>&1 || true
    fi

    ln -sfn "$HERE/zsh/.p10k.zsh" ~/.p10k.zsh
    touch ~/.zshrc
    tmp="$(mktemp)"
    awk '
        BEGIN { in_block = 0; inserted = 0 }
        /^# >>> hyprconf zsh >>>$/ { in_block = 1; next }
        /^# <<< hyprconf zsh <<<$/ { in_block = 0; next }
        in_block == 1 { next }
        /powerlevel10k\.zsh-theme/ { next }
        /^[[:space:]]*export[[:space:]]+ZSH=/ { next }
        /^[[:space:]]*ZSH_THEME=/ { next }
        /\.p10k\.zsh/ { next }
        /^[[:space:]]*(source|\.)[[:space:]].*oh-my-zsh\.sh[[:space:]]*$/ {
            if (inserted == 0) { print_block(); inserted = 1 }
            next
        }
        /^[[:space:]]*alias[[:space:]]+hyprsync=/ { next }
        { print }
        function print_block() {
            print "# >>> hyprconf zsh >>>"
            print "export ZSH=\"$HOME/.oh-my-zsh\""
            print "P10K_THEME=\"$ZSH/custom/themes/powerlevel10k/powerlevel10k.zsh-theme\""
            print "if [[ -r \"$P10K_THEME\" ]]; then"
            print "  ZSH_THEME=\"powerlevel10k/powerlevel10k\""
            print "else"
            print "  ZSH_THEME=\"robbyrussell\""
            print "fi"
            print ""
            print "if [[ -r \"$ZSH/oh-my-zsh.sh\" ]]; then"
            print "  source \"$ZSH/oh-my-zsh.sh\""
            print "else"
            print "  echo \"[hyprconf] Oh My Zsh not found — re-run: bash ~/.hyprconf/omarchy/install.sh\""
            print "fi"
            print ""
            print "if [[ -r \"$P10K_THEME\" && -f \"$HOME/.p10k.zsh\" ]]; then"
            print "  source \"$HOME/.p10k.zsh\""
            print "fi"
            print "typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION=$\047\\uf303\047"
            print "# <<< hyprconf zsh <<<"
        }
        END { if (inserted == 0) { print ""; print_block() } }
    ' ~/.zshrc | cat -s > "$tmp"
    # cat -s collapses runs of blank lines to one: the managed block's own
    # source line never matches the insertion-anchor regex (it's quoted), so
    # every re-run falls through to the END-block append path and would
    # otherwise grow an extra blank line before the block on every pass.
    mv "$tmp" ~/.zshrc

    add_if_missing() {
        grep -qxF "$1" ~/.zshrc 2>/dev/null || echo "$1" >> ~/.zshrc
    }
    add_if_missing 'source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh'
    add_if_missing "alias hyprsync='bash ~/.hyprconf/omarchy/install.sh'"
else
    echo "    WARNING: zsh not installed — skipping Oh My Zsh / Powerlevel10k"
fi

hyprctl reload >/dev/null 2>&1 || true

echo "==> Done. SUPER+D still opens Omarchy's menu; hyprconf's other hotkeys are now live."
