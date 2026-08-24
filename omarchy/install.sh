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
# Resolved zsh, or empty when zsh isn't installed. Uses ${x+set} rather than
# := so a test can override it to the empty string to simulate "no zsh".
if [[ -z ${_HYPRCONF_ZSH+set} ]]; then
    _HYPRCONF_ZSH="$(command -v zsh 2>/dev/null || true)"
fi

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
    command -v omarchy-pkg-add >/dev/null 2>&1 ||
        die "omarchy-pkg-add not on PATH — this overlay installs on top of Omarchy."
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
    omarchy-pkg-add "${pkgs[@]}" || die "package install failed"
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

    # `omarchy-theme-set` is not a cheap no-op — it rebuilds the staged theme,
    # swaps symlinks and fans out ~15 restart/retint commands — so only run it
    # when ours isn't already the active theme.
    local active="$_HYPRCONF_STATE/omarchy/current/theme.name"
    if [[ -r $active ]] && [[ "$(cat "$active")" == hyprconf ]]; then
        info "already active"
    else
        omarchy-theme-set hyprconf
    fi
}

stage_hotkeys() {
    log "Hotkeys"
    mkdir -p "$_HYPRCONF_CONFIG/hypr/scripts"
    if [[ -e $_HYPRCONF_CONFIG/hypr/bindings.lua && ! -L $_HYPRCONF_CONFIG/hypr/bindings.lua ]]; then
        cp "$_HYPRCONF_CONFIG/hypr/bindings.lua" "$_HYPRCONF_CONFIG/hypr/bindings.lua.stock"
        info "backed up stock bindings.lua -> bindings.lua.stock"
    fi
    ln -sfn "$HERE/hypr/bindings.lua" "$_HYPRCONF_CONFIG/hypr/bindings.lua"
    local f
    for f in switch_monitor.sh adjust-gaps toggle-native-display; do
        install -m 755 "$HERE/hypr/scripts/$f" "$_HYPRCONF_CONFIG/hypr/scripts/$f"
    done
}

stage_monitors() {
    log "Monitor presets (SUPER+SHIFT+B / SUPER+SHIFT+K)"
    # Presets only. Whichever monitors.lua is active — Omarchy's own auto
    # layout, or a previously chosen preset — is left alone until a hotkey is
    # actually pressed.
    local f
    for f in pcMonitors.bedroom.lua pcMonitors.kitchen.lua; do
        install -m 644 "$HERE/hypr/$f" "$_HYPRCONF_CONFIG/hypr/$f"
    done
}

stage_bin() {
    log "PATH tools"
    mkdir -p "$_HYPRCONF_LOCAL_BIN"
    local f
    for f in hyprconf-brightness hyprconf-stats hyprconf-gpu-info; do
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
        git -C "$p10k" pull --ff-only >/dev/null 2>&1 || true
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
    stage_terminal
    stage_theme
    stage_hotkeys
    stage_monitors
    stage_bin
    stage_bar_plugin
    stage_shell
    stage_hooks
    hyprctl reload >/dev/null 2>&1 || true
    if (( do_update )); then stage_update; fi

    log "Done. SUPER+D still opens Omarchy's menu; the login shell is still bash."
}

main "$@"
