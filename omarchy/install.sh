#!/usr/bin/env bash
# Installs the hyprconf overlay on top of a fresh Omarchy install.
#
#   git clone <hyprconf-repo-url> ~/.hyprconf && cd ~/.hyprconf
#   git checkout omarchy
#   bash omarchy/install.sh
#
# Every stage is idempotent, so re-running is the supported way to pick up
# changes after a `git pull`. `hyprsync` is the alias for `--sync`.
#
# Design rule throughout: impact Omarchy as little as possible. Nothing here
# writes to /etc, nothing changes the login shell, and everything Omarchy owns
# is either left alone or extended through a documented seam (a user theme, a
# plugin, a hook, a kitty `include`). The only privileged step is installing
# packages, and that goes through Omarchy's own `omarchy-pkg-add`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

# Paths are env-overridable so the hermetic test suite can point them at a fake
# tree. Never readonly — see the testing rules in AGENTS.md.
: "${_HYPRCONF_OMARCHY_PATH:=${OMARCHY_PATH:-/usr/share/omarchy}}"
: "${_HYPRCONF_CONFIG:=$HOME/.config}"
: "${_HYPRCONF_STATE:=$HOME/.local/state}"
: "${_HYPRCONF_LOCAL_BIN:=$HOME/.local/bin}"
: "${_HYPRCONF_ZSHRC:=$HOME/.zshrc}"
: "${_HYPRCONF_P10K:=$HOME/.p10k.zsh}"
: "${_HYPRCONF_OMZ:=$HOME/.oh-my-zsh}"
# Omarchy's package front-end. A name, not a path, and overridable for the same
# reason as the zsh lookup below: on a real Omarchy box /usr/bin/omarchy-pkg-add
# is always on PATH, so a test asserting the "this is not Omarchy" refusal has
# no other way to make it absent.
: "${_HYPRCONF_PKG_ADD:=omarchy-pkg-add}"
# The zsh binary looked up on PATH. Overridable so a test can point the lookup
# at a name that does not exist until the package stage creates it.
: "${_HYPRCONF_ZSH_BIN:=zsh}"

do_pull=0
do_update=0
do_packages=1

log()  { printf '==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die()  { printf 'hyprconf: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: bash omarchy/install.sh [OPTIONS]

Installs (or re-applies) the hyprconf overlay on an Omarchy system.

Options:
  --sync          Pull the hyprconf checkout, re-apply, then run omarchy-update.
                  This is what the `hyprsync` alias runs.
  --no-update     Apply only; never invoke omarchy-update. Used by the
                  post-update hook, which already runs inside an update.
  --no-packages   Skip the package stage — the only stage needing sudo.
  -h, --help      Show this help.

With no options: apply every stage once, without pulling or updating.
USAGE
}

while (( $# )); do
    case "$1" in
        --sync)        do_pull=1; do_update=1 ;;
        --no-update)   do_update=0 ;;
        --no-packages) do_packages=0 ;;
        -h|--help)     usage; exit 0 ;;
        *)             die "unknown option: $1 (try --help)" ;;
    esac
    shift
done

# ---------------------------------------------------------------- preflight

# Refuse to run anywhere that isn't Omarchy. This overlay assumes Omarchy owns
# the base system; run against the standalone hyprconf desktop it would fight
# that machine's own configuration.
preflight() {
    [[ -d $_HYPRCONF_OMARCHY_PATH ]] ||
        die "no Omarchy found at $_HYPRCONF_OMARCHY_PATH — this overlay installs on top of Omarchy."
    command -v "$_HYPRCONF_PKG_ADD" >/dev/null 2>&1 ||
        die "$_HYPRCONF_PKG_ADD not on PATH — this overlay installs on top of Omarchy."
}

# ------------------------------------------------------------------ helpers

# Replace the hyprconf-managed block in $1 with the contents of $2, preserving
# everything outside the markers. Byte-stable across repeated runs: trailing
# blank lines are stripped before the block is appended, so a re-run cannot
# accumulate whitespace ahead of it.
write_managed_block() {
    local file="$1" block="$2" tmp kept
    touch "$file"
    tmp="$(mktemp)"
    awk '
        /^# >>> hyprconf >>>$/ { skip = 1; next }
        /^# <<< hyprconf <<<$/ { skip = 0; next }
        skip { next }
        { print }
    ' "$file" > "$tmp"
    kept="$(cat "$tmp")"   # command substitution strips trailing newlines
    rm -f "$tmp"
    {
        if [[ -n $kept ]]; then printf '%s\n\n' "$kept"; fi
        cat "$block"
    } > "$file"
}

# Point one of Omarchy's ~/.config/hypr override files at the overlay's own
# copy, keeping a one-time .stock backup of whatever real file was there first.
#
# This is Omarchy's documented seam, not a fork: hyprland.lua `require`s each of
# these files AFTER loading the defaults, so the overlay's version only has to
# state where hyprconf differs. Deleting the symlink (or moving the .stock file
# back) returns the machine to stock.
link_hypr_override() {
    local name="$1"
    local target="$_HYPRCONF_CONFIG/hypr/$name"
    if [[ -e $target && ! -L $target ]]; then
        cp "$target" "$target.stock"
        info "backed up stock $name -> $name.stock"
    fi
    ln -sfn "$HERE/hypr/$name" "$target"
}

# Resolve zsh into $_HYPRCONF_ZSH, or the empty string when it is not
# installed. Deliberately NOT resolved at startup: on a fresh Omarchy zsh does
# not exist until stage_packages installs it moments later, and a startup lookup
# would pin the empty string for the whole run — kitty would never get its
# `shell` line and stage_shell would skip itself on the very run that installed
# zsh, leaving bash in the terminal until some later re-run. main() calls this
# right after the package stage instead.
#
# Uses ${x+set} rather than := so a test can pin the value, the empty string
# included, to simulate a box with no zsh.
resolve_zsh() {
    if [[ -z ${_HYPRCONF_ZSH+set} ]]; then
        _HYPRCONF_ZSH="$(command -v "$_HYPRCONF_ZSH_BIN" 2>/dev/null || true)"
    fi
}

# ------------------------------------------------------------------- stages

stage_pull() {
    log "Updating the hyprconf checkout"
    if ! git -C "$REPO_ROOT" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
        info "no upstream configured — skipping pull"
        return 0
    fi
    # --ff-only, never a hard reset: on the Omarchy machine this checkout is
    # also where the overlay gets edited. Diverged history is a stop, not
    # something to silently discard.
    #
    # NB: a pull that changes this script does not affect the run in progress —
    # bash has already read it. The data files every later stage reads (the
    # package list, the zshrc block, bindings.lua) ARE re-read fresh, so only
    # this file's own logic is a version behind. Re-run to pick that up.
    git -C "$REPO_ROOT" pull --ff-only ||
        die "git pull failed (diverged history?) — resolve it and re-run"
}

stage_packages() {
    log "Packages"
    local pkgs=() line
    while IFS= read -r line || [[ -n $line ]]; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -d '[:space:]')"
        [[ -n $line ]] && pkgs+=("$line")
    done < "$HERE/packages"
    (( ${#pkgs[@]} )) || return 0

    # omarchy-pkg-add is already idempotent (guards with omarchy-pkg-missing,
    # verifies with pacman -Q, exits non-zero on failure), so a re-run is a
    # cheap pacman -Q loop with no sudo prompt. Never bare `pacman -Syu`:
    # Omarchy installs an ALPM AbortOnFail hook that blocks sysupgrade forms.
    "$_HYPRCONF_PKG_ADD" "${pkgs[@]}" || die "package install failed"
}

stage_terminal() {
    log "Terminal: kitty"
    # Assert kitty is present BEFORE touching the default. omarchy-default-
    # terminal's own guard is `omarchy-cmd-missing kitty`, and when that fires
    # without --install it exec()s a floating GUI window — fatal in a
    # non-interactive run. Proving kitty exists makes that branch unreachable.
    # (--install avoids the window but routes through omarchy-install-terminal,
    # which prints "Failed to install" and still exits 0, so a failed install
    # would read as success under set -e.)
    command -v kitty >/dev/null 2>&1 ||
        die "kitty is not installed — re-run without --no-packages"

    local current=""
    current="$(omarchy-default-terminal 2>/dev/null || true)"
    if [[ $current == kitty ]]; then
        info "already the default terminal"
    else
        # One file backs this: ~/.config/xdg-terminals.list. The SUPER+RETURN
        # bind, $TERMINAL, the floating terminals, the TUI launchers, the menu
        # and the bar all resolve through xdg-terminal-exec, so nothing else
        # needs patching.
        omarchy-default-terminal kitty
    fi
    stage_kitty_include
}

# hyprconf's kitty preferences, layered as an include so Omarchy's kitty.conf
# stays authoritative — it owns the theme include, listen_on (Super+Return cwd
# inheritance) and the font_family/font_size lines its font tooling rewrites.
stage_kitty_include() {
    # Separate `local` statements on purpose: `local a=1 b="$a"` declares both
    # names before assigning, so $a is still unbound there — fatal under set -u.
    local dir="$_HYPRCONF_CONFIG/kitty"
    local conf="$dir/kitty.conf"
    mkdir -p "$dir"
    install -m 644 "$HERE/kitty/hyprconf.conf" "$dir/hyprconf.conf"

    # Only point kitty at zsh once zsh really exists — otherwise kitty cannot
    # start at all. The login shell is deliberately left as bash.
    if [[ -n $_HYPRCONF_ZSH ]]; then
        grep -q '^shell ' "$dir/hyprconf.conf" || {
            printf '\n# hyprconf runs zsh in the terminal. The LOGIN shell stays bash so\n'
            printf '# Omarchy'"'"'s rc chain, session and scripts are untouched.\n'
            printf 'shell %s\n' "$_HYPRCONF_ZSH"
        } >> "$dir/hyprconf.conf"
    else
        warn "zsh not installed — kitty will keep using the login shell"
    fi

    if [[ -f $conf ]]; then
        grep -qxF 'include hyprconf.conf' "$conf" ||
            printf '\n# hyprconf overlay\ninclude hyprconf.conf\n' >> "$conf"
    else
        warn "$conf not found — hyprconf.conf installed but nothing includes it"
    fi
}

stage_theme() {
    log "Theme: hyprconf (Dracula)"
    mkdir -p "$_HYPRCONF_CONFIG/omarchy/themes"
    # A SYMLINK on purpose. omarchy-theme-set decides whether a user theme came
    # from a stranger with `[[ ! -L $source && -d $source/.git ]]`; because ours
    # is a symlink it takes the permissive branch. Turning this into a copy of a
    # git checkout would put it through INSTALLED_THEME_DENIED instead.
    ln -sfn "$HERE/themes/hyprconf" "$_HYPRCONF_CONFIG/omarchy/themes/hyprconf"

    # Installed, never activated. Which theme is active is the user's choice,
    # and an install — or any of the re-applies that follow every Omarchy
    # update — must not take it away from them. (`omarchy-theme-set` is no
    # cheap no-op either: it rebuilds the staged theme, swaps symlinks and fans
    # out ~15 restart/retint commands.)
    local active="$_HYPRCONF_STATE/omarchy/current/theme.name"
    if [[ -r $active ]] && [[ "$(cat "$active")" == hyprconf ]]; then
        info "already the active theme"
    else
        info "available in Omarchy's theme menu (SUPER+SHIFT+CTRL+SPACE) — the active theme is left as it is"
    fi
}

# The system monospace font, set ONCE on first install and never again.
#
# Which font is running is a user-facing choice, and this installer re-runs
# after every Omarchy update via the post-update hook — without the marker, a
# font the user picked later would be silently reverted to ours on the next
# update, exactly the way the theme used to be taken back.
# hyprconf's extra wallpapers, filed under the Omarchy theme each belongs to.
#
# Omarchy's background switcher scans exactly two directories, and both are
# keyed to the ACTIVE theme: that theme's own backgrounds/, and
# ~/.config/omarchy/backgrounds/<theme>/ (omarchy-theme-bg-next and
# omarchy-theme-bg-switcher agree on this). A wallpaper filed anywhere else is
# invisible — which is why hyprconf's gruvbox shot, sitting in hyprconf's own
# theme directory, never appeared while any other theme was active.
#
# The hyprconf theme's own background (dracula) is NOT here: it ships inside
# the theme, where Omarchy already finds it.
#
# Copied when absent, so deleting one and re-running brings it back. To stop
# that for good, drop the file from omarchy/wallpapers/.
# hyprconf's app picks, expressed as Omarchy defaults rather than hard-coded in
# the keymap. SUPER+F/C/T/E call omarchy-launch-browser / -editor / -terminal /
# -nautilus, which resolve these — so `omarchy default browser zen` moves the
# key with it, and the choice lives where Omarchy's own menu can edit it.
#
# Set ONCE, for the same reason as the font: the post-update hook re-runs this
# installer after every Omarchy update, and re-asserting a default would
# silently undo a later choice. Failures warn rather than abort — a default app
# is not worth taking an install down over, and the browser setter needs a live
# session for xdg-settings.
stage_defaults() {
    log "Default apps"
    local marker="$_HYPRCONF_STATE/hyprconf/defaults-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the defaults are yours now"
        return 0
    fi

    omarchy-default-browser firefox ||
        warn "could not set firefox as the default browser (set it with: omarchy default browser firefox)"
    omarchy-default-editor code ||
        warn "could not set code as the default editor (set it with: omarchy default editor code)"

    mkdir -p "$(dirname "$marker")"
    : > "$marker"
    info "browser=firefox editor=code (change with: omarchy default browser|editor <name>)"
}

stage_backgrounds() {
    log "Wallpapers"
    local entry file theme dest
    # <file in omarchy/wallpapers>:<omarchy theme it belongs to>
    local -a wallpapers=(
        "gruvbox.jpg:gruvbox"
    )
    for entry in "${wallpapers[@]}"; do
        file="${entry%%:*}"
        theme="${entry##*:}"
        [[ -f $HERE/wallpapers/$file ]] || continue
        dest="$_HYPRCONF_CONFIG/omarchy/backgrounds/$theme"
        mkdir -p "$dest"
        if [[ -e $dest/$file ]]; then
            info "$file already in the $theme backgrounds"
        else
            install -m 644 "$HERE/wallpapers/$file" "$dest/$file"
            info "$file -> $theme backgrounds (SUPER+CTRL+SPACE to pick it)"
        fi
    done
}

stage_font() {
    log "Font: Geist Mono Nerd Font"
    local marker="$_HYPRCONF_STATE/hyprconf/font-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the font is yours now"
        return 0
    fi

    # Resolve the family from what is actually installed rather than hard-coding
    # the string. Nerd Font packaging has renamed families between releases, and
    # omarchy-font-set exits 1 on any name `fc-list` does not know — which under
    # set -e would take the whole install down over a cosmetic stage.
    local family
    family="$(fc-list : family 2>/dev/null | tr ',' '\n' |
        grep -m1 -ixE 'GeistMono Nerd Font' || true)"
    [[ -n $family ]] ||
        family="$(fc-list : family 2>/dev/null | tr ',' '\n' |
            grep -m1 -iE 'geist.*(nerd|mono)' || true)"
    if [[ -z $family ]]; then
        warn "GeistMono Nerd Font is not installed — leaving the system font alone"
        return 0
    fi

    omarchy-font-set "$family" || {
        warn "omarchy-font-set rejected '$family' — leaving the system font alone"
        return 0
    }
    mkdir -p "$(dirname "$marker")"
    : > "$marker"
    info "set to $family (change it any time with: omarchy font set <name>)"
}

stage_hotkeys() {
    log "Hotkeys"
    mkdir -p "$_HYPRCONF_CONFIG/hypr/scripts"
    link_hypr_override bindings.lua
    # toggle-native-display is deliberately gone: SUPER+SHIFT+BACKSPACE now
    # calls Omarchy's own `omarchy-hyprland-monitor-internal toggle`, which
    # does the same job through a path that still works on Hyprland 0.56.
    # Sweep up the copy earlier overlay versions installed, so an upgraded
    # machine ends up with the same tree as a fresh one.
    rm -f "$_HYPRCONF_CONFIG/hypr/scripts/toggle-native-display"
    local f
    for f in switch_monitor.sh adjust-gaps; do
        install -m 755 "$HERE/hypr/scripts/$f" "$_HYPRCONF_CONFIG/hypr/scripts/$f"
    done
}

stage_looknfeel() {
    log "Look'n'feel and input (natural scroll, gaps, blur, gestures)"
    mkdir -p "$_HYPRCONF_CONFIG/hypr"
    # Both files state only hyprconf's deltas from Omarchy's own defaults; the
    # reasoning for each ported and each skipped setting is in their headers.
    link_hypr_override looknfeel.lua
    link_hypr_override input.lua
}

stage_monitors() {
    log "Monitor presets (SUPER+SHIFT+B / SUPER+SHIFT+K)"
    # Presets only. Whichever monitors.lua is active — Omarchy's own auto
    # layout, or a previously chosen preset — is left alone until a hotkey is
    # actually pressed. Each preset carries hyprconf's workspace-to-monitor
    # rules for that layout, which is why they travel as whole files.
    #
    # Only bedroom and kitchen have hotkeys, in hyprconf too. The rest are
    # `~/.config/hypr/scripts/switch_monitor.sh {K,pc,laptop}` — pc and laptop
    # being the two hyprconf's own setup.sh picked between by chassis
    # detection, which has no equivalent here.
    #
    # Omarchy's own monitors.lua is saved first, and once: switch_monitor.sh
    # symlinks the chosen preset straight over that path, so without this the
    # first hotkey press would destroy Omarchy's auto layout with no way back.
    # `switch_monitor.sh stock` restores this copy.
    local active="$_HYPRCONF_CONFIG/hypr/monitors.lua"
    if [[ -f $active && ! -L $active && ! -e $active.stock ]]; then
        cp "$active" "$active.stock"
        info "saved Omarchy's monitors.lua -> monitors.lua.stock"
    fi

    # SEEDED, not synced. A preset is a description of one machine's physical
    # desk — outputs, modes, scales — so once it exists it belongs to that
    # machine, and switch_monitor.sh's own comment promises edits survive
    # re-selecting a preset. Copying over it on every run would break that
    # promise silently, and the post-update hook re-runs this after every
    # Omarchy update. Delete a preset to have it re-seeded from the repo.
    local f
    for f in pcMonitors.bedroom.lua pcMonitors.kitchen.lua pcMonitors.K.lua \
             pcMonitors.lua laptopMonitors.lua; do
        if [[ -e $_HYPRCONF_CONFIG/hypr/$f ]]; then
            continue
        fi
        install -m 644 "$HERE/hypr/$f" "$_HYPRCONF_CONFIG/hypr/$f"
        info "seeded $f"
    done
}

stage_fastfetch() {
    log "fastfetch greeting"
    # Omarchy ships fastfetch but no fastfetch config of its own — nothing to
    # displace, so hyprconf's layout is simply linked in. ~/.zshrc runs it as
    # the shell greeting, exactly as hyprconf's own .zshrc always has.
    local dir="$_HYPRCONF_CONFIG/fastfetch"
    local target="$dir/config.jsonc"
    mkdir -p "$dir"
    if [[ -e $target && ! -L $target ]]; then
        cp "$target" "$target.stock"
        info "backed up existing config.jsonc -> config.jsonc.stock"
    fi
    ln -sfn "$HERE/fastfetch/config.jsonc" "$target"
}

stage_bin() {
    log "PATH tools"
    mkdir -p "$_HYPRCONF_LOCAL_BIN"
    local f
    # hyprconf-brightness is gone with the brightness rebinds: Omarchy's
    # omarchy-brightness-display does the same job and raises its OSD. Sweep up
    # the copy earlier overlay versions installed.
    rm -f "$_HYPRCONF_LOCAL_BIN/hyprconf-brightness"
    for f in hyprconf-stats hyprconf-gpu-info; do
        install -m 755 "$HERE/bin/$f" "$_HYPRCONF_LOCAL_BIN/$f"
    done
    case ":$PATH:" in
        *":$_HYPRCONF_LOCAL_BIN:"*) ;;
        *) warn "$_HYPRCONF_LOCAL_BIN is not on PATH — hotkeys calling these tools will fail" ;;
    esac
}

stage_bar_plugin() {
    log "Resource-usage bar widget"
    local dir="$_HYPRCONF_CONFIG/omarchy/plugins"
    mkdir -p "$dir"
    rm -rf "$dir/hyprconf.resources"
    cp -r "$HERE/plugins/hyprconf-resources" "$dir/hyprconf.resources"
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
    if omarchy-plugin-list --json 2>/dev/null |
        jq -e 'any(.[]; .id == "hyprconf.resources" and .enabled)' >/dev/null 2>&1; then
        info "already enabled"
    else
        omarchy-plugin-enable hyprconf.resources --section right || true
    fi
}

stage_shell() {
    log "Shell: zsh + powerlevel10k in the terminal"
    # Deliberately NO chsh. The login shell stays bash, so Omarchy's rc chain,
    # its aliases/functions/completions, uwsm, SSH and scripts are untouched.
    # kitty is what launches zsh (see stage_kitty_include), and .zshrc sources
    # Omarchy's own env/alias files so its updates keep flowing through.
    [[ -n $_HYPRCONF_ZSH ]] || { warn "zsh not installed — skipping"; return 0; }

    if [[ ! -d $_HYPRCONF_OMZ ]]; then
        info "Installing Oh My Zsh"
        git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$_HYPRCONF_OMZ"
    fi

    local p10k="$_HYPRCONF_OMZ/custom/themes/powerlevel10k"
    mkdir -p "$(dirname "$p10k")"
    if [[ ! -d $p10k ]]; then
        info "Installing powerlevel10k"
        git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$p10k"
    else
        # Bounded, and failure is fine. This runs on every apply — including
        # from the post-update hook, non-interactively, inside `omarchy-update`
        # — so an unreachable or slow network must not stall an Omarchy update.
        # An out-of-date prompt theme is cosmetic; a hung system update is not.
        # (Observed: an unbounded pull here held a run for several minutes.)
        timeout 20 git -C "$p10k" pull --ff-only >/dev/null 2>&1 || true
    fi

    ln -sfn "$HERE/zsh/.p10k.zsh" "$_HYPRCONF_P10K"
    write_managed_block "$_HYPRCONF_ZSHRC" "$HERE/zsh/zshrc.block"
}

stage_hooks() {
    log "Omarchy post-update hook"
    local dir="$_HYPRCONF_CONFIG/omarchy/hooks/post-update.d"
    mkdir -p "$dir"
    sed "s|@HYPRCONF_DIR@|$REPO_ROOT|g" "$HERE/hooks/post-update.d/10-hyprconf" > "$dir/10-hyprconf"
    chmod 755 "$dir/10-hyprconf"
}

stage_update() {
    log "Updating Omarchy"
    # Omarchy's own updater, never pacman: an ALPM AbortOnFail hook blocks
    # sysupgrade forms outside this path. HYPRCONF_SYNC_RUNNING tells the
    # post-update hook the overlay was applied moments ago, so it skips its
    # redundant re-apply.
    HYPRCONF_SYNC_RUNNING=1 omarchy-update
}

# --------------------------------------------------------------------- main

main() {
    preflight
    if (( do_pull ));     then stage_pull; fi
    if (( do_packages )); then stage_packages; fi
    # After the package stage, never before it — see resolve_zsh.
    resolve_zsh
    stage_terminal
    stage_theme
    stage_defaults
    stage_backgrounds
    stage_font
    stage_hotkeys
    stage_looknfeel
    stage_monitors
    stage_fastfetch
    stage_bin
    stage_bar_plugin
    stage_shell
    stage_hooks
    hyprctl reload >/dev/null 2>&1 || true
    if (( do_update )); then stage_update; fi

    log "Done. SUPER+D still opens Omarchy's menu; the login shell is still bash."
}

main "$@"
