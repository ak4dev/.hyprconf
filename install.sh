#!/usr/bin/env bash
# Installs the hyprconf overlay on top of a fresh Omarchy install.
#
#   bash <(curl -fsSL --proto '=https' https://hyprconf.sh)
#
# hyprconf.sh serves this very file to curl and wget. Run that way it has no
# payload beside it, so it clones github.com/ak4dev/.hyprconf (branch stable)
# into ~/.hyprconf — or uses the checkout already there — and hands over to
# that checkout's own copy (see bootstrap). The same by hand:
#
#   git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
#   bash ~/.hyprconf/install.sh
#
# Every module is idempotent, so re-running is the supported way to pick up
# changes after a `git pull`; `hyprsync` is the alias for `--sync`, and
# `hyprconf <module>` re-applies one module after an edit to its payload.
#
# Design rule throughout: impact Omarchy as little as possible. Nothing here
# changes the login shell, and everything Omarchy owns is either left alone or
# extended through a documented seam (a user theme, a plugin, a hook, a kitty
# `include`). This file asks for no sudo at all: every package and every root
# write belongs to the module that wants it, behind HYPRCONF_NO_SUDO, which
# --no-packages exports — so the post-update hook never needs a password.
set -euo pipefail

# The checkout: the installer lives at the repository root. ${BASH_SOURCE[0]}
# is /dev/fd/NN under `bash <(curl …)` and unset under `curl … | bash` (hence
# the $0 fallback, for set -u); either way no payload sits beside it and
# main() hands over to bootstrap.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# $HERE lands in stage_hooks' `sed "s|@HYPRCONF_DIR@|...|g"`, where '&' reads
# back the match, '|' ends the expression and '\' escapes: escape all three
# once, or a checkout under a path like ~/a&b installs a hook that points
# nowhere.
HERE_SED=${HERE//\\/\\\\}; HERE_SED=${HERE_SED//&/\\&}; HERE_SED=${HERE_SED//|/\\|}

# Everything under $HOME is reached through $HOME itself, which the hermetic
# test suite relocates; the seams below name what lies outside it — binaries
# and system paths — so the suite can point them at fakes. Never readonly —
# see the testing rules in AGENTS.md. OMARCHY_PATH is Omarchy's own variable
# (default/bash/env-bootstrap), with Omarchy's own fallback.
: "${OMARCHY_PATH:=/usr/share/omarchy}"
# The command preflight asks for to decide "is this Omarchy". A name, not a
# path, and overridable because on a real Omarchy box /usr/bin/omarchy-pkg-add
# is always on PATH, so a test asserting that refusal has no other way to make
# it absent. Nothing here calls it: the modules install their own packages.
: "${_HYPRCONF_PKG_ADD:=omarchy-pkg-add}"
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
no_update=0
only=()

log()  { printf '==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die()  { printf 'hyprconf: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: bash <(curl -fsSL --proto '=https' https://hyprconf.sh) [OPTIONS]
       bash install.sh [OPTIONS] [MODULE...]

Installs (or re-applies) the hyprconf overlay on an Omarchy system.

The curl form clones github.com/ak4dev/.hyprconf (branch stable) into
~/.hyprconf — or uses the checkout already there, without pulling it — and
runs that checkout's install.sh with the same options. HYPRCONF_REPO,
HYPRCONF_BRANCH and HYPRCONF_DIR override those three.

Options:
  --sync          Pull the hyprconf checkout, re-apply, then run omarchy-update
                  (whose post-update hook re-applies once more, after Omarchy's
                  migrations). This is what the `hyprsync` alias runs.
  --no-update     Apply only; never invoke omarchy-update. Used by the
                  post-update hook, which already runs inside an update.
  --no-packages   Skip everything that needs sudo: every module's packages and
                  its own root work. Exported to the modules as
                  HYPRCONF_NO_SUDO, which each one honours itself.
  -h, --help      Show this help.

With no options: apply every module once, without pulling or updating. A
MODULE name (a directory under modules/) applies only the ones named — the
re-apply after an edit to that module's files, e.g. `hyprconf hypr`.
USAGE
}

while (( $# )); do
    case "$1" in
        --sync)        do_pull=1; do_update=1 ;;
        --no-update)   no_update=1 ;;
        # Nothing but an export: install.sh itself asks for no sudo any
        # more. Every modules/*/install reads this and bows out of its own
        # sudo work with one pointer line and exit 0.
        --no-packages) export HYPRCONF_NO_SUDO=1 ;;
        -h|--help)     usage; exit 0 ;;
        -*)            die "unknown option: $1 (try --help)" ;;
        # A module name: apply only the ones named. Checked in main(), once
        # a checkout is beside this file — on the curl path there is none yet.
        *)             only+=("$1") ;;
    esac
    shift
done
# "never invoke omarchy-update" means never, whichever order the flags came
# in: --sync sets do_update, and a last-wins loop would let
# `--no-update --sync` run the update anyway.
if (( no_update )); then do_update=0; fi

# ---------------------------------------------------------------- preflight

# Refuse to run anywhere that isn't Omarchy. This overlay assumes Omarchy owns
# the base system; run against a hand-built Hyprland desktop it would fight
# that machine's own configuration.
preflight() {
    # The overlay writes the invoking user's $HOME, and asks for sudo only in
    # the modules that do their own root work behind HYPRCONF_NO_SUDO; run
    # under sudo it half-installs into /root
    # (env_reset sets HOME) and the curl|bash habit of prefixing sudo is the
    # dangerous one. No seam: the suite runs unprivileged, CI included.
    if ((EUID == 0)); then
        die "run as your regular user — the modules ask for sudo themselves where they need it."
    fi
    [[ -d $OMARCHY_PATH ]] ||
        die "no Omarchy found at $OMARCHY_PATH — this overlay installs on top of Omarchy."
    command -v "$_HYPRCONF_PKG_ADD" >/dev/null 2>&1 ||
        die "$_HYPRCONF_PKG_ADD not on PATH — this overlay installs on top of Omarchy."
}

# ---------------------------------------------------------------- bootstrap

# The curl path: `bash <(curl -fsSL --proto '=https' https://hyprconf.sh)` runs this file from /dev/fd
# (schemeless, curl's first request is plaintext port 80 and an on-path
# attacker answers it before the https redirect exists — hence the scheme
# and --proto, which also refuses any downgrade redirect)
# with nothing beside it, so nothing is applied from here. Preflight FIRST —
# a box without Omarchy is refused before anything lands on it — then the
# checkout is cloned into $HYPRCONF_DIR, or the one already there is used as
# it is (never pulled: that is --sync's job), and its own install.sh takes
# over with the arguments as given. That copy re-reads nothing from this
# one, so the served file can be any version that has this function.
bootstrap() {
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
    exec bash "$HYPRCONF_DIR/install.sh" "$@"
}

# ------------------------------------------------------------------- stages

stage_pull() {
    log "Updating the hyprconf checkout"
    if ! git -C "$HERE" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
        info "no upstream configured — skipping pull"
        return 0
    fi
    # --ff-only, never a hard reset: on the Omarchy machine this checkout is
    # also where the overlay gets edited. Diverged history is a stop, not
    # something to silently discard.
    #
    # NB: a pull that changes this script does not affect the run in progress —
    # bash has already read it. Everything a later stage or a module reads
    # (each module's `install` and its payload) IS read fresh, so only this
    # file's own logic is a version behind. Re-run to pick that up.
    #
    # `-c pull.rebase=false` is for the reader with `pull.rebase = true` in
    # their global git config — a common setting, and under it `--ff-only`
    # refuses outright with "cannot pull with rebase: You have unstaged
    # changes" whenever the checkout is dirty, which is the normal state of a
    # box the overlay is edited on. The pin covers this invocation only, and
    # --ff-only still stops on a real divergence. The message does not guess
    # at the cause: git has already printed it.
    git -C "$HERE" -c pull.rebase=false pull --ff-only ||
        die "git pull failed (git's own error is above) — resolve it and re-run"
}

# The installer itself, under its own name: `hyprconf --sync` is what the
# hyprsync alias in modules/shell-zsh/zshrc runs, and `hyprconf <module>` the
# re-apply after an edit. A symlink, not a copy — there is nothing in this
# file to substitute, and it has to stay the file a `git pull` updates —
# behind a readlink test, so a re-run writes nothing. With the hook below it
# is all install.sh puts in $HOME of its own: every tool is a module's, linked
# into the same directory by that module (default/bash/env-bootstrap:37-40
# puts it on the session PATH).
stage_link() {
    log "The hyprconf command (~/.local/bin/hyprconf -> install.sh)"
    mkdir -p "$HOME/.local/bin"
    [[ "$(readlink "$HOME/.local/bin/hyprconf" 2>/dev/null)" == "$HERE/install.sh" ]] ||
        ln -sfn "$HERE/install.sh" "$HOME/.local/bin/hyprconf"
}

# Every hook install.sh itself ships, hooks/<type>.d/<file>, into the matching
# ~/.config/omarchy/hooks/<type>.d/ — the directories omarchy-hook runs. Only
# post-update is left here; the theme-set hook is modules/firefox-theme's, and
# that module installs it itself, self-contained (no @HYPRCONF_DIR@ to render).
# Through Omarchy's own `omarchy-hook-install <type> <file>` (4.0.0-1:
# mkdir -p the .d dir, cp under the file's basename, chmod 755; unchanged on
# 4.0.2-1, bin/omarchy-hook-install:27-29). The hook is rendered first, with
# @HYPRCONF_DIR@ substituted, into a temp dir under its final basename,
# since the basename is the name it is installed under. No hand-rolled copy
# when the command is missing (rule 1): preflight has already refused a box
# without Omarchy, and the command has shipped since the 4.0.0-1 pin — a
# failure is a warning, and the next run retries.
stage_hooks() {
    log "Omarchy hooks (post-update, theme-set)"
    local src type file tmp
    tmp="$(mktemp -d)"
    for src in "$HERE"/hooks/*.d/*; do
        type="$(basename "$(dirname "$src")")"
        type="${type%.d}"
        file="$tmp/${src##*/}"
        sed "s|@HYPRCONF_DIR@|$HERE_SED|g" "$src" > "$file"
        omarchy-hook-install "$type" "$file" >/dev/null ||
            warn "omarchy-hook-install $type ${src##*/} failed"
    done
    rm -rf "$tmp"
}

stage_update() {
    log "Updating Omarchy"
    # Omarchy's own updater, never pacman: an ALPM AbortOnFail hook blocks
    # sysupgrade forms outside this path. It runs omarchy-migrate and then
    # `omarchy-hook post-update` (bin/omarchy-update:48-49, 4.0.2-1), so the
    # overlay's own hook re-applies every stage once more, AFTER the
    # migrations — on purpose, not a redundancy to skip: a migration that
    # rewrites bindings.lua, kitty.conf or shell.json does so after the
    # apply above, and that second run is the one that puts them back. Not
    # a loop: the hook passes --no-update.
    omarchy-update
}

# --------------------------------------------------------------------- main

main() {
    # No payload beside this file: the curl path. bootstrap execs or dies.
    [[ -d $HERE/modules ]] || bootstrap "${orig_args[@]}"
    preflight
    # Self-contained modules: each one applies, gates and undoes itself
    # (modules/<name>/README.md), installs its own packages behind its own
    # HYPRCONF_NO_SUDO gate, and is order-free — the glob runs them
    # alphabetically. A name on the command line narrows the loop to the
    # modules named, checked before anything runs.
    local m mods=()
    if (( ${#only[@]} )); then
        for m in "${only[@]}"; do
            [[ -x $HERE/modules/$m/install ]] || die "no module named $m (the directories under modules/)"
            mods+=("$HERE/modules/$m/install")
        done
    else
        mods=("$HERE"/modules/*/install)
    fi
    if (( do_pull )); then stage_pull; fi
    for m in "${mods[@]}"; do bash "$m"; done
    stage_link
    stage_hooks
    if (( do_update )); then stage_update; fi

    log "Done."
}

main
