#!/usr/bin/env bash
# Installs the hyprconf overlay on top of a fresh Omarchy install.
#
#   bash <(curl -fsSL hyprconf.sh)
#
# hyprconf.sh serves this very file to curl and wget. Run that way it has no
# payload beside it, so it clones github.com/ak4dev/.hyprconf (branch stable)
# into ~/.hyprconf — or uses the checkout already there — and hands over to
# that checkout's own copy (see bootstrap). The same by hand:
#
#   git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
#   bash ~/.hyprconf/install.sh
#
# Every stage is idempotent, so re-running is the supported way to pick up
# changes after a `git pull`. `hyprsync` is the alias for `--sync`.
#
# Design rule throughout: impact Omarchy as little as possible. Nothing here
# changes the login shell, and everything Omarchy owns is either left alone or
# extended through a documented seam (a user theme, a plugin, a hook, a kitty
# `include`). The privileged steps are installing packages (through Omarchy's
# own `omarchy-pkg-add`) and the system Firefox policy — the overlay's one
# write outside $HOME — and --no-packages skips both, so the post-update hook
# never needs sudo.
set -euo pipefail

# The installer lives at the repository root, so the two are the same
# directory; both names are kept because they read differently ($HERE for
# shipped data files beside this script, $REPO_ROOT for git and the hook).
# ${BASH_SOURCE[0]} is /dev/fd/NN under `bash <(curl …)` and unset under
# `curl … | bash` (hence the $0 fallback, for set -u); either way no payload
# sits beside it and main() hands over to bootstrap.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$HERE"

# Everything under $HOME is reached through $HOME itself, which the hermetic
# test suite relocates; the seams below name what lies outside it — binaries
# and system paths — so the suite can point them at fakes. Never readonly —
# see the testing rules in AGENTS.md.
: "${_HYPRCONF_OMARCHY_PATH:=${OMARCHY_PATH:-/usr/share/omarchy}}"
# Omarchy's package front-end. A name, not a path, and overridable for the same
# reason as the zsh lookup below: on a real Omarchy box /usr/bin/omarchy-pkg-add
# is always on PATH, so a test asserting the "this is not Omarchy" refusal has
# no other way to make it absent.
: "${_HYPRCONF_PKG_ADD:=omarchy-pkg-add}"
# The zsh binary looked up on PATH. Overridable so a test can point the lookup
# at a name that does not exist until the package stage creates it.
: "${_HYPRCONF_ZSH_BIN:=zsh}"
# The kitty binary stage_terminal checks for. Overridable for the same reason
# as omarchy-pkg-add: a test proving the "kitty is not installed" stop has no
# other way to make it absent on a machine whose /usr/bin has one.
: "${_HYPRCONF_KITTY_BIN:=kitty}"
# Where the system Firefox policy lands. Root-owned, so the one stage that
# writes it goes through sudo; overridable so the hermetic suite can point it
# at a tmp tree. _HYPRCONF_ASSUME_TTY lets that suite reach the sudo path from
# a non-tty pytest run.
: "${_HYPRCONF_FIREFOX_POLICIES:=/etc/firefox/policies}"
: "${_HYPRCONF_ASSUME_TTY:=}"
# How long activate_plugin_copy waits for the shell to discover a freshly
# copied plugin (attempts x 0.05s). The hermetic suite sets it to 0 — its
# omarchy-plugin-list is a stub that never lists the copy.
: "${_HYPRCONF_PLUGIN_WAIT:=40}"
# Where the curl path (bootstrap) gets the checkout from and puts it. Plain
# names, not _HYPRCONF_*: these are for users too (a fork, a branch under
# test, a checkout somewhere other than ~/.hyprconf).
: "${HYPRCONF_REPO:=https://github.com/ak4dev/.hyprconf}"
: "${HYPRCONF_BRANCH:=stable}"
: "${HYPRCONF_DIR:=$HOME/.hyprconf}"

# The arguments as given, for bootstrap to hand to the checkout's copy: the
# option loop below shifts them away.
orig_args=("$@")

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
Usage: bash <(curl -fsSL hyprconf.sh) [OPTIONS]
       bash install.sh [OPTIONS]

Installs (or re-applies) the hyprconf overlay on an Omarchy system.

The curl form clones github.com/ak4dev/.hyprconf (branch stable) into
~/.hyprconf — or uses the checkout already there, without pulling it — and
runs that checkout's install.sh with the same options. HYPRCONF_REPO,
HYPRCONF_BRANCH and HYPRCONF_DIR override those three.

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

# ---------------------------------------------------------------- bootstrap

# The .hyprconf banner (the same art as assets/banner.svg). Colours only on a
# terminal, and NO screen clear — the post-update hook runs this script
# inside omarchy-update, whose output must stay on screen. $1 is the branch
# named on the second SYS line.
banner() {
    local wh='' gl='' ng='' am='' dm='' rs=''
    if [[ -t 1 ]]; then
        wh=$'\e[1;37m' gl=$'\e[1;31m' ng=$'\e[2;32m'
        am=$'\e[1;33m' dm=$'\e[2;37m' rs=$'\e[0m'
    fi
    # top noise line
    printf '%s  ▒░▒▓▒░░▒▓░░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░░▒▓░▒▓▒░▒░▒▓▒░▒▓%s\n' "$ng" "$rs"
    # .hyprconf logo — standard ASCII-art lowercase font. The (_) glyph on
    # rows 4–5 is the figlet rendering of the leading '.'; row 3 is
    # glitch-red, the corrupted-scanline artifact.
    printf '%s         _                                        __%s\n'                   "$dm" "$rs"
    printf '%s        | |__  _   _ _ __  _ __ ___ ___  _ __  / _|%s\n'                  "$wh" "$rs"
    printf "%s        | '_ \\| | | | '_ \\| '__/ __/ _ \\| '_ \\| |_%s\n"                "$gl" "$rs"
    printf '%s       _| | | | |_| | |_) | | | (_| (_) | | | |  _|%s\n'                  "$wh" "$rs"
    printf '%s     (_)|_| |_|\__, | .__/|_|  \___\___/|_| |_||_|%s\n'                   "$dm" "$rs"
    printf '%s               |___/|_|%s\n'                                               "$dm" "$rs"
    # bottom noise line + sys info
    printf '%s  ▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓▒░▒▓░░▒▓░▒▓░▒▓░▒▓░▒▓▒▓░▒▓░▒▓░░▒▓░▒▓░░▒▓░▒▓░▒▓%s\n' "$ng" "$rs"
    printf '%s  ──────────────────────────────────────────────────────────────────────%s\n'   "$dm" "$rs"
    printf '%s  [ SYS ] %-49s%s\n'                                                     "$am" "omarchy overlay" "hyprconf.sh"
    printf    '  [ SYS ] origin: github.com/ak4dev/.hyprconf   branch: %s%s\n'          "$1" "$rs"
    printf '%s  ──────────────────────────────────────────────────────────────────────%s\n\n' "$dm" "$rs"
}

# The banner, once per install: on a terminal only (or the suite's stand-in
# for one), never inside omarchy-update, and never twice on the curl path —
# bootstrap prints it, then exports HYPRCONF_BANNER_SHOWN before it hands
# over to the checkout's copy. The post-update hook needs its own gate: the
# tty test is TRUE there, because omarchy-update re-execs itself under
# script(1) (bin/omarchy-update, Omarchy 4.0.0-1: `exec env
# OMARCHY_UPDATE_LOGGED=1 script -qefc ...`), which puts a pty on every
# child's stdout — and exports OMARCHY_UPDATE_LOGGED to every one of them,
# which is the marker used here. The branch is $1, or the checkout's when
# not given.
show_banner() {
    [[ -z ${HYPRCONF_BANNER_SHOWN:-} && -z ${OMARCHY_UPDATE_LOGGED:-} ]] || return 0
    [[ -t 1 || -n $_HYPRCONF_ASSUME_TTY ]] || return 0
    local branch="${1:-}"
    [[ -n $branch ]] ||
        branch="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    banner "${branch:-unknown}"
}

# The curl path: `bash <(curl -fsSL hyprconf.sh)` runs this file from /dev/fd
# with nothing beside it, so nothing is applied from here. Preflight FIRST —
# a box without Omarchy is refused before anything lands on it — then the
# checkout is cloned into $HYPRCONF_DIR, or the one already there is used as
# it is (never pulled: that is --sync's job), and its own install.sh takes
# over with the arguments as given. That copy re-reads nothing from this
# one, so the served file can be any version that has this function.
bootstrap() {
    show_banner "$HYPRCONF_BRANCH"
    preflight
    command -v git >/dev/null 2>&1 ||
        die "git not on PATH — install it (omarchy-pkg-add git) and re-run"
    if [[ -d $HYPRCONF_DIR/.git ]]; then
        log "Using the existing checkout at $HYPRCONF_DIR"
    else
        log "Cloning $HYPRCONF_REPO ($HYPRCONF_BRANCH) into $HYPRCONF_DIR"
        git clone --branch "$HYPRCONF_BRANCH" --single-branch "$HYPRCONF_REPO" "$HYPRCONF_DIR" ||
            die "git clone failed — see the message above"
    fi
    [[ -f $HYPRCONF_DIR/install.sh ]] ||
        die "$HYPRCONF_DIR/install.sh not found — is $HYPRCONF_DIR a hyprconf checkout?"
    export HYPRCONF_BANNER_SHOWN=1
    exec bash "$HYPRCONF_DIR/install.sh" "$@"
}

# ------------------------------------------------------------------ helpers

# Replace the hyprconf-managed block in $1 with the contents of $2, preserving
# everything outside the markers: the old block is stripped, then the new one
# appended after one blank line. Byte-stable across repeated runs — trailing
# blank lines are dropped first, so a re-run cannot accumulate whitespace
# ahead of the block. The one block written is the zshrc one, so the markers
# are the '#'-comment pair.
write_managed_block() {
    local file="$1" block="$2" kept
    touch "$file"
    strip_managed_block "$file" "# >>> hyprconf >>>" "# <<< hyprconf <<<"
    kept="$(cat "$file")"   # command substitution strips trailing newlines
    {
        [[ -z $kept ]] || printf '%s\n\n' "$kept"
        cat "$block"
    } > "$file"
}

# Remove a managed block from $1 (markers $2/$3), preserving everything else.
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
    local target="$HOME/.config/hypr/$name"
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

# The system Firefox policy: telemetry off, tracking protection on, uBlock
# Origin force-installed. Firefox reads
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
    # Assert kitty is present BEFORE touching the default: omarchy-default-
    # terminal (Omarchy 4.0.0-1) checks nothing — it writes the desktop id
    # into ~/.config/xdg-terminals.list and notifies — so pointing it at an
    # absent kitty would leave SUPER+RETURN and every TUI launcher with no
    # terminal at all.
    command -v "$_HYPRCONF_KITTY_BIN" >/dev/null 2>&1 ||
        die "kitty is not installed — re-run without --no-packages"

    local current=""
    current="$(omarchy-default-terminal 2>/dev/null || true)"
    if [[ $current == kitty ]]; then
        info "already the default terminal"
    else
        # One file backs this: ~/.config/xdg-terminals.list. The SUPER+RETURN
        # bind, $TERMINAL, the floating terminals, the TUI launchers, the menu
        # and the bar all resolve through xdg-terminal-exec, so nothing else
        # needs patching. The setter's exit status is its closing
        # omarchy-notification-send's (no set -e in bin/omarchy-default-
        # terminal, 4.0.0-1), which fails with no shell to notify — a TTY
        # first run — after the list file is already written, so a failure
        # is a warning and the re-run finds kitty current.
        omarchy-default-terminal kitty ||
            warn "could not set kitty as the default terminal (set it with: omarchy default terminal kitty)"
    fi
    stage_kitty_include
}

# hyprconf's kitty preferences, layered as an include so Omarchy's kitty.conf
# stays authoritative — it owns the theme include, listen_on (Super+Return cwd
# inheritance) and the font_family/font_size lines its font tooling rewrites.
stage_kitty_include() {
    # Separate `local` statements on purpose: `local a=1 b="$a"` declares both
    # names before assigning, so $a is still unbound there — fatal under set -u.
    local dir="$HOME/.config/kitty"
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
    log "Theme: dracula"
    local link="$HOME/.config/omarchy/themes/dracula"
    mkdir -p "${link%/*}"
    # A real directory there is a theme the user installed themselves
    # (omarchy theme install) — not ours to replace, and `ln -sfn` would only
    # drop a stray link inside it (-n guards a link, not a directory).
    if [[ -e $link && ! -L $link ]]; then
        warn "$link is a real theme directory — left alone (move it away to get the overlay's dracula)"
        return 0
    fi
    # A SYMLINK on purpose, so a `git pull` updates the theme in place.
    # omarchy-theme-set (Omarchy 4.0.0-1) only needs `-d $USER_THEMES_PATH/<name>`
    # to hold and then `cp -r`s the directory's contents into the staged
    # theme — both follow a symlink, so nothing distinguishes it from a copy.
    ln -sfn "$HERE/themes/dracula" "$link"

    # Installed, never activated. Which theme is active is the user's choice,
    # and an install — or any of the re-applies that follow every Omarchy
    # update — must not take it away from them. (`omarchy-theme-set` is no
    # cheap no-op either: it rebuilds the staged theme, swaps symlinks and fans
    # out ~15 restart/retint commands.)
    local active="$HOME/.local/state/omarchy/current/theme.name"
    local name=""
    [[ -r $active ]] && name="$(cat "$active")"
    if [[ $name == dracula ]]; then
        info "already the active theme"
    else
        info "available in Omarchy's theme menu (SUPER+SHIFT+CTRL+SPACE) — the active theme is left as it is"
    fi
}

# Omarchy's screensaver starts after 150 s (config/omarchy/shell.json,
# idle.screensaver); hyprconf's desktop waited a quarter of an hour. Set
# ONCE — shell.json is the user's file (Omarchy's manual, Dotfiles), and a
# timeout changed later must stay theirs. Omarchy 4.0.0-1 ships no command
# for these keys (grep -rl screensaver /usr/share/omarchy/bin finds none;
# omarchy-shell-config is a sourced helper, omarchy:hidden=true), so the file
# is edited the way that helper's commit() does it: jq over the user file —
# or the shipped defaults when there is none yet — an atomic move, then
# `omarchy-shell shell reloadConfig`. Only the screensaver key; the lock
# timeout is left as Omarchy has it.
stage_idle() {
    log "Idle: screensaver after 15 minutes"
    local marker="$HOME/.local/state/hyprconf/idle-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the timeouts are yours now"
        return 0
    fi
    command -v jq >/dev/null 2>&1 || {
        warn "jq not available — will retry on the next run"
        return 0
    }
    local json="$HOME/.config/omarchy/shell.json" src
    src="$json"
    [[ -s $json ]] || src="$_HYPRCONF_OMARCHY_PATH/config/omarchy/shell.json"
    if [[ ! -f $src ]]; then
        warn "no shell.json to edit ($src) — will retry on the next run"
        return 0
    fi
    mkdir -p "$(dirname "$json")"
    if jq -S '.idle = ((.idle // {}) + { screensaver: 900 })' "$src" > "$json.tmp"; then
        mv "$json.tmp" "$json"
    else
        rm -f "$json.tmp"
        warn "could not edit $json — will retry on the next run"
        return 0
    fi
    omarchy-shell shell reloadConfig >/dev/null 2>&1 ||
        omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
    mkdir -p "$(dirname "$marker")"
    : > "$marker"
    info "idle.screensaver = 900 s (edit ~/.config/omarchy/shell.json to change it; lock stays as it is)"
}

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
    local marker="$HOME/.local/state/hyprconf/defaults-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the defaults are yours now"
        return 0
    fi

    local seeded=1
    omarchy-default-browser firefox || {
        seeded=0
        warn "could not set firefox as the default browser (set it with: omarchy default browser firefox)"
    }
    omarchy-default-editor code || {
        seeded=0
        warn "could not set code as the default editor (set it with: omarchy default editor code)"
    }
    # No marker on a failed seed — a first run with --no-packages (firefox
    # and code not installed yet) must not record the defaults as applied.
    if (( seeded )); then
        mkdir -p "$(dirname "$marker")"
        : > "$marker"
        info "browser=firefox editor=code (change with: omarchy default browser|editor <name>)"
    else
        warn "defaults not seeded — will retry on the next run"
    fi
}

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
        dest="$HOME/.config/omarchy/backgrounds/$theme"
        mkdir -p "$dest"
        if [[ -e $dest/$file ]]; then
            info "$file already in the $theme backgrounds"
        else
            install -m 644 "$HERE/wallpapers/$file" "$dest/$file"
            info "$file -> $theme backgrounds (SUPER+CTRL+SPACE to pick it)"
        fi
    done
}

# The system monospace font, set ONCE on first install and never again.
#
# Which font is running is a user-facing choice, and this installer re-runs
# after every Omarchy update via the post-update hook — without the marker, a
# font the user picked later would be silently reverted to ours on the next
# update, exactly the way the theme used to be taken back.
stage_font() {
    log "Font: Geist Mono Nerd Font"
    local marker="$HOME/.local/state/hyprconf/font-applied"
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
    mkdir -p "$HOME/.config/hypr/scripts"
    link_hypr_override bindings.lua
    local f
    for f in switch_monitor.sh adjust-gaps; do
        install -m 755 "$HERE/hypr/scripts/$f" "$HOME/.config/hypr/scripts/$f"
    done
}

stage_looknfeel() {
    log "Look'n'feel and input (natural scroll, gaps, blur, gestures)"
    mkdir -p "$HOME/.config/hypr"
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
    # Only bedroom and kitchen have hotkeys. The rest are
    # `~/.config/hypr/scripts/switch_monitor.sh {K,pc,laptop}`.
    #
    # Omarchy's own monitors.lua is saved first, and once: switch_monitor.sh
    # symlinks the chosen preset straight over that path, so without this the
    # first hotkey press would destroy Omarchy's auto layout with no way back.
    # `switch_monitor.sh stock` restores this copy.
    local active="$HOME/.config/hypr/monitors.lua"
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
        if [[ -e $HOME/.config/hypr/$f ]]; then
            if [[ -f $stock_monitors ]] && cmp -s "$HOME/.config/hypr/$f" "$stock_monitors"; then
                warn "$f is Omarchy's stock monitors.lua template — an \`omarchy refresh\` wrote" \
                     "through the monitors.lua symlink; your preset is in" \
                     "$HOME/.config/hypr/monitors.lua.bak.<epoch> (copy it back, or delete" \
                     "$f and re-run to re-seed the repo's version)"
            fi
            continue
        fi
        install -m 644 "$HERE/hypr/$f" "$HOME/.config/hypr/$f"
        info "seeded $f"
    done
}

stage_fastfetch() {
    log "fastfetch greeting"
    # Omarchy ships fastfetch but no fastfetch config of its own — nothing to
    # displace, so hyprconf's layout is simply linked in. ~/.zshrc runs it as
    # the shell greeting, exactly as hyprconf's own .zshrc always has.
    local dir="$HOME/.config/fastfetch"
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
    mkdir -p "$HOME/.local/bin"
    local f
    # Every bin/hyprconf-* file; a new tool is one file in bin/. @HYPRCONF_DIR@
    # is substituted the way the hooks get it, for the tools that need the
    # checkout (the Python lib).
    for f in "$HERE"/bin/hyprconf-*; do
        sed "s|@HYPRCONF_DIR@|$REPO_ROOT|g" "$f" > "$HOME/.local/bin/${f##*/}"
        chmod 755 "$HOME/.local/bin/${f##*/}"
    done
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) warn "$HOME/.local/bin is not on PATH — hotkeys calling these tools will fail" ;;
    esac
}

# Dual-GPU boxes: Wine pins every monitor to the first Vulkan GPU it
# enumerates (Xwayland exposes no RandR providers), so when the GPU driving
# the displays is not Vulkan device 0 — PCI order, not where the monitors are
# plugged in — every Proton game dies at swapchain creation. The fix is
# session environment (a ~/.config/uwsm/env.d/ file, Omarchy's documented
# override seam, /usr/share/uwsm/env.d/10-omarchy), and hyprconf-vulkan-gpu,
# which stage_bin just put on ~/.local/bin, owns the whole decision: it
# diagnoses sysfs (and vulkaninfo when present), bows out when there is one
# GPU, the right one is already device 0, the box is already configured
# (uwsm env.d, uwsm/env, environment.d or the live environment) or the user
# chose Ignore, and never prompts without a terminal or inside omarchy-update
# (OMARCHY_UPDATE_LOGGED, the marker show_banner gates on: script(1)'s pty
# would pass its tty test) — the post-update hook's run gets one info line and
# exit 0. This stage only runs it; its failure is a warning, never a failed
# install.
stage_vulkan_gpu() {
    log "Dual-GPU Vulkan check (hyprconf-vulkan-gpu)"
    "$HOME/.local/bin/hyprconf-vulkan-gpu" prompt ||
        warn "hyprconf-vulkan-gpu did not complete — see: hyprconf-vulkan-gpu status"
}

# hyprconf's rows in Omarchy's menu, through Omarchy's own seam for them:
# ~/.config/omarchy/extensions/omarchy-menu.jsonc, the one user file the menu
# merges over its defaults (shell/plugins/menu/Menu.qml, userMenuPath; the
# FileView watches it, so an edit shows up with no shell restart). Omarchy
# 4.0.0-1 ships no command that edits that file — `omarchy commands --json`
# has no menu-extension route, and omarchy-menu only summons — so it is
# edited here, in a managed block kept immediately before the closing brace.
# The shape is dictated by the parser (shell/plugins/menu/MenuModel.js,
# stripJsonc): it drops only comment lines that START with //, and only a
# comma right before a } or ], and one parse failure silently drops the WHOLE
# user file. Hence: markers on comment lines of their own, every entry in the
# block ending with a comma, and the user's own last entry ahead of the block
# given the comma it then needs. Seeded from Omarchy's template (all
# comments) when the user has no file yet; the previous block is stripped
# first, and the file is left untouched when nothing would change.
#
# One row: Proton VPN under Install > Service, beside Omarchy's own NordVPN
# row and shaped exactly like it (default/omarchy/omarchy-menu.jsonc,
# install.service.nordvpn) — dotted id, `when` hides it once installed, and
# the floating presentation terminal runs bin/hyprconf-install-service-
# protonvpn, which stage_bin put on ~/.local/bin (on PATH in the session:
# default/bash/envs appends it, and the bar widgets find hyprconf-stats the
# same way).
stage_menu() {
    log "Omarchy menu: Proton VPN installer (Install > Service)"
    local file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
    local template="$_HYPRCONF_OMARCHY_PATH/config/omarchy/extensions/omarchy-menu.jsonc"
    local begin='  // >>> hyprconf >>>' end='  // <<< hyprconf <<<'
    local entry='  "install.service.protonvpn": {"icon":"󰦝","label":"Proton VPN","when":"! omarchy-pkg-present proton-vpn-gtk-app","action":"omarchy-launch-floating-terminal-with-presentation hyprconf-install-service-protonvpn"},'

    mkdir -p "${file%/*}"
    # Absent or empty — a touched or truncated file holds nothing of the
    # user's and is unparseable for the menu as it is — it is seeded.
    if [[ ! -s $file ]]; then
        if [[ -f $template ]]; then
            cp "$template" "$file"
            info "seeded omarchy-menu.jsonc from Omarchy's template"
        else
            printf '{\n}\n' > "$file"
        fi
        chmod 644 "$file"
    fi

    # Through a symlink (a stow-style dotfiles checkout), never over it. The
    # rewrite is done on a copy beside the real file — the block stripped,
    # then re-inserted — and moved into place only when the bytes differ.
    local target tmp
    target="$(readlink -f "$file")"
    tmp="$(mktemp "$target.XXXXXX")"
    cp "$target" "$tmp"
    strip_managed_block "$tmp" "$begin" "$end"
    if ! awk -v b="$begin" -v e="$end" -v entry="$entry" '
        { lines[NR] = $0 }
        END {
            close_at = 0
            for (i = NR; i >= 1; i--)
                if (lines[i] ~ /^[[:space:]]*}[[:space:]]*$/) { close_at = i; break }
            if (!close_at) exit 3
            # The last line of content the user owns: blank lines and
            # whole-line comments do not count (the parser drops those).
            prev = 0
            for (i = close_at - 1; i >= 1; i--) {
                if (lines[i] ~ /^[[:space:]]*$/) continue
                if (lines[i] ~ /^[[:space:]]*\/\//) continue
                prev = i; break
            }
            for (i = 1; i < close_at; i++) {
                line = lines[i]
                if (i == prev && line !~ /[,{][[:space:]]*$/) line = line ","
                print line
            }
            print b; print entry; print e
            # Trailing empty lines go now: a re-run strips the block with
            # strip_managed_block, which drops them, so keeping them here
            # would make the first re-run a rewrite instead of a no-op.
            last = NR
            while (last > close_at && lines[last] == "") last--
            for (i = close_at; i <= last; i++) print lines[i]
        }' "$tmp" > "$tmp.new"; then
        rm -f "$tmp" "$tmp.new"
        warn "$file has no closing-brace line to put the hyprconf block before — add the Proton VPN row by hand"
        return 0
    fi
    rm -f "$tmp"
    if cmp -s "$tmp.new" "$target"; then
        rm -f "$tmp.new"
        info "already current"
        return 0
    fi
    chmod --reference="$target" "$tmp.new"
    mv "$tmp.new" "$target"
    info "install.service.protonvpn -> $file (SUPER+D > Install > Service)"
}

stage_bar_plugin() {
    log "Resource-usage bar widget (hyprconf.resources)"
    sync_plugin_dir hyprconf-resources hyprconf.resources
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
    local dir="$HOME/.config/omarchy/plugins/$target_id"
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
    mkdir -p "$HOME/.config/omarchy/plugins"
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
# still attempted, and its failure status is the caller's retry signal. No
# wait at all with no shell to ask (omarchy-plugin-list exits 1 the moment
# omarchy-shell reports "is not running"): a TTY run has nothing to wait for.
activate_plugin_copy() {
    local id="$1" _attempt list
    shift
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
    for (( _attempt = 0; _attempt < _HYPRCONF_PLUGIN_WAIT; _attempt++ )); do
        list="$(omarchy-plugin-list --json 2>/dev/null)" || break
        jq -e --arg id "$id" 'any(.[]; .id == $id)' <<<"$list" >/dev/null 2>&1 && break
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
# overlay links out of the checkout; when the files changed, main() reloads
# the shell once.
sync_plugin_dir() {
    local src="$HERE/plugins/$1" id="$2"
    local dir="$HOME/.config/omarchy/plugins/$id"
    if [[ -d $dir ]] && diff -rq "$src" "$dir" >/dev/null 2>&1; then
        return 0
    fi
    mkdir -p "$HOME/.config/omarchy/plugins"
    rm -rf "$dir"
    cp -r "$src" "$dir"
    shell_reload_needed=1
    info "widget files synced from plugins/$1"
}

# Enable a plugin ONCE. Whether a widget is on the bar is the user's call from
# then on — `omarchy plugin disable <id>` is a choice, and the post-update
# hook re-runs this installer after every Omarchy update, so an unconditional
# enable would put the widget back every time. Same marker pattern as the
# font and the default apps. Needs the live shell; a TTY or SSH run leaves
# the marker unwritten so the next in-session run tries again.
enable_plugin_once() {
    local id="$1" marker="$HOME/.local/state/hyprconf/$2"
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

# Wait (bounded) for the shell to have persisted the LAST thing it was asked
# for: shell.json satisfies the jq predicate $1 (--arg pairs may follow).
# Its config writes are asynchronous (PluginRegistry hands every mutation to
# a FileView), so a read of the file — or a read-modify-write, see
# follow_center_anchor — straight after an enable, a set or a move can work
# on a stale copy. Advisory: on timeout the caller carries on.
wait_for_shell_json() {
    local filter="$1" json="$HOME/.config/omarchy/shell.json" _attempt
    shift
    for (( _attempt = 0; _attempt < _HYPRCONF_PLUGIN_WAIT; _attempt++ )); do
        [[ -f $json ]] && jq -e "$@" "$filter" "$json" >/dev/null 2>&1 && return 0
        sleep 0.05
    done
    return 0
}

# jq: the ids on the bar (layout entries are bare strings or objects with an
# id — omarchy-bar's own entry_id rule), for the predicates below.
_JQ_IDS='def ids: [.bar.layout // {} | .[]? | .[]? | if type == "string" then . else (.id // "") end];'

# Wait for a copy's swap into the stock widget's slot to be on disk: $2 on
# the bar and $1 off it — the shape after an enable (the copy replaces the
# stock entry).
wait_for_swap() {
    wait_for_shell_json "$_JQ_IDS"' (ids | any(. == $keep)) and (ids | all(. != $stock))' \
        --arg stock "$1" --arg keep "$2"
}

# The bar centers on an anchor id, and canonicalWidgetId does no clone
# resolution (shell/Commons/Util.qml — a plain string cast), so an anchor
# left at omarchy.clock matches nothing once the bar swaps to our copy and
# the clock drifts off-center. Follow the swap — but only while the anchor
# still points at the stock id, so a user's own anchor choice is never
# overridden. A read-modify-write of the shell's own file: the caller waits
# (wait_for_shell_json) for the last thing it asked the shell for to be on
# disk first, or the edit lands on a stale copy and the shell's pending
# write then takes it back.
follow_center_anchor() {
    local stock="$1" keep="$2" shell_json="$HOME/.config/omarchy/shell.json"
    if [[ -f $shell_json ]] &&
        [[ "$(jq -r '.bar.centerAnchor // ""' "$shell_json")" == "$stock" ]]; then
        jq --arg id "$keep" '.bar.centerAnchor = $id' "$shell_json" > "$shell_json.tmp" &&
            mv "$shell_json.tmp" "$shell_json"
        info "bar centerAnchor follows $keep"
    fi
}

# hyprconf's clock format on a copy, through omarchy-bar, then a wait for it
# to be on disk: it is the last thing the shell is asked for before
# follow_center_anchor edits shell.json itself.
set_clock_format() {
    local id="$1" format="hh:mm:ss AP"
    if ! omarchy-bar set "$id" format "$format" >/dev/null 2>&1; then
        warn "could not set the clock format (set it with: omarchy bar set $id format '$format')"
        return 0
    fi
    wait_for_shell_json 'any(.bar.layout // {} | .[]? | .[]?; type == "object" and .id == $id and .format == $format)' \
        --arg id "$id" --arg format "$format"
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
    local marker="$HOME/.local/state/hyprconf/clock-applied"
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
    local dir="$HOME/.config/omarchy/plugins/$id"
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
    wait_for_swap omarchy.clock "$id"
    set_clock_format "$id"
    follow_center_anchor omarchy.clock "$id"

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
    sync_plugin_dir hyprconf-workspaces hyprconf.workspaces
    enable_plugin_once hyprconf.workspaces workspaces-applied
}

# The focused window's title beside the workspaces, as hyprconf's own bar
# drew it — on TWO lines. Omarchy's stock omarchy.active-window widget is
# the same thing on one line (elided title, tooltip with the full one, click
# focuses, middle-click closes) and reads one setting, maxWidth, so the
# two-line version is the overlay's own copy (plugins/hyprconf-active-window,
# header comment there): clonedFrom the stock widget, so the shell swaps it
# into the stock widget's slot and routes the stock IPC to it, and `omarchy
# plugin disable hyprconf.active-window` restores stock. Synced every run,
# enabled ONCE with no placement of its own: the manifest's defaultSection
# is left, and the shell anchors a left-section widget right after
# omarchy.workspaces — resolved to hyprconf.workspaces while that copy is on
# the bar (PluginRegistry.qml barTarget / findRelativeBarLocation, 4.0.0-1).
# The character budget is the stock setting: `omarchy bar set
# hyprconf.active-window maxWidth 400`.
stage_window_title() {
    log "Bar window title, two lines (hyprconf.active-window)"
    sync_plugin_dir hyprconf-active-window hyprconf.active-window
    enable_plugin_once hyprconf.active-window active-window-applied
}

stage_shell() {
    log "Shell: zsh + powerlevel10k in the terminal"
    # Deliberately NO chsh. The login shell stays bash, so Omarchy's rc chain,
    # its aliases/functions/completions, uwsm, SSH and scripts are untouched.
    # kitty is what launches zsh (see stage_kitty_include), and .zshrc sources
    # Omarchy's own env/alias files so its updates keep flowing through.
    [[ -n $_HYPRCONF_ZSH ]] || { warn "zsh not installed — skipping"; return 0; }

    if [[ ! -d $HOME/.oh-my-zsh ]]; then
        info "Installing Oh My Zsh"
        git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh"
    fi

    local p10k="$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
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

    ln -sfn "$HERE/zsh/.p10k.zsh" "$HOME/.p10k.zsh"
    write_managed_block "$HOME/.zshrc" "$HERE/zsh/zshrc.block"
}

# Every hook the overlay ships, hooks/<name>.d/<file>, into the matching
# ~/.config/omarchy/hooks/<name>.d/ — the directories omarchy-hook runs
# (post-update from omarchy-update, theme-set from omarchy-theme-set).
stage_hooks() {
    log "Omarchy hooks (post-update, theme-set)"
    local src dir
    for src in "$HERE"/hooks/*.d/*; do
        dir="$HOME/.config/omarchy/hooks/$(basename "$(dirname "$src")")"
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
    local hook="$HOME/.config/omarchy/hooks/theme-set.d/10-hyprconf"
    local name="$HOME/.local/state/omarchy/current/theme.name"
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
    # No payload beside this file: the curl path. bootstrap execs or dies.
    [[ -d $HERE/hypr && -f $HERE/packages ]] || bootstrap "${orig_args[@]}"
    show_banner
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
    stage_idle
    stage_hotkeys
    stage_looknfeel
    stage_monitors
    stage_fastfetch
    stage_bin
    # Right after stage_bin: it runs the tool that stage just installed.
    stage_vulkan_gpu
    stage_menu
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

main
