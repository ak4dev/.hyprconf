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
# Every stage is idempotent, so re-running is the supported way to pick up
# changes after a `git pull`. `hyprsync` is the alias for `--sync`.
#
# Design rule throughout: impact Omarchy as little as possible. Nothing here
# changes the login shell, and everything Omarchy owns is either left alone or
# extended through a documented seam (a user theme, a plugin, a hook, a kitty
# `include`). The privileged steps are installing packages (through Omarchy's
# own `omarchy-pkg-add`), Firefox and VS Code (through Omarchy's own
# installers), the system Firefox policy and the Keychron udev rule — the
# overlay's two writes outside $HOME — and --no-packages skips them all, so
# the post-update hook never needs sudo.
set -euo pipefail

# The checkout: the installer lives at the repository root. ${BASH_SOURCE[0]}
# is /dev/fd/NN under `bash <(curl …)` and unset under `curl … | bash` (hence
# the $0 fallback, for set -u); either way no payload sits beside it and
# main() hands over to bootstrap.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# $HERE lands in `sed "s|@HYPRCONF_DIR@|...|g"` replacements (stage_bin,
# stage_hooks), where '&' reads back the match, '|' ends the expression and
# '\' escapes: escape all three once, or a checkout under a path like
# ~/a&b installs tools and hooks that point nowhere.
HERE_SED=${HERE//\\/\\\\}; HERE_SED=${HERE_SED//&/\\&}; HERE_SED=${HERE_SED//|/\\|}

# Everything under $HOME is reached through $HOME itself, which the hermetic
# test suite relocates; the seams below name what lies outside it — binaries
# and system paths — so the suite can point them at fakes. Never readonly —
# see the testing rules in AGENTS.md. OMARCHY_PATH is Omarchy's own variable
# (default/bash/env-bootstrap), with Omarchy's own fallback.
: "${OMARCHY_PATH:=/usr/share/omarchy}"
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
# Where the system Firefox policy lands. Root-owned, so the stage that writes
# it goes through sudo; overridable so the hermetic suite can point it at a tmp
# tree. _HYPRCONF_ASSUME_TTY lets that suite reach the sudo path from a non-tty
# pytest run.
: "${_HYPRCONF_FIREFOX_POLICIES:=/etc/firefox/policies}"
: "${_HYPRCONF_ASSUME_TTY:=}"
# Where the Keychron hidraw rule lands — root-owned for the same reason, and
# overridable for the same reason. udev reads /etc/udev/rules.d before its own
# /usr/lib tree, and 70- must sort before systemd's 73-seat-late.rules.
: "${_HYPRCONF_UDEV_RULES:=/etc/udev/rules.d}"
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
no_update=0

log()  { printf '==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die()  { printf 'hyprconf: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: bash <(curl -fsSL --proto '=https' https://hyprconf.sh) [OPTIONS]
       bash install.sh [OPTIONS]

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
  --no-packages   Skip the four stages that need sudo: packages, Firefox (and
                  its policy), VS Code and the Keychron udev rule.
  -h, --help      Show this help.

With no options: apply every stage once, without pulling or updating.
USAGE
}

while (( $# )); do
    case "$1" in
        --sync)        do_pull=1; do_update=1 ;;
        --no-update)   no_update=1 ;;
        --no-packages) do_packages=0 ;;
        -h|--help)     usage; exit 0 ;;
        *)             die "unknown option: $1 (try --help)" ;;
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
    # The overlay writes the invoking user's $HOME and asks for sudo itself
    # in the four gated stages; run under sudo it half-installs into /root
    # (env_reset sets HOME) and the curl|bash habit of prefixing sudo is the
    # dangerous one. CI runs the hermetic suite as root, hence the seam.
    if ((EUID == 0)) && [[ -z ${_HYPRCONF_ALLOW_ROOT:-} ]]; then
        die "run as your regular user — install.sh asks for sudo itself where a stage needs it."
    fi
    [[ -d $OMARCHY_PATH ]] ||
        die "no Omarchy found at $OMARCHY_PATH — this overlay installs on top of Omarchy."
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
        branch="$(git -C "$HERE" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    banner "${branch:-unknown}"
}

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

# How $1's hyprconf-managed block looks: "both" markers, a "half" pair, or
# "none". Every marker state machine below latches skip=1 at the begin marker
# and clears it only at an end marker, so rewriting a file that has lost one
# of the pair — a botched manual revert, a dotfiles merge, a trimmed tail —
# deletes everything from the marker to EOF, at exit 0, with no backup and
# nothing said. A half pair is a file this installer does not understand:
# every caller leaves it exactly as it is and says so.
managed_block_state() {
    local file="$1" begin="$2" end="$3" b=0 e=0
    [[ -f $file ]] || { printf 'none'; return 0; }
    # -e: defensive — a marker starting with a dash would read as an option
    # (today's markers start with "#" and "  //").
    if grep -qxF -e "$begin" "$file"; then b=1; fi
    if grep -qxF -e "$end" "$file"; then e=1; fi
    if (( b && e )); then printf 'both'
    elif (( b || e )); then printf 'half'
    else printf 'none'; fi
}

# Put the hyprconf-managed block of $1 at the contents of $2, preserving
# everything outside the markers WHERE IT IS. An existing block is replaced
# in place: a line the user added after the end marker stays after it — they
# wrote it to run after the block (after Oh My Zsh, the theme and
# zsh-syntax-highlighting, which zsh/zshrc.block sources last for a reason),
# and stripping the block and re-appending it would silently move that line
# above the block on the hook's next run. A file with no block yet gets it
# appended after one blank line, trailing blank lines dropped first so a
# re-run cannot accumulate whitespace ahead of it. Byte-stable across
# repeated runs. The one block written is the zshrc one, so the markers are
# the '#'-comment pair.
#
# Both preservation promises hold only over a COMPLETE pair: with one marker
# line hand-removed the file is refused untouched (managed_block_state), not
# rewritten — see there for what the alternative costs.
write_managed_block() {
    local file="$1" block="$2" begin="# >>> hyprconf >>>" end="# <<< hyprconf <<<" tmp kept state
    touch "$file"
    state="$(managed_block_state "$file" "$begin" "$end")"
    if [[ $state == half ]]; then
        warn "$file has one hyprconf marker line but not the other — left untouched;" \
             "put the missing '$begin' / '$end' line back (or delete the odd one) and re-run"
        return 0
    fi
    if [[ $state == both ]]; then
        tmp="$(mktemp)"
        # The first block is replaced at its own position; any further pair
        # (never written by this installer) is dropped, so one block remains.
        # The block path goes through the ENVIRONMENT, never `-v blk=`: awk
        # applies POSIX escape processing to a -v assignment, so a checkout
        # under a path with a backslash (~/my\stuff — HYPRCONF_DIR is the
        # user's to choose) names a file getline cannot open, and every
        # marker line is consumed with nothing printed in its place: the
        # block and both markers gone, at exit 0. ENVIRON is POSIX awk and
        # takes the bytes as they are. Same class of hazard as HERE_SED.
        blk="$block" awk -v b="$begin" -v e="$end" '
            $0 == b {
                if (!done) {
                    while ((getline line < ENVIRON["blk"]) > 0) print line
                    close(ENVIRON["blk"])
                }
                done = 1; skip = 1; next
            }
            $0 == e { skip = 0; next }
            skip { next }
            { print }
        ' "$file" > "$tmp"
        cat "$tmp" > "$file"
        rm -f "$tmp"
        return 0
    fi
    kept="$(cat "$file")"   # command substitution strips trailing newlines
    {
        [[ -z $kept ]] || printf '%s\n\n' "$kept"
        cat "$block"
    } > "$file"
}

# Remove a managed block from $1 (markers $2/$3), preserving everything else.
# Returns 1 without touching the file on a half marker pair, which is the
# caller's signal to leave the whole file alone (managed_block_state).
strip_managed_block() {
    local file="$1" begin="$2" end="$3" tmp state
    state="$(managed_block_state "$file" "$begin" "$end")"
    [[ $state == half ]] && return 1
    [[ $state == both ]] || return 0
    tmp="$(mktemp)"
    awk -v b="$begin" -v e="$end" '
        $0 == b { skip = 1; next }
        $0 == e { skip = 0; next }
        skip { next }
        { print }
    ' "$file" > "$tmp"
    # Trailing blank lines go with the block: the command substitution
    # strips every trailing newline and printf puts exactly one back. That
    # is what stage_menu — the one caller — needs, because its own awk drops
    # them too (see its comment), so the block it writes on the FIRST run is
    # already what a re-run over the stripped file produces
    # (test_menu_block_is_byte_stable_from_the_first_run_after_trailing_blank_lines).
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
    local stock="$OMARCHY_PATH/config/hypr/$name"
    # The last template this installer saw. Comparing against the INSTALLED
    # one alone recognises a clobber only until Omarchy ships the next
    # version of that file — and omarchy-update upgrades the package BEFORE
    # it runs the post-update hook (bin/omarchy-update: omarchy-update-
    # system-pkgs, then omarchy-hook post-update; 4.0.2-1). So a file
    # refreshed at template A and not repaired the same day read as a real
    # user edit the moment B landed: no repair, no warning, every hyprconf
    # hotkey gone, and every later hyprsync dead at the fast-forward pull —
    # permanently, because the guard could never fire again.
    local cached="$HOME/.local/state/hyprconf/stock/$name"
    [[ -f $ours && -f $stock ]] || return 0
    local matched=""
    if cmp -s "$ours" "$stock"; then
        matched="$stock"
    elif [[ -f $cached ]] && cmp -s "$ours" "$cached"; then
        matched="$cached"
    fi
    # Remember what the template looks like NOW, for the run after the next
    # Omarchy release replaces it. Written only when it changed, so a re-run
    # stays byte-stable. The whole directory goes with the rest of the state
    # (README > Reverting to stock).
    if ! cmp -s "$stock" "$cached" 2>/dev/null; then
        mkdir -p "${cached%/*}"
        cp "$stock" "$cached"
    fi
    [[ -n $matched ]] || return 0
    if git -C "$HERE" checkout -q -- "hypr/$name" 2>/dev/null && ! cmp -s "$ours" "$matched"; then
        warn "hypr/$name in the checkout had been replaced by Omarchy's stock template" \
             "(omarchy refresh writes through the symlink) — restored it from git"
    else
        warn "hypr/$name in the checkout is Omarchy's stock template and could not be" \
             "restored from git — see: git -C $HERE status"
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
    # First, undo any `omarchy refresh` that landed on the checkout through
    # the override symlinks (restore_clobbered_override). A hypr/*.lua that
    # is Omarchy's stock template byte for byte is a dirty tracked file, and
    # `git pull --ff-only` refuses to merge over a dirty file upstream also
    # changed ("Your local changes to the following files would be
    # overwritten by merge") — about a file the user never edited, and on
    # every re-run, because the guard's other callers (stage_hotkeys,
    # stage_looknfeel) come after this stage. A no-op on anything but the
    # template.
    #
    # The set is DERIVED, never re-listed: a hand list here would sit 450
    # lines from the link_hypr_override calls that decide it, with nothing
    # coupling the two, and a fourth override added without editing it would
    # block every later pull. The monitor presets fall out on their own —
    # restore_clobbered_override returns at its [[ -f $stock ]] test, since
    # Omarchy ships no config/hypr template for them. An untracked
    # look-alike is skipped: `git checkout --` can restore nothing for it,
    # so all the guard could do is warn, once per run, forever.
    local path name
    for path in "$HERE"/hypr/*.lua; do
        [[ -f $path ]] || continue
        name="${path##*/}"
        git -C "$HERE" ls-files --error-unmatch -- "hypr/$name" >/dev/null 2>&1 || continue
        restore_clobbered_override "$name"
    done
    if ! git -C "$HERE" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
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

# Firefox through Omarchy's own installer, plus the system Firefox policy.
#
# `omarchy-install-browser firefox` (bin/omarchy-install-browser, the
# `firefox)` case, Omarchy 4.0.2-1) is omarchy-pkg-add firefox, its own
# policies.json into /usr/lib/firefox/distribution/ through
# install/helpers/browser-policy.sh's browser_policy_setup_firefox_distribution
# (the directory made root-owned 0755, files not root's purged, the policy
# `install -m 644 -o root -g root`, all as root), and MOZ_ENABLE_WAYLAND=1 in
# ~/.config/environment.d/ — every step idempotent, and nothing is launched.
# Its browser-policy migration (migrations/1787515927.sh) hardens the same
# directory and never touches /etc/firefox, where the file below lives. Run
# only when omarchy-pkg-present firefox fails.
#
# The policy — telemetry off, tracking protection on, uBlock Origin and
# Proton Pass force-installed, DuckDuckGo the default engine, and the UI
# settings this config carries (compact density, vertical tabs, a bare
# Firefox Home, DRM playback on) — lives at /etc/firefox/policies/
# policies.json: Firefox reads enterprise policies only from root-owned
# paths, and that one takes precedence over the distribution/ file Omarchy
# writes, which would shadow Omarchy's own prefs (VA-API, fractional
# scaling, overscroll). So the file installed is a superset: Omarchy's
# $OMARCHY_PATH/default/firefox/policies.json merged UNDER
# infra/firefox/policies.json (jq `*` is a recursive object merge — a shared
# "Preferences" keeps both sides, and ours wins on the same key), written
# only when the merged bytes differ. Every captured pref is a Status
# "default": it seeds a profile and the user can still change it — the
# toolbar arrangement included, a seeded browser.uiCustomization.state that
# a fresh profile's first window is built from (CLAUDE.md › Known quirks for
# the semantics). Firefox silently drops any pref outside its own allowlist,
# so tests/unit/test_firefox.py pins that list — the one setting no policy
# can make stick (the find bar's Highlight All, which that allowlist
# rejects) is left to the user, in README › Firefox settings. One of the
# overlay's two writes outside $HOME (the other is the Keychron udev rule),
# hence behind the --no-packages gate with the other sudo work; it bows out
# when no terminal can take sudo's password
# prompt — the post-update hook runs non-interactively inside omarchy-update,
# where a hung prompt would stall the whole update.
stage_firefox() {
    log "Firefox: Omarchy's installer, plus hyprconf's policy"
    local src="$HERE/infra/firefox/policies.json"
    local dst="$_HYPRCONF_FIREFOX_POLICIES/policies.json"
    local theirs="$OMARCHY_PATH/default/firefox/policies.json"
    local merged
    merged="$(mktemp)"
    local -a layers=()
    [[ -f $theirs ]] && layers+=("$theirs")
    layers+=("$src")
    if ! jq -s 'reduce .[] as $layer ({}; . * $layer)' "${layers[@]}" > "$merged" 2>/dev/null; then
        rm -f "$merged"
        warn "jq could not merge the Firefox policies — will retry on the next run"
        return 0
    fi

    local install_firefox=0 install_policy=0
    omarchy-pkg-present firefox || install_firefox=1
    [[ -f $dst ]] && cmp -s "$merged" "$dst" || install_policy=1
    if (( ! install_firefox && ! install_policy )); then
        rm -f "$merged"
        info "installed; policy current at $dst"
        return 0
    fi
    if [[ ! -t 0 && -z $_HYPRCONF_ASSUME_TTY ]]; then
        rm -f "$merged"
        warn "no terminal for sudo — run \`bash install.sh\` from a terminal to install Firefox and its policy"
        return 0
    fi
    if (( install_firefox )); then
        info "installing through omarchy-install-browser firefox (Omarchy's own flow: the package, its prefs under /usr/lib/firefox/distribution, MOZ_ENABLE_WAYLAND)"
        if ! omarchy-install-browser firefox; then
            rm -f "$merged"
            warn "omarchy-install-browser firefox failed — retry with: omarchy install browser firefox"
            return 0
        fi
    fi
    if (( install_policy )); then
        if sudo install -Dm644 "$merged" "$dst"; then
            info "policy installed at $dst (Omarchy's prefs + hyprconf's)"
        else
            warn "could not install the Firefox policy — skipping"
        fi
    fi
    rm -f "$merged"
}

# VS Code through Omarchy's own installer. omarchy-install-editor-vscode
# (Omarchy 4.0.0-1) is omarchy-pkg-add visual-studio-code-bin — from
# Omarchy's own [omarchy] pacman repository, never the AUR — then
# ~/.vscode/argv.json (gnome-libsecret), update.mode none in
# ~/.config/Code/User/settings.json, omarchy-theme-set-vscode, and one
# `setsid uwsm-app -- gtk-launch code`: it opens VS Code once when it is
# done, by design, and exits 0 whatever happened (no set -e; the launch is
# backgrounded), so the result is read back with omarchy-pkg-present. Behind
# the --no-packages gate with the other sudo work; bows out without a
# terminal. Not set-once: like every package, VS Code is ensured present, so
# a later interactive run that finds it gone installs it again.
#
# Nothing is removed first. Arch's `code` (Code - OSS) conflicts with the
# package (pacman -Si visual-studio-code-bin: Conflicts With: code), but a
# stock Omarchy never installs it — nothing in install/*.packages, bin/ or
# migrations/ adds it (4.0.2-1) — so on a box that has it the user put it
# there: theirs to drop, never this overlay's. The conflict then fails inside
# Omarchy's installer — omarchy-pkg-add is `sudo pacman -S --noconfirm
# --needed` (bin/omarchy-pkg-add:12), which pacman refuses, and
# omarchy-install-editor-vscode carries on and exits 0 (no set -e) — and the
# read-back below warns with the retry command.
stage_editor() {
    log "VS Code: Omarchy's installer"
    if omarchy-pkg-present visual-studio-code-bin; then
        info "already installed"
        return 0
    fi
    if [[ ! -t 0 && -z $_HYPRCONF_ASSUME_TTY ]]; then
        warn "no terminal for sudo — run \`bash install.sh\` from a terminal to install VS Code"
        return 0
    fi
    info "installing through omarchy-install-editor-vscode — Omarchy's own flow, which opens VS Code once when it is done"
    omarchy-install-editor-vscode || true
    if omarchy-pkg-present visual-studio-code-bin; then
        info "installed"
    else
        warn "visual-studio-code-bin did not install — retry with: omarchy install editor vscode"
    fi
}

# Keychron / Lemokey keyboards and mice over WebHID. The web launcher at
# launcher.keychron.com talks to the board's vendor-defined HID interface, and
# a hidraw node is 0600 root:root by default (/usr/lib/udev/rules.d/
# 50-udev-default.rules sets no MODE for hidraw), so the browser cannot open
# it. The rule tags the node uaccess and systemd's 73-seat-late.rules turns
# that into an ACL for the active session — see infra/udev/70-keychron.rules
# for why the match is vendor-only and why the filename must sort at 70-.
#
# Omarchy has no command for this — `omarchy commands --json` has no udev
# route — but it ships the shape itself: install/hardware/framework/
# qmk-hid.sh copies default/udev/framework16-qmk-hid.rules into
# /etc/udev/rules.d for the Framework 16's QMK interface. This is that same
# pattern with hyprconf's vendors, written the way stage_firefox writes its
# policy: compared first, so a steady-state re-run never reaches sudo.
#
# Not gated on a Keychron being plugged in: a udev rule is for the device you
# attach next as much as the one attached now.
stage_keychron() {
    log "Keychron / Lemokey: hidraw access for the web launcher"
    local src="$HERE/infra/udev/70-keychron.rules"
    local dst="$_HYPRCONF_UDEV_RULES/70-keychron.rules"
    if [[ -f $dst ]] && cmp -s "$src" "$dst"; then
        info "rule current at $dst"
        return 0
    fi
    if [[ ! -t 0 && -z $_HYPRCONF_ASSUME_TTY ]]; then
        warn "no terminal for sudo — run \`bash install.sh\` from a terminal to install the Keychron udev rule"
        return 0
    fi
    if ! sudo install -Dm644 "$src" "$dst"; then
        warn "could not install the Keychron udev rule — skipping"
        return 0
    fi
    info "rule installed at $dst (Keychron 0x3434, Lemokey 0x362d)"
    # Apply it to what is already plugged in; without this the ACL arrives
    # only on the next re-plug or reboot.
    if sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw; then
        info "applied to connected devices — reload the launcher tab"
    else
        warn "rule installed but not applied — re-plug the board or reboot"
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
    # omarchy-theme-update skips a link (`[[ ! -L ${dir%/} ]]` before its
    # `git pull`), so `omarchy theme update` never pulls into the checkout.
    ln -sfn "$HERE/themes/dracula" "$link"

    # Installed, never activated. Which theme is active is the user's choice,
    # and an install — or any of the re-applies that follow every Omarchy
    # update — must not take it away from them. (`omarchy-theme-set` is no
    # cheap no-op either: it rebuilds the staged theme, swaps symlinks and fans
    # out ~15 restart/retint commands.)
    info "available in Omarchy's theme menu (SUPER+SHIFT+CTRL+SPACE) — the active theme is left as it is"
}

# Omarchy's screensaver starts after 150 s (config/omarchy/shell.json,
# idle.screensaver); the overlay's timeout is 900 s. Set
# ONCE — shell.json is the user's file (Omarchy's manual, Dotfiles), and a
# timeout changed later must stay theirs. Omarchy 4.0.0-1 ships no command
# for these keys (`omarchy commands --json` has no route for the timeout and
# `grep -Rl idle.screensaver /usr/share/omarchy/bin` finds nothing;
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
    local json="$HOME/.config/omarchy/shell.json" src
    src="$json"
    [[ -s $json ]] || src="$OMARCHY_PATH/config/omarchy/shell.json"
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
    omarchy-shell shell reloadConfig >/dev/null 2>&1 || true
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
# invisible.
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
# update.
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
    mkdir -p "$HOME/.config/hypr"
    # The hotkey tools themselves (bin/hyprconf-monitor-preset, bin/hyprconf-
    # gaps) are PATH commands: stage_bin installs them and bindings.lua binds
    # them by name, the way Omarchy binds its own.
    link_hypr_override bindings.lua
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
    # Presets only — seeded, never applied. hyprconf-monitor-preset (stage_bin
    # puts it on PATH) copies the chosen one into Omarchy's Hyprland toggles
    # directory, which loads after ~/.config/hypr/monitors.lua and wins, so
    # Omarchy's own monitors.lua is never replaced. Each preset carries
    # hyprconf's workspace-to-monitor rules for that layout, which is why they
    # travel as whole files. Only bedroom and kitchen have hotkeys; the third
    # is `hyprconf-monitor-preset laptop`.
    #
    # SEEDED, not synced. A preset is a description of one machine's physical
    # desk — outputs, modes, scales — so once it exists it belongs to that
    # machine, and hyprconf-monitor-preset's own comment promises edits
    # survive re-selecting a preset. Copying over it on every run would break
    # that promise silently, and the post-update hook re-runs this after every
    # Omarchy update. Delete a preset to have it re-seeded from the repo.
    local f
    for f in pcMonitors.bedroom.lua pcMonitors.kitchen.lua laptopMonitors.lua; do
        [[ -e $HOME/.config/hypr/$f ]] && continue
        install -m 644 "$HERE/hypr/$f" "$HOME/.config/hypr/$f"
        info "seeded $f"
    done
}

stage_fastfetch() {
    log "fastfetch greeting"
    # Omarchy's own fastfetch layout is the system-wide default,
    # /etc/fastfetch/config.jsonc (owned by omarchy-settings 4.0.0-1) — and
    # fastfetch reads ~/.config/fastfetch/config.jsonc first, its documented
    # per-user override, so hyprconf's layout is linked there and Omarchy's
    # file is left untouched. A user config already at that path is backed
    # up first. ~/.zshrc runs it as the shell greeting.
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
    local f dst
    # Every bin/hyprconf-* file; a new tool is one file in bin/. @HYPRCONF_DIR@
    # is substituted the way the hooks get it, for the tools that need the
    # checkout (the Python lib). Rendered beside the target and mv'd over it:
    # the rename is atomic, so a hotkey exec'ing one of these mid-install
    # runs old bytes or new, never a truncated prefix (a running tool keeps
    # its old inode); cmp keeps the steady-state re-run write-free, matching
    # the byte-stable posture of the other stages. The bar's feeders are not
    # here: they ship inside plugins/hyprconf-resources and land with it.
    for f in "$HERE"/bin/hyprconf-*; do
        dst="$HOME/.local/bin/${f##*/}"
        sed "s|@HYPRCONF_DIR@|$HERE_SED|g" "$f" > "$dst.hyprconf-tmp"
        chmod 755 "$dst.hyprconf-tmp"
        if cmp -s "$dst.hyprconf-tmp" "$dst" 2>/dev/null; then
            rm -f "$dst.hyprconf-tmp"
            chmod 755 "$dst"
        else
            mv -f "$dst.hyprconf-tmp" "$dst"
        fi
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
# default/bash/envs appends it).
stage_menu() {
    log "Omarchy menu: Proton VPN installer (Install > Service)"
    local file="$HOME/.config/omarchy/extensions/omarchy-menu.jsonc"
    local template="$OMARCHY_PATH/config/omarchy/extensions/omarchy-menu.jsonc"
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
    # A half marker pair costs this file more than the tail: with the end
    # marker gone the strip eats the outer closing brace too, the bottom-up
    # scan below then latches onto a NESTED brace instead of reaching its
    # exit-3 guard, and the row lands inside the user's own object. The
    # result is invalid JSON, and Omarchy swallows that whole — MenuModel.js
    # parseMenuJsonc returns [] on a JSON.parse throw (4.0.2-1) — so the
    # user loses their ENTIRE menu, not one row.
    if ! strip_managed_block "$tmp" "$begin" "$end"; then
        rm -f "$tmp"
        warn "$file has one hyprconf marker line but not the other — left untouched;" \
             "put the missing marker line back (or delete the odd one) and re-run"
        return 0
    fi
    local rc=0
    awk -v b="$begin" -v e="$end" -v entry="$entry" '
        { lines[NR] = $0 }
        END {
            # The parser also accepts `{ "items": { … } }` and then reads
            # ONLY that object (MenuModel.js: `parsed.items` when it is a
            # non-array object, else `parsed`). The block goes before the
            # LAST brace line, which in that shape is the outer one — the
            # row would sit outside items, ignored for good, while every
            # re-run found the file current. Refused instead.
            #
            # The wrapper is a JSON fact, not a line fact: `"items"`, its
            # colon and its `{` may each sit on a line of their own. So the
            # test runs over the joined file, where [[:space:]] spans the
            # newlines too; the leading "\n" is what makes the anchor hold
            # for the first line as well.
            joined = "\n"
            for (i = 1; i <= NR; i++) joined = joined lines[i] "\n"
            if (joined ~ /\n[[:space:]]*\{?[[:space:]]*"items"[[:space:]]*:[[:space:]]*\{/) exit 4
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
        }' "$tmp" > "$tmp.new" || rc=$?
    if (( rc )); then
        rm -f "$tmp" "$tmp.new"
        if (( rc == 4 )); then
            warn "$file wraps its rows in an \"items\" object, where a block before the closing brace is never read — add the Proton VPN row by hand, inside it"
        else
            warn "$file has no closing-brace line to put the hyprconf block before — add the Proton VPN row by hand"
        fi
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

# Placement comes from the manifest: barWidget.defaultSection = "right",
# which the shell honours on an enable with no explicit placement
# (shell/services/PluginRegistry.qml defaultBarWidgetSection, 4.0.0-1;
# omarchy-plugin-validate checks the value) — the same seam the
# active-window copy uses, so no --section argument here.
stage_bar_plugin() {
    log "Resource-usage bar widget (hyprconf.resources)"
    sync_plugin_dir hyprconf-resources hyprconf.resources
    enable_plugin_once hyprconf.resources resources-applied
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
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
    for (( _attempt = 0; _attempt < _HYPRCONF_PLUGIN_WAIT; _attempt++ )); do
        list="$(omarchy-plugin-list --json 2>/dev/null)" || break
        jq -e --arg id "$id" 'any(.[]; .id == $id)' <<<"$list" >/dev/null 2>&1 && break
        sleep 0.05
    done
    omarchy-plugin-enable "$id" >/dev/null 2>&1
}

# Make the running shell pick changed plugin files up: `omarchy-shell shell
# rescanPlugins` re-walks the plugin dirs and hot-reloads plugin code
# (shell/README.md, IPC table; shell.qml reloadPlugins unloads panels,
# services and widgets and loads them again) — the call omarchy-plugin-update
# makes after a fast-forward (bin/omarchy-plugin-update:131). omarchy-shell
# exits 1 when no shell answers, and only then is the shell restarted, which
# is how one comes back; with no session at all (a TTY run) both fail, and
# harmlessly.
reload_plugins() {
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 ||
        omarchy-restart-shell >/dev/null 2>&1 || true
}

# Every path under $1 as "<mode> <relative path>", sorted — the half of a
# directory comparison `diff -rq` does not make. -mindepth 1 leaves the
# directory itself out: the installed one carries mktemp -d's 0700, not the
# checkout's, and never healing that is the point (it is where a plugin dir
# is staged from), while a difference there would re-sync on every run.
dir_modes() {
    (cd "$1" && find . -mindepth 1 -printf '%m %p\n' | sort)
}

# Install (or refresh) one of the overlay's own bar-widget plugins, shipped
# in plugins/<src>, as ~/.config/omarchy/plugins/<id>. SYNCED on every run —
# a `git pull` updates the widget the way it updates everything else the
# overlay links out of the checkout. Staged in a sibling temp dir and moved
# into place, the way omarchy-plugin-clone lands a clone (mktemp -d under the
# plugins dir, cp -aL, mv), so the shell's directory watch never scans a
# half-copied plugin; then the shell rescans.
#
# Each plugin folder is also publishable on its own (README.md inside it),
# and `omarchy plugin add <url>` lands the same id as a git checkout
# (bin/omarchy-plugin-add: git clone, omarchy-plugin-validate, mv to
# plugins/<id>; 4.0.2-1). That checkout is Omarchy's to manage — `omarchy
# plugin update` fast-forwards it and refuses a non-git folder
# (bin/omarchy-plugin-update: `[[ -d $PLUGINS_DIR/$id/.git ]] || fail`) —
# so it is left alone: the diff below would otherwise see its .git and
# replace the checkout, uncommitted edits included. The other order is
# safe on its own: with the overlay's copy in place, omarchy-plugin-add
# refuses a duplicate id.
#
# The freshness gate is bytes AND modes. `diff -rq` is mode-blind, so an
# installed feeder that lost its exec bit (an rsync or cloud restore of
# ~/.config without permissions, a clone git could not mark 100755) was
# never re-synced: Widget.qml execs it directly as an argv list, no shell,
# so it fails with EACCES and the widget freezes at "0%" — and `chmod +x`
# in the checkout plus a re-run did nothing, because the bytes still
# matched. cp -aL below already puts the checkout's modes back.
sync_plugin_dir() {
    local src="$HERE/plugins/$1" id="$2"
    local dir="$HOME/.config/omarchy/plugins/$id"
    if [[ -d $dir/.git ]]; then
        info "$id is an \`omarchy plugin add\` checkout — left to: omarchy plugin update $id"
        return 0
    fi
    if [[ -d $dir ]] && diff -rq "$src" "$dir" >/dev/null 2>&1 &&
        [[ "$(dir_modes "$src")" == "$(dir_modes "$dir")" ]]; then
        return 0
    fi
    mkdir -p "$HOME/.config/omarchy/plugins"
    local stage
    stage="$(mktemp -d "$HOME/.config/omarchy/plugins/.hyprconf.XXXXXX")"
    cp -aL "$src/." "$stage/"
    rm -rf "$dir"
    mv "$stage" "$dir"
    reload_plugins
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
    if [[ -e $marker ]]; then
        info "enabled once already — \`omarchy plugin disable $id\` sticks"
        return 0
    fi
    if activate_plugin_copy "$id"; then
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

# The bar clock, ticking seconds: plugins/hyprconf-clock is Omarchy's own
# clock widget (BarWidget.qml + Model.js, Omarchy 4.0.2-1 — MIT, the NOTICE
# beside them) with two deltas its header names, clonedFrom omarchy.clock so
# the shell swaps it into the stock slot. The stock widget cannot tick
# seconds: omarchy.clock samples SystemClock at Minutes precision
# (shell/plugins/panels/clock/BarWidget.qml), so a seconds format would sit
# frozen 59 s of every minute. Shipped and SYNCED on every run like the other
# three — an install-time copy of the stock plugin, made once, lagged the
# 4.0.2 release's hardening of its own Panel.qml by eight lines with nothing
# to refresh it (omarchy-plugin-update refuses a non-git folder). Only the
# user's choices are set ONCE, behind the marker: the enable, hyprconf's
# format — 12-hour with seconds and AM/PM, "hh:mm:ss AP" in the
# Qt.formatDateTime tokens the widget feeds its format setting to — and the
# centre anchor, for the same reason as the font and the default apps: the
# post-update hook re-runs this installer, and a clock the user later
# reformatted (right-click cycles formats; `omarchy bar set`) must stay
# theirs. The sync comes first so the shell never loads a stale build.
stage_clock() {
    log "Bar clock: hh:mm:ss AP (hyprconf.clock)"
    local id="hyprconf.clock"
    sync_plugin_dir hyprconf-clock "$id"
    local marker="$HOME/.local/state/hyprconf/clock-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the clock is yours now"
        return 0
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

    mkdir -p "$(dirname "$marker")"
    : > "$marker"
    info "seconds tick via the $id widget (back to stock with: omarchy plugin disable $id)"
}

# Only ACTIVE workspaces on the bar, on two lines, Pac-Man on the focused
# one. The stock widget hardcodes pills 1-5 whether they exist or not, caps
# ids at 10 (bar/widgets/Workspaces.qml, workspaceIds(): "var ids = [1, 2, 3,
# 4, 5]"), and honors NO settings — `omarchy bar set omarchy.workspaces …`
# writes keys the widget never reads — so the overlay ships its own widget
# (plugins/hyprconf-workspaces, header comment there) as a clonedFrom copy:
# the shell swaps it into the stock widget's slot and routes the stock IPC to
# it, and `omarchy plugin disable hyprconf.workspaces` restores the stock
# widget.
stage_workspaces() {
    log "Bar workspaces: only active workspaces, two lines (hyprconf.workspaces)"
    sync_plugin_dir hyprconf-workspaces hyprconf.workspaces
    enable_plugin_once hyprconf.workspaces workspaces-applied
}

# The focused window's title beside the workspaces, on TWO lines. Omarchy's
# stock omarchy.active-window widget is the same thing on one line (elided
# title, tooltip with the full one, click focuses, middle- or right-click closes) and
# reads one setting, maxWidth, so the two-line version is the overlay's own
# copy (plugins/hyprconf-active-window, header comment there): clonedFrom the
# stock widget, so the shell swaps it into the stock widget's slot and routes
# the stock IPC to it, and `omarchy plugin disable hyprconf.active-window`
# restores stock. Synced every run,
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

# clone_pinned <url> <dir> <sha> <name>: the named commit and only it —
# cloned without checkout, the exact sha fetched shallow (GitHub serves
# unadvertised reachable objects by full sha), checked out detached. A dir
# already at the pin costs nothing and touches no network; one at any other
# commit (an install from before the pins, or a bumped pin) is moved to it,
# fetching from the pinned URL so a stray origin cannot answer. EVERY network
# step is timeout-bounded — the blob download happens at the checkout under
# --filter=blob:none, not the fetch (the unbounded pull this replaces once
# held an omarchy-update for minutes). Non-fatal throughout; a failed MOVE
# keeps the existing checkout in service (return 0: the dir is usable, just
# not yet at the pin), a failed fresh CLONE leaves nothing to use (return 1).
clone_pinned() {
    local url=$1 dir=$2 sha=$3 name=$4
    if [[ -d $dir ]]; then
        if ! git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
            warn "$name at $dir is not a git checkout — leaving it as it is (move it aside to let the pin re-clone)"
            return 0
        fi
        [[ $(git -C "$dir" rev-parse HEAD 2>/dev/null) == "$sha" ]] && return 0
        info "Moving $name to its pinned commit"
        { timeout 300 git -C "$dir" fetch --depth=1 "$url" "$sha" >/dev/null 2>&1 &&
            timeout 300 git -C "$dir" checkout --detach -q FETCH_HEAD; } ||
            warn "could not move $name to its pin — the current checkout stays in use; will retry on the next run"
        return 0
    fi
    info "Installing $name (pinned)"
    { timeout 300 git clone --no-checkout --filter=blob:none "$url" "$dir" >/dev/null 2>&1 &&
        timeout 300 git -C "$dir" fetch --depth=1 "$url" "$sha" >/dev/null 2>&1 &&
        timeout 300 git -C "$dir" checkout --detach -q FETCH_HEAD; } ||
        { rm -rf "$dir"; warn "could not clone $name — will retry on the next run"; return 1; }
}

stage_shell() {
    log "Shell: zsh + powerlevel10k in the terminal"
    # Deliberately NO chsh. The login shell stays bash, so Omarchy's rc chain,
    # its aliases/functions/completions, uwsm, SSH and scripts are untouched.
    # kitty is what launches zsh (see stage_kitty_include), and .zshrc sources
    # Omarchy's own env/alias files so its updates keep flowing through.
    [[ -n $_HYPRCONF_ZSH ]] || { warn "zsh not installed — skipping"; return 0; }

    # Third-party shell code, PINNED: both repos are checked out at exactly
    # the commits below and never auto-updated. Their code runs in every
    # interactive zsh, and the old per-apply `git pull` was a silent
    # auto-propagation channel from two upstream HEADs into every box on
    # every omarchy-update (the post-update hook runs this stage with output
    # discarded) — an upstream or maintainer-account compromise would have
    # shipped itself. Bumping a pin is a deliberate commit through the
    # publish gates (zsh/zshrc.block's `zstyle :omz:update mode disabled`
    # holds the other half: the updater shipping inside the pinned code).
    # Clone/fetch stay bounded and non-fatal, as before:
    # a dead network must not stall an Omarchy update, and the rest of the
    # stage is skipped so .zshrc never names a theme that is not there.
    # Pins verified 2026-09-01 (upstream HEADs, reviewed):
    local omz_pin=9112b53fa8b5ab556c7c893aa8be8a247ac512a0
    local p10k_pin=3308262dfbd743b6e1d3956a2b5572f7a049d692
    local p10k="$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
    clone_pinned https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh" "$omz_pin" "Oh My Zsh" || return 0
    mkdir -p "$(dirname "$p10k")"
    clone_pinned https://github.com/romkatv/powerlevel10k.git "$p10k" "$p10k_pin" "powerlevel10k" || return 0

    ln -sfn "$HERE/zsh/.p10k.zsh" "$HOME/.p10k.zsh"
    write_managed_block "$HOME/.zshrc" "$HERE/zsh/zshrc.block"
}

# Every hook the overlay ships, hooks/<type>.d/<file>, into the matching
# ~/.config/omarchy/hooks/<type>.d/ — the directories omarchy-hook runs
# (post-update from omarchy-update, theme-set from omarchy-theme-set) —
# through Omarchy's own `omarchy-hook-install <type> <file>` (4.0.0-1:
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

# hyprconf's theme templates into Omarchy's user template directory,
# ~/.config/omarchy/themed/: every <name>.tpl there is rendered by
# omarchy-theme-set-templates on each theme set — {{ background }},
# {{ foreground }}, {{ accent }}, {{ color0..15 }} and the rest of the list in
# config/omarchy/themed/alacritty.toml.tpl.sample — into
# ~/.local/state/omarchy/current/theme/<name>, user templates ahead of
# default/themed (4.0.0-1). Copied when the bytes differ. The render for the
# theme active RIGHT NOW is Omarchy's own `omarchy-theme-refresh` ("Refresh
# the current theme from its templates": omarchy-theme-set of the current
# theme.name with OMARCHY_THEME_SKIP_BACKGROUND=1, so the wallpaper stays) —
# the templates renderer on its own writes only into theme-set's next-theme
# staging dir and is called from nowhere else (the omarchy-theme-set-templates
# call under omarchy-theme-set's flock, 4.0.2-1).
# Run only when a template changed or its render is missing, so the
# post-update hook's re-runs cost nothing; with no active theme yet the next
# `omarchy theme set` renders it.
stage_themed() {
    log "Theme templates (~/.config/omarchy/themed)"
    local dir="$HOME/.config/omarchy/themed"
    local theme="$HOME/.local/state/omarchy/current/theme"
    local tpl name changed=0 unrendered=0
    for tpl in "$HERE"/themed/*.tpl; do
        [[ -f $tpl ]] || continue
        name="${tpl##*/}"
        if [[ ! -f $dir/$name ]] || ! cmp -s "$tpl" "$dir/$name"; then
            mkdir -p "$dir"
            install -m 644 "$tpl" "$dir/$name"
            changed=1
            info "installed $name"
        fi
        [[ -f $theme/${name%.tpl} ]] || unrendered=1
    done
    if (( ! changed && ! unrendered )); then
        info "already current and rendered"
        return 0
    fi
    if [[ ! -r $theme.name ]]; then
        info "no active theme yet — rendered on the next omarchy theme set"
        return 0
    fi
    command -v omarchy-theme-refresh >/dev/null 2>&1 || {
        warn "omarchy-theme-refresh not found — rendered on the next omarchy theme set"
        return 0
    }
    info "rendering through omarchy-theme-refresh (Omarchy's own re-render of the current theme; the wallpaper is kept)"
    omarchy-theme-refresh >/dev/null 2>&1 ||
        warn "omarchy-theme-refresh failed — rendered on the next omarchy theme set"
}

# Extend the ACTIVE theme to Firefox now, not only on the next `omarchy
# theme set`: the theme-set hook just installed is run once, the way
# omarchy-theme-set runs it (`omarchy-hook theme-set <name>` after its own
# fan-out — where VS Code is themed, by omarchy-theme-set-vscode). Not
# set-once — the hook is idempotent and cheap, and a re-run keeps Firefox in
# step with a theme switched while the overlay was not installed.
stage_theme_apps() {
    log "Theme into Firefox (theme-set hook)"
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
    [[ -d $HERE/hypr && -f $HERE/packages ]] || bootstrap "${orig_args[@]}"
    show_banner
    preflight
    if (( do_pull )); then stage_pull; fi
    # Everything that needs sudo: packages, Firefox (+ the policy), VS Code,
    # the Keychron udev rule. stage_keychron runs last of the four so the
    # first `sudo install` of a run is still the Firefox policy's.
    if (( do_packages )); then stage_packages; stage_firefox; stage_editor; stage_keychron; fi
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
    stage_shell
    stage_hooks
    # Before stage_theme_apps: its hook wants the templates rendered.
    stage_themed
    stage_theme_apps
    hyprctl reload >/dev/null 2>&1 || true
    if (( do_update )); then stage_update; fi

    log "Done. SUPER+D still opens Omarchy's menu; the login shell is still bash."
}

main
