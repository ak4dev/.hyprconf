#!/usr/bin/env bash
# Installs the hyprconf overlay on top of a fresh Omarchy install.
#
#   git clone <hyprconf-repo-url> ~/.hyprconf && cd ~/.hyprconf
#   bash install.sh
#
# Every stage is idempotent, so re-running is the supported way to pick up
# changes after a `git pull`. `hyprsync` is the alias for `--sync`.
#
# Design rule throughout: impact Omarchy as little as possible. Nothing here
# changes the login shell, and everything Omarchy owns is either left alone or
# extended through a documented seam (a user theme, a plugin, a hook, a kitty
# `include`). The privileged steps are installing packages (through Omarchy's
# own `omarchy-pkg-add`) and the system Firefox policy — the overlay's one
# write outside $HOME, kept from the retired standalone setup — and --no-packages skips both,
# so the post-update hook never needs sudo.
set -euo pipefail

# The installer lives at the repository root, so the two are the same
# directory; both names are kept because they read differently ($HERE for
# shipped data files beside this script, $REPO_ROOT for git and the hook).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$HERE"

# Paths are env-overridable so the hermetic test suite can point them at a fake
# tree. Never readonly — see the testing rules in AGENTS.md.
: "${_HYPRCONF_OMARCHY_PATH:=${OMARCHY_PATH:-/usr/share/omarchy}}"
: "${_HYPRCONF_CONFIG:=$HOME/.config}"
: "${_HYPRCONF_STATE:=$HOME/.local/state}"
: "${_HYPRCONF_LOCAL_BIN:=$HOME/.local/bin}"
: "${_HYPRCONF_LOCAL_LIB:=$HOME/.local/lib}"
: "${_HYPRCONF_APPS:=$HOME/.local/share/applications}"
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
# Where the system Firefox policy lands. Root-owned, so the one stage that
# writes it goes through sudo; overridable so the hermetic suite can point it
# at a tmp tree. _HYPRCONF_ASSUME_TTY lets that suite reach the sudo path from
# a non-tty pytest run.
: "${_HYPRCONF_FIREFOX_POLICIES:=/etc/firefox/policies}"
: "${_HYPRCONF_ASSUME_TTY:=}"
# How long activate_plugin_copy waits for the shell to discover a freshly
# copied plugin (attempts x 0.05s). The hermetic suite sets it to 0 — its
# omarchy-plugin-list is a stub that never answers.
: "${_HYPRCONF_PLUGIN_WAIT:=40}"

do_pull=0
do_update=0
do_packages=1
# Set by the bar-widget stages when a copy was (re)enabled this run; main()
# does one deferred shell reload instead of one per stage.
shell_reload_needed=0

log()  { printf '==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die()  { printf 'hyprconf: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: bash install.sh [OPTIONS]

Installs (or re-applies) the hyprconf overlay on an Omarchy system.

Options:
  --sync          Pull the hyprconf checkout, re-apply, then run omarchy-update.
                  This is what the `hyprsync` alias runs.
  --no-update     Apply only; never invoke omarchy-update. Used by the
                  post-update hook, which already runs inside an update.
  --no-packages   Skip the stages that need sudo: packages and the Firefox policy.
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
# the base system; run against a hand-built Hyprland desktop it would fight
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
# accumulate whitespace ahead of it. The markers default to the '#'-comment
# pair; a caller editing a Lua file passes that syntax's own ($3/$4).
write_managed_block() {
    local file="$1" block="$2"
    local begin="${3:-# >>> hyprconf >>>}" end="${4:-# <<< hyprconf <<<}"
    local tmp kept
    touch "$file"
    tmp="$(mktemp)"
    awk -v b="$begin" -v e="$end" '
        $0 == b { skip = 1; next }
        $0 == e { skip = 0; next }
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

# Remove a managed block from $1 (markers $2/$3), preserving everything else.
# The inverse of write_managed_block, for a block the overlay no longer ships.
strip_managed_block() {
    local file="$1" begin="$2" end="$3" tmp
    [[ -f $file ]] || return 0
    # -e: the Lua marker starts with "--", which grep would read as an option.
    grep -qxF -e "$begin" "$file" || return 0
    tmp="$(mktemp)"
    awk -v b="$begin" -v e="$end" '
        $0 == b { skip = 1; next }
        $0 == e { skip = 0; next }
        skip { next }
        { print }
    ' "$file" > "$tmp"
    # Drop the blank line the writer put in front of the block.
    printf '%s\n' "$(cat "$tmp")" > "$file"
    rm -f "$tmp"
}

# Undo an `omarchy refresh` that landed on the checkout.
#
# omarchy-refresh-config — and omarchy-refresh-hyprland, which calls it for
# every hypr/*.lua — does `cp -f "$OMARCHY_PATH/config/$file"
# "$HOME/.config/$file"`. cp -f follows a symlink, and the override files below
# ARE symlinks out of this checkout, so the "refresh" lands here: hypr/$name in
# the repo becomes Omarchy's commented stock template byte for byte, every
# hotkey hyprconf adds is gone, and nothing says so but `git status`. Observed
# on Omarchy 4.0.0-1 (bindings.lua, input.lua and looknfeel.lua all replaced in
# one `omarchy refresh hyprland`). The symlinks stay — the Omarchy manual's own
# dotfiles chapter recommends stow-style links — and this is the repair: a
# stock template is trivially re-derivable and never something a user meant to
# keep in hyprconf's own tree, so when the checkout's copy is byte-identical to
# the template it is put back from git. Anything else — a real edit — is left
# alone. Omarchy keeps its own backup of what it replaced ($file.bak.<epoch>).
restore_clobbered_override() {
    local name="$1"
    local ours="$HERE/hypr/$name"
    local stock="$_HYPRCONF_OMARCHY_PATH/config/hypr/$name"
    [[ -f $ours && -f $stock ]] || return 0
    cmp -s "$ours" "$stock" || return 0
    if git -C "$REPO_ROOT" checkout -q -- "hypr/$name" 2>/dev/null && ! cmp -s "$ours" "$stock"; then
        warn "hypr/$name in the checkout had been replaced by Omarchy's stock template" \
             "(omarchy refresh writes through the symlink) — restored it from git"
    else
        warn "hypr/$name in the checkout is Omarchy's stock template and could not be" \
             "restored from git — see: git -C $REPO_ROOT status"
    fi
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
    restore_clobbered_override "$name"
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

# The system Firefox policy, kept from hyprconf's retired standalone setup: telemetry
# off, tracking protection on, uBlock Origin force-installed. Firefox reads
# enterprise policies only from root-owned paths (/etc/firefox/policies, or
# the install dir's distribution/), so this cannot live in $HOME — it is the
# overlay's one write outside it, and the reason the stage sits behind the
# same --no-packages gate as the only other privileged work. It also bows out
# when no terminal can take sudo's password prompt: the post-update hook runs
# non-interactively inside omarchy-update, where a hung prompt would stall
# the whole update.
stage_firefox() {
    log "Firefox policies (privacy defaults + uBlock Origin)"
    local src="$REPO_ROOT/infra/firefox/policies.json"
    local dst="$_HYPRCONF_FIREFOX_POLICIES/policies.json"
    if [[ ! -f $src ]]; then
        warn "policies source not found ($src) — skipping"
        return 0
    fi
    if [[ -f $dst ]] && cmp -s "$src" "$dst"; then
        info "already installed at $dst"
        return 0
    fi
    if [[ ! -t 0 && -z $_HYPRCONF_ASSUME_TTY ]]; then
        warn "no terminal for sudo — run \`bash install.sh\` from a terminal to install the Firefox policy"
        return 0
    fi
    if sudo install -Dm644 "$src" "$dst"; then
        info "installed at $dst"
    else
        warn "could not install the Firefox policy — skipping"
    fi
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
# that for good, drop the file from wallpapers/.
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
    # <file in wallpapers/>:<omarchy theme it belongs to>
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
    # being the two hyprconf's retired standalone setup picked between by chassis
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
    #
    # A preset that reads exactly like Omarchy's stock monitors.lua template is
    # not a preset any more: `omarchy refresh config hypr/monitors.lua` (or
    # `omarchy refresh hyprland`) ran while monitors.lua was the symlink
    # switch_monitor.sh leaves pointing at the chosen preset, and cp -f wrote
    # the template through the link onto the preset itself. Not repaired here —
    # the preset is machine-local and re-seeding it could enable outputs that
    # are not plugged in right now — but said out loud, with where the real
    # content went: omarchy-refresh-config backs the file up first as
    # monitors.lua.bak.<epoch>, next to it.
    local stock_monitors="$_HYPRCONF_OMARCHY_PATH/config/hypr/monitors.lua"
    local f
    for f in pcMonitors.bedroom.lua pcMonitors.kitchen.lua pcMonitors.K.lua \
             pcMonitors.lua laptopMonitors.lua; do
        if [[ -e $_HYPRCONF_CONFIG/hypr/$f ]]; then
            if [[ -f $stock_monitors ]] && cmp -s "$_HYPRCONF_CONFIG/hypr/$f" "$stock_monitors"; then
                warn "$f is Omarchy's stock monitors.lua template — an \`omarchy refresh\` wrote" \
                     "through the monitors.lua symlink; your preset is in" \
                     "$_HYPRCONF_CONFIG/hypr/monitors.lua.bak.<epoch> (copy it back, or delete" \
                     "$f and re-run to re-seed the repo's version)"
            fi
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
    log "PATH tools (bin/hyprconf-*)"
    mkdir -p "$_HYPRCONF_LOCAL_BIN"
    local f
    # hyprconf-brightness is gone with the brightness rebinds: Omarchy's
    # omarchy-brightness-display does the same job and raises its OSD. Sweep up
    # the copy earlier overlay versions installed.
    rm -f "$_HYPRCONF_LOCAL_BIN/hyprconf-brightness"
    # Every hyprconf-* tool the repo ships: the two bar-widget feeders and
    # hyprconf-yubikey (LUKS FIDO2 unlock). A new tool is one file in bin/.
    for f in "$HERE"/bin/hyprconf-*; do
        install -m 755 "$f" "$_HYPRCONF_LOCAL_BIN/${f##*/}"
    done
    case ":$PATH:" in
        *":$_HYPRCONF_LOCAL_BIN:"*) ;;
        *) warn "$_HYPRCONF_LOCAL_BIN is not on PATH — hotkeys calling these tools will fail" ;;
    esac
}

# The hyprconf TUI is gone (the overlay is a deployment mechanism, not a
# configuration app: hypr/*.lua are edited by hand, per Omarchy's own model).
# Earlier overlay versions installed it; sweep every piece up so an upgraded
# machine ends up with the same tree as a fresh one: the launcher, the two
# symlinks into the checkout, the app-menu entry, and the managed block the
# TUI's conf.d loader lived in at the tail of ~/.config/hypr/hyprland.lua.
# conf.d/*.lua files the TUI wrote are left in place — they are the user's
# settings — with a note, since nothing loads them any more.
stage_sweep_tui() {
    log "Sweeping up the retired hyprconf TUI"
    rm -f "$_HYPRCONF_LOCAL_BIN/hyprconf" "$_HYPRCONF_APPS/hyprconf.desktop"
    local link
    for link in "$_HYPRCONF_LOCAL_LIB/hyprconf" "$_HYPRCONF_CONFIG/hypr/scripts/hyprconf-tui"; do
        [[ -L $link ]] && rm -f "$link"
    done
    strip_managed_block "$_HYPRCONF_CONFIG/hypr/hyprland.lua" \
        "-- >>> hyprconf >>>" "-- <<< hyprconf <<<"
    if [[ -d $_HYPRCONF_CONFIG/hypr/conf.d ]] && [[ -n "$(ls -A "$_HYPRCONF_CONFIG/hypr/conf.d" 2>/dev/null)" ]]; then
        warn "$_HYPRCONF_CONFIG/hypr/conf.d/ still holds files the retired TUI wrote — nothing loads them now; fold what you want to keep into hypr/*.lua"
    fi
}

stage_bar_plugin() {
    log "Resource-usage bar widget (hyprconf.resources)"
    if sync_plugin_dir hyprconf-resources hyprconf.resources; then
        shell_reload_needed=1
        info "widget files synced from plugins/hyprconf-resources"
    fi
    enable_plugin_once hyprconf.resources resources-applied --section right
}

# Copy a built-in shell plugin to the project's own id — what
# omarchy-plugin-clone does, minus its hardcoded <username>.<id> naming (a
# username must never leak into shipped configuration; the project namespace
# is hyprconf.*, beside hyprconf.resources). The source is resolved from
# omarchy-plugin-catalog at runtime (never a hard-coded /usr/share path,
# which would rot), and the manifest is rewritten the way clone's
# update_manifest does: our id and displayName, clonedFrom pointing at the
# built-in — which is what makes the shell route the built-in's IPC here and
# swap the stock widget out on enable (shell/services/PluginRegistry.qml
# resolves entries through clonedFrom). No-op when the copy already exists;
# non-zero when the source cannot be resolved.
copy_builtin_plugin() {
    local source_id="$1" target_id="$2" display="$3"
    local dir="$_HYPRCONF_CONFIG/omarchy/plugins/$target_id"
    [[ -d $dir ]] && return 0

    # `|| true` inside the substitution: under pipefail a failing jq (or an
    # absent catalog command) would otherwise abort the whole install via
    # set -e, when the correct answer is the caller's retry path.
    local row src manifest
    row="$(omarchy-plugin-catalog 2>/dev/null |
        jq -r --arg id "$source_id" \
            '.[] | select(.firstParty and .id == $id) | [.sourceDir, .manifestPath] | @tsv' \
            2>/dev/null | head -n1 || true)"
    IFS=$'\t' read -r src manifest <<<"$row"
    [[ -n ${src:-} && -d $src && -n ${manifest:-} && -f $manifest ]] || return 1

    # Plugin-directory layout only (panels/clock/: manifest.json beside its
    # QML) — the clock is the one built-in still copied at install time.
    # Widgets living in the shared bar/widgets/ dir keep a sibling
    # <Name>.manifest.json instead; the one of those the overlay replaces
    # (workspaces) ships as its own plugin under plugins/ rather than as a
    # patched copy.
    [[ ${manifest##*/} == manifest.json ]] || return 1
    mkdir -p "$_HYPRCONF_CONFIG/omarchy/plugins"
    rm -rf "$dir.tmp"
    cp -aL "$src/." "$dir.tmp"
    jq --arg id "$target_id" --arg name "$display" --arg sourceId "$source_id" '
        .id = $id
        | .name = $name
        | (if (.barWidget | type) == "object" then .barWidget.displayName = $name else . end)
        | .omarchy = ((if (.omarchy | type) == "object" then .omarchy else {} end) + { clonedFrom: $sourceId })
        | del(.omarchy.clonePaths)
    ' "$dir.tmp/manifest.json" > "$dir.tmp/manifest.json.new" &&
        mv "$dir.tmp/manifest.json.new" "$dir.tmp/manifest.json" || {
            rm -rf "$dir.tmp"
            return 1
        }
    mv "$dir.tmp" "$dir"
}

# Make the shell pick a plugin copy up and put it on the bar. The rescan is
# asynchronous — omarchy-plugin-clone waits for discovery before enabling
# (up to 40 x 0.05s), and an enable issued before discovery fails with
# "unknown plugin". Same wait here; advisory only — on timeout the enable is
# still attempted, and its failure status is the caller's retry signal.
activate_plugin_copy() {
    local id="$1" _attempt
    shift
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
    for (( _attempt = 0; _attempt < _HYPRCONF_PLUGIN_WAIT; _attempt++ )); do
        if omarchy-plugin-list --json 2>/dev/null |
            jq -e --arg id "$id" 'any(.[]; .id == $id)' >/dev/null 2>&1; then
            break
        fi
        sleep 0.05
    done
    # A clonedFrom copy takes the stock widget's own slot; anything else
    # needs telling where to land — the rest of the arguments are
    # omarchy-plugin-enable's own placement flags (--section/--after/…).
    omarchy-plugin-enable "$id" "$@" >/dev/null 2>&1
}

# Install (or refresh) one of the overlay's own bar-widget plugins, shipped
# in plugins/<src>, as ~/.config/omarchy/plugins/<id>. SYNCED on every run —
# a `git pull` updates the widget the way it updates everything else the
# overlay links out of the checkout. Returns 0 when the files changed (main()
# then reloads the shell once), 1 when the installed copy was already current.
sync_plugin_dir() {
    local src="$HERE/plugins/$1" id="$2"
    local dir="$_HYPRCONF_CONFIG/omarchy/plugins/$id"
    if [[ -d $dir ]] && diff -rq "$src" "$dir" >/dev/null 2>&1; then
        return 1
    fi
    mkdir -p "$_HYPRCONF_CONFIG/omarchy/plugins"
    rm -rf "$dir"
    cp -r "$src" "$dir"
}

# Enable a plugin ONCE. Whether a widget is on the bar is the user's call from
# then on — `omarchy plugin disable <id>` is a choice, and the post-update
# hook re-runs this installer after every Omarchy update, so an unconditional
# enable would put the widget back every time. Same marker pattern as the
# font and the default apps. Needs the live shell; a TTY or SSH run leaves
# the marker unwritten so the next in-session run tries again.
enable_plugin_once() {
    local id="$1" marker="$_HYPRCONF_STATE/hyprconf/$2"
    shift 2
    if [[ -e $marker ]]; then
        info "enabled once already — \`omarchy plugin disable $id\` sticks"
        return 0
    fi
    if activate_plugin_copy "$id" "$@"; then
        mkdir -p "$(dirname "$marker")"
        : > "$marker"
        info "enabled (back to stock with: omarchy plugin disable $id)"
    else
        warn "could not enable $id (is the Omarchy shell running?) — will retry on the next run"
    fi
}

# Retire the <user>.<id> copies earlier overlay versions made with
# omarchy-plugin-clone (which hardcodes that name) once the hyprconf.* copy
# exists: the shell swaps a clonedFrom copy into the stock widget's slot, but
# a second copy of the same built-in stays on the bar beside it — observed
# as two clocks after an upgrade. Omarchy's own plugin commands do the
# work (omarchy-plugin-list --json reports clonedFrom; -disable pulls it
# off the bar; -remove deletes the copy). Runs on every pass, before the
# set-once markers, so an upgrade heals itself.
retire_stale_clones() {
    local stock="$1" keep="$2" id
    command -v jq >/dev/null 2>&1 || return 0
    while IFS= read -r id; do
        [[ -n $id ]] || continue
        omarchy-plugin-disable "$id" >/dev/null 2>&1 || true
        omarchy-plugin-remove "$id" --yes >/dev/null 2>&1 || true
        info "retired $id (an older copy of $stock; $keep replaces it)"
        shell_reload_needed=1
    done < <(omarchy-plugin-list --json 2>/dev/null |
        jq -r --arg stock "$stock" --arg keep "$keep" \
            '.[] | select((.clonedFrom // "") == $stock and .id != $keep and .id != $stock) | .id' 2>/dev/null ||
        true)
}

# The bar clock, set ONCE to hyprconf's own format: 12-hour with seconds and
# AM/PM ("hh:mm:ss AP" — Qt.formatDateTime tokens, which is what the widget
# feeds its format setting to). The stock widget cannot tick seconds:
# omarchy.clock samples SystemClock at Minutes precision (shell/plugins/
# panels/clock/BarWidget.qml), so a seconds format would sit frozen 59s of
# every minute — the widget is copied to hyprconf.clock and the copy
# patched, BEFORE it is enabled, so the shell never loads the stale Minutes
# build. Set-once marker for the same reason as the font and the default
# apps: the post-update hook re-runs this installer, and a clock the user
# later reformatted (right-click cycles formats; `omarchy bar set`) must
# stay theirs.
stage_clock() {
    log "Bar clock: hh:mm:ss AP (hyprconf.clock)"
    retire_stale_clones omarchy.clock hyprconf.clock
    local marker="$_HYPRCONF_STATE/hyprconf/clock-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the clock is yours now"
        return 0
    fi
    # jq drives the catalog lookup and the manifest rewrite. Omarchy ships
    # it; if it is somehow absent, retry rather than half-apply.
    command -v jq >/dev/null 2>&1 || {
        warn "jq not available — will retry on the next run"
        return 0
    }

    local id="hyprconf.clock"
    local dir="$_HYPRCONF_CONFIG/omarchy/plugins/$id"
    copy_builtin_plugin omarchy.clock "$id" "hyprconf Clock" || {
        warn "could not locate the omarchy.clock plugin source — will retry on the next run"
        return 0
    }
    if [[ -f $dir/BarWidget.qml ]]; then
        sed -i 's/SystemClock\.Minutes/SystemClock.Seconds/' "$dir/BarWidget.qml"
    else
        warn "no BarWidget.qml in $dir — leaving the copy unpatched"
    fi

    # Needs the live shell; on a TTY or over SSH there is nothing to answer,
    # so the marker stays unwritten and the next in-session run retries.
    activate_plugin_copy "$id" || {
        warn "could not enable $id (is the Omarchy shell running?) — will retry on the next run"
        return 0
    }
    omarchy-bar set "$id" format "hh:mm:ss AP" ||
        warn "could not set the clock format (set it with: omarchy bar set $id format 'hh:mm:ss AP')"

    # The bar centers on an anchor id, and canonicalWidgetId does no clone
    # resolution (shell/Commons/Util.qml — a plain string cast), so an anchor
    # left at omarchy.clock matches nothing once the bar swaps to our copy
    # and the clock drifts off-center. Follow the swap — but only while the
    # anchor still points at the stock id, so a user's own anchor choice is
    # never overridden.
    local shell_json="$_HYPRCONF_CONFIG/omarchy/shell.json"
    if [[ -f $shell_json ]] &&
        [[ "$(jq -r '.bar.centerAnchor // ""' "$shell_json")" == omarchy.clock ]]; then
        jq --arg id "$id" '.bar.centerAnchor = $id' "$shell_json" > "$shell_json.tmp" &&
            mv "$shell_json.tmp" "$shell_json"
        info "bar centerAnchor follows $id"
    fi

    shell_reload_needed=1
    mkdir -p "$(dirname "$marker")"
    : > "$marker"
    info "seconds tick via the $id widget (back to stock with: omarchy plugin disable $id)"
}

# Only ACTIVE workspaces on the bar, on two lines, Pac-Man on the focused one
# — the way hyprconf's own bar always behaved. The stock widget hardcodes
# pills 1-5 whether they exist or not, caps ids at 10 (bar/widgets/
# Workspaces.qml, workspaceIds(): "var ids = [1, 2, 3, 4, 5]"), and honors NO
# settings — `omarchy bar set omarchy.workspaces …` writes keys the widget
# never reads — so the overlay ships its own widget (plugins/hyprconf-
# workspaces, header comment there) as a clonedFrom copy: the shell swaps it
# into the stock widget's slot and routes the stock IPC to it, and `omarchy
# plugin disable hyprconf.workspaces` restores the stock widget.
stage_workspaces() {
    log "Bar workspaces: only active workspaces, two lines (hyprconf.workspaces)"
    retire_stale_clones omarchy.workspaces hyprconf.workspaces
    if sync_plugin_dir hyprconf-workspaces hyprconf.workspaces; then
        shell_reload_needed=1
        info "widget files synced from plugins/hyprconf-workspaces"
    fi
    enable_plugin_once hyprconf.workspaces workspaces-applied
}

# The focused window's title beside the workspaces, as hyprconf's own bar
# always drew it. Nothing to ship: Omarchy's stock omarchy.active-window
# widget (shell/plugins/bar/widgets/ActiveWindow.qml) is the same thing —
# elided title, tooltip with the full one, click focuses, middle-click
# closes — merely off by default. Enabled ONCE, right after the workspaces
# widget (the copy's id first; the stock id if the user went back to it;
# the head of the left section as the last resort — a placement target
# the bar does not carry makes omarchy-plugin-enable fail). Its width is
# the widget's own maxWidth setting: `omarchy bar set omarchy.active-window
# maxWidth 400`.
stage_window_title() {
    log "Bar window title (omarchy.active-window)"
    local marker="$_HYPRCONF_STATE/hyprconf/window-title-applied"
    if [[ -e $marker ]]; then
        info "enabled once already — \`omarchy plugin disable omarchy.active-window\` sticks"
        return 0
    fi
    local anchor
    for anchor in hyprconf.workspaces omarchy.workspaces; do
        if activate_plugin_copy omarchy.active-window --section left --after "$anchor"; then
            mkdir -p "$(dirname "$marker")"
            : > "$marker"
            info "enabled after $anchor (back to stock with: omarchy plugin disable omarchy.active-window)"
            return 0
        fi
    done
    if activate_plugin_copy omarchy.active-window --section left; then
        mkdir -p "$(dirname "$marker")"
        : > "$marker"
        info "enabled in the left section (back to stock with: omarchy plugin disable omarchy.active-window)"
    else
        warn "could not enable omarchy.active-window (is the Omarchy shell running?) — will retry on the next run"
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

# Every hook the overlay ships, hooks/<name>.d/<file>, into the matching
# ~/.config/omarchy/hooks/<name>.d/ — the directories omarchy-hook runs
# (post-update from omarchy-update, theme-set from omarchy-theme-set).
stage_hooks() {
    log "Omarchy hooks (post-update, theme-set)"
    local src dir
    for src in "$HERE"/hooks/*.d/*; do
        dir="$_HYPRCONF_CONFIG/omarchy/hooks/$(basename "$(dirname "$src")")"
        mkdir -p "$dir"
        sed "s|@HYPRCONF_DIR@|$REPO_ROOT|g" "$src" > "$dir/$(basename "$src")"
        chmod 755 "$dir/$(basename "$src")"
    done
}

# Extend the ACTIVE theme to Firefox and Code - OSS now, not only on the
# next `omarchy theme set`: the theme-set hook just installed is run once,
# the way omarchy-theme-set runs it (`omarchy-hook theme-set <name>` after
# its own fan-out). Not set-once — the hook is idempotent and cheap, and a
# re-run keeps both apps in step with a theme switched while the overlay
# was not installed.
stage_theme_apps() {
    log "Theme into Firefox and VS Code (theme-set hook)"
    local hook="$_HYPRCONF_CONFIG/omarchy/hooks/theme-set.d/10-hyprconf"
    local name="$_HYPRCONF_STATE/omarchy/current/theme.name"
    if [[ ! -r $name ]]; then
        info "no active theme yet — applies on the next omarchy theme set"
        return 0
    fi
    bash "$hook" "$(cat "$name")" || warn "theme-set hook failed — see the messages above"
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
    # The Firefox policy sits behind the same gate — the only other sudo.
    if (( do_packages )); then stage_firefox; fi
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
    stage_sweep_tui
    stage_bar_plugin
    stage_clock
    stage_workspaces
    stage_window_title
    # One deferred reload for however many bar-widget copies changed this
    # run. The copies are patched BEFORE they are enabled, so a fresh enable
    # needs no reload — this covers the swap of an already-rendered stock
    # widget picking up its replacement cleanly. Guarded: headless runs have
    # no shell to restart, and a cosmetic reload must not take the install
    # down.
    if (( shell_reload_needed )); then
        omarchy-restart-shell >/dev/null 2>&1 || true
    fi
    stage_shell
    stage_hooks
    stage_theme_apps
    hyprctl reload >/dev/null 2>&1 || true
    if (( do_update )); then stage_update; fi

    log "Done. SUPER+D still opens Omarchy's menu; the login shell is still bash."
}

main "$@"
