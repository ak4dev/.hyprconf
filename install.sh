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
# `include`). The one privileged step here is installing packages, through
# Omarchy's own `omarchy-pkg-add`, and --no-packages skips it — so the
# post-update hook never needs sudo. That flag also exports HYPRCONF_NO_SUDO,
# which every module reads: modules/firefox (Firefox and the system policy,
# the overlay's write outside $HOME), modules/vscode, modules/font and
# modules/keychron all bow out of their own root work behind it.
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
  --no-packages   Skip everything that needs sudo: the package list here, and
                  every module's own root work. Exported to the modules as
                  HYPRCONF_NO_SUDO, which each one honours itself.
  -h, --help      Show this help.

With no options: apply every stage once, without pulling or updating.
USAGE
}

while (( $# )); do
    case "$1" in
        --sync)        do_pull=1; do_update=1 ;;
        --no-update)   no_update=1 ;;
        # Exported, not just local: every modules/*/install reads it and
        # bows out of its own sudo work with one pointer line and exit 0.
        --no-packages) do_packages=0; export HYPRCONF_NO_SUDO=1 ;;
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
    # The overlay writes the invoking user's $HOME and asks for sudo itself —
    # in stage_packages here, and in each module that does its own root work
    # behind HYPRCONF_NO_SUDO; run under sudo it half-installs into /root
    # (env_reset sets HOME) and the curl|bash habit of prefixing sudo is the
    # dangerous one. No seam: the suite runs unprivileged, CI included.
    if ((EUID == 0)); then
        die "run as your regular user — install.sh asks for sudo itself where a stage needs it."
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

# ------------------------------------------------------------------ helpers

# How $1's hyprconf-managed block looks: a usable "pair", an "unpaired" one,
# or "none". Every marker state machine below latches skip=1 at the begin
# marker and clears it only at an end marker, so rewriting a file whose pair
# is not a pair — one marker lost to a botched manual revert, a dotfiles
# merge or a trimmed tail, or the two of them left in the wrong order —
# deletes everything from the begin marker to EOF, at exit 0, with no backup
# and nothing said. Presence is therefore not enough: an end marker ABOVE
# the begin marker is consumed with skip already 0 and never clears the
# latch, so the tail goes exactly as if it were missing. Both shapes are a
# file this installer does not understand: every caller leaves it exactly as
# it is and says so.
managed_block_state() {
    local file="$1" begin="$2" end="$3" b e
    [[ -f $file ]] || { printf 'none'; return 0; }
    # -e: defensive — a marker starting with a dash would read as an option
    # (today's pair starts with "#"). First line of each: a duplicate pair
    # below the first is dropped by the rewrite anyway.
    b="$(grep -nxF -e "$begin" "$file" | head -1 | cut -d: -f1)"
    e="$(grep -nxF -e "$end" "$file" | head -1 | cut -d: -f1)"
    if [[ -n $b && -n $e ]]; then
        if (( b < e )); then printf 'pair'; else printf 'unpaired'; fi
    elif [[ -n $b || -n $e ]]; then printf 'unpaired'
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
# Both preservation promises hold only over a marker pair that is ordered and
# complete: with one marker line hand-removed, or the two swapped, the file
# is refused untouched (managed_block_state), not rewritten — see there for
# what the alternative costs.
write_managed_block() {
    local file="$1" block="$2" begin="# >>> hyprconf >>>" end="# <<< hyprconf <<<" tmp kept state
    touch "$file"
    state="$(managed_block_state "$file" "$begin" "$end")"
    if [[ $state == unpaired ]]; then
        warn "$file has no usable '$begin' … '$end' pair — left untouched;" \
             "put the missing marker line back, in that order (or delete the odd one), and re-run"
        return 0
    fi
    if [[ $state == pair ]]; then
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
    elif [[ -f $cached && ! -L $cached ]] && cmp -s "$ours" "$cached"; then
        matched="$cached"
    fi
    # Remember what the template looks like NOW, for the run after the next
    # Omarchy release replaces it. Written only when it changed, so a re-run
    # stays byte-stable, and never through a symlink out of the state
    # directory — both the read above and this write stay inside it. The
    # whole directory goes with the rest of the state (README > Reverting to
    # stock).
    #
    # Best-effort, like every other state write here: a cache it cannot
    # write degrades the guard to the installed template alone, it does not
    # stop the run. Unguarded (`set -e`), a ~/.local/state/hyprconf/stock
    # that is a regular file, or one entry the user cannot write, killed the
    # whole install at the first hypr override — hooks, plugins and clock
    # never reached, on every post-update run.
    #
    # The cache is user-writable and it is an input to `git checkout --`:
    # planting the checkout's own current bindings.lua there makes the next
    # run revert an uncommitted edit. Accepted, and no trust boundary
    # (CONTRIBUTING > Security): the same actor can write $HERE/hypr/*.lua
    # directly, which is the file this would restore.
    if [[ ! -L $cached ]] && ! cmp -s "$stock" "$cached" 2>/dev/null; then
        { mkdir -p "${cached%/*}" && cp "$stock" "$cached"; } 2>/dev/null ||
            warn "could not cache Omarchy's hypr/$name template under ${cached%/*} —" \
                 "the refresh guard will not survive the next template bump"
    fi
    [[ -n $matched ]] || return 0
    # Whether the repair took is "did hypr/$name change", not "does it still
    # look like a template". Two shapes make those differ: a clobber the user
    # committed (git checkout succeeds and restores the clobber itself), and
    # the cache refresh above, which has already replaced the bytes $matched
    # names with the newer template — so comparing against $matched reported
    # every cached-match clobber repaired, the unrepairable ones included.
    local before
    before="$(cksum < "$ours")"
    if git -C "$HERE" checkout -q -- "hypr/$name" 2>/dev/null &&
        [[ "$(cksum < "$ours")" != "$before" ]]; then
        warn "hypr/$name in the checkout had been replaced by Omarchy's stock template" \
             "(omarchy refresh writes through the symlink) — restored it from git"
    else
        warn "hypr/$name in the checkout is Omarchy's stock template and could not be" \
             "restored from git — see: git -C $HERE status"
    fi
}

# Keep a one-time .stock backup of whatever was at an override path before the
# overlay linked over it, so README › Reverting to stock puts it back with a
# plain `mv`. `cp -P` copies a SYMLINK as a symlink: a stow-style dotfiles link
# is somebody's own arrangement and has to survive the round trip unchanged —
# the old `[[ -e $target && ! -L $target ]]` guard skipped every link, so
# `ln -sfn` overwrote it with no backup and no message. README:90 already
# promises a symlinked monitors.lua is yours; this was the one place that did
# not keep one.
#
# Two further tests keep a re-run honest: never back up a link that is already
# ours (it would fire on every run), and never overwrite a backup that exists
# (a user who re-creates their own link after an install must not lose the
# first backup).
backup_before_link() {
    local target="$1" src="$2"
    [[ -e $target || -L $target ]] || return 0
    [[ "$(readlink "$target" 2>/dev/null)" != "$src" ]] || return 0
    [[ ! -e $target.stock && ! -L $target.stock ]] || return 0
    cp -P "$target" "$target.stock"
    info "backed up $(basename "$target") -> $(basename "$target").stock"
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
    backup_before_link "$target" "$HERE/hypr/$name"
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

stage_terminal() {
    log "Terminal: kitty"
    # Assert kitty is present BEFORE touching the default: omarchy-default-
    # terminal (Omarchy 4.0.3-1) checks nothing — it writes the desktop id
    # into ~/.config/xdg-terminals.list and notifies — so pointing it at an
    # absent kitty would leave SUPER+RETURN and every TUI launcher with no
    # terminal at all. Its installer is no help either: omarchy-install-
    # terminal prints "Failed to install $package" and still exits 0
    # (/usr/bin/omarchy-install-terminal:50-52, 4.0.3-1), so kitty comes from
    # the packages file and this stage never calls it.
    #
    # Warn and skip rather than die: this is the FIRST stage after the package
    # gate, and hooks/post-update.d/10-hyprconf re-runs the installer with
    # --no-packages after every omarchy-update. A `die` here would take the
    # hotkeys, the plugins, the hooks and the theme stages down with it on
    # every update of a box that has no kitty — silently, forever. Every other
    # non-package stage warns and returns for the same reason, and every
    # module exits 0 rather than failing the run.
    # Omarchy's own probe, not a hand-rolled `command -v`: omarchy-cmd-present
    # is `command -v` per argument (/usr/bin/omarchy-cmd-present, 4.0.3-1,
    # unchanged from 4.0.2), the command omarchy-font-set:33 asks the same
    # question with — and the harness already fakes every omarchy-* name.
    omarchy-cmd-present kitty || {
        warn "kitty is not installed — the terminal default and its include are left alone" \
             "(run \`bash install.sh\` from a terminal to install it)"
        return 0
    }

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
# stays authoritative. On 4.0.3-1 that file is the theme include plus an
# override layer (config/kitty/kitty.conf); Omarchy's real defaults —
# listen_on and `allow_remote_control socket-only` among them — moved to
# /etc/xdg/kitty/kitty.conf, which kitty merges BELOW the user file (its
# SYSTEM_CONF, /usr/lib/kitty/kitty/cli.py:712). An upgraded box keeps its
# own copies of those lines. The include below is appended LAST, so anything
# hyprconf.conf restated would silently win over omarchy-font-set, which now
# appends font_family to the user file when it is absent
# (/usr/bin/omarchy-font-set:33-40) — it restates nothing.
stage_kitty_include() {
    # Separate `local` statements on purpose: `local a=1 b="$a"` declares both
    # names before assigning, so $a is still unbound there — fatal under set -u.
    local dir="$HOME/.config/kitty"
    local conf="$dir/kitty.conf"
    mkdir -p "$dir"
    install -m 644 "$HERE/kitty/hyprconf.conf" "$dir/hyprconf.conf"

    # Only point kitty at zsh once zsh really exists — otherwise kitty cannot
    # start at all. The login shell is deliberately left as bash. The reason
    # lives once, in the shipped header of kitty/hyprconf.conf.
    if [[ -n $_HYPRCONF_ZSH ]]; then
        printf '\nshell %s\n' "$_HYPRCONF_ZSH" >> "$dir/hyprconf.conf"
    else
        warn "zsh not installed — kitty will keep using the login shell"
    fi

    # Unconditional: ~/.config/kitty/kitty.conf is OPTIONAL from 4.0.3 on —
    # Omarchy's defaults moved to /etc/xdg/kitty/kitty.conf, which kitty
    # merges BELOW any user file (SYSTEM_CONF, /usr/lib/kitty/kitty/cli.py:712,
    # kitty 0.48.2) — so a box with no user file must still get the include,
    # and creating it costs Omarchy nothing. That is how omarchy-font-set
    # reaches the same file (`mkdir -p ~/.config/kitty` then append,
    # /usr/bin/omarchy-font-set:33-40). grep answers non-zero when the file is
    # absent, which is the branch that creates it.
    grep -qxF 'include hyprconf.conf' "$conf" 2>/dev/null ||
        printf '\n# hyprconf overlay\ninclude hyprconf.conf\n' >> "$conf"
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

stage_bin() {
    log "PATH tools (bin/hyprconf-*)"
    mkdir -p "$HOME/.local/bin"
    local f dst
    # Every bin/hyprconf-* file; a new tool is one file in bin/. @HYPRCONF_DIR@
    # is substituted the way the post-update hook gets it, for any tool that
    # needs the checkout path. Rendered beside the target and mv'd over it:
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
# directory comparison `diff -rq` does not make. -mindepth 1 keeps it to the
# files the sync reproduces: the plugin directory's own mode comes from the
# checkout either way (cp -aL copies the source directory's mode onto the
# staging dir mktemp -d made, and mv keeps it), so including it would decide
# nothing. No entry is ever a symlink to compare against a copy — Omarchy's
# validator and test_plugins.py both refuse one inside a plugin folder
# (bin/omarchy-plugin-validate, "symlinks are not allowed inside a plugin
# folder"; 4.0.2-1) — so this and the cp -aL below cannot disagree.
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
# never re-synced: Service.qml execs it directly as an argv list, no shell,
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
# left at omarchy.clock matches nothing once the bar swaps to our copy: the
# clock drifts off-center and hasAnchor goes false (shell/plugins/bar/Bar.qml).
# Run on EVERY run, not once behind the clock marker: an anchor can go stale
# long after the first install — `omarchy plugin clone omarchy.clock` leaves
# one naming a clone whose folder a later `omarchy plugin remove` renamed to
# a dot-prefixed .bak (unscanned, so the id exists nowhere) — and nothing else
# repairs it.
#
# Only an anchor that names the clock SOURCE is touched, never a choice:
#
#   * $stock, the id the swap moved the clock out from under, or
#   * an id that is on no bar section AND is no installed plugin — the shape a
#     removed clone leaves. A bare "not on the bar" test is not enough: it
#     would re-point an anchor aimed at a widget the user merely disabled.
#
# and only while $keep is really on the bar, so the anchor never names a
# widget the bar does not carry (a user who disabled our clock keeps theirs).
# With no shell to list plugins the dangling case is left alone rather than
# guessed at.
#
# A read-modify-write of the shell's own file: stage_clock waits
# (wait_for_shell_json) for the last thing it asked the shell for to be on
# disk first, or the edit lands on a stale copy and the shell's pending
# write then takes it back. Omarchy has no command for bar.centerAnchor
# (`omarchy bar --help` has no route for it, 4.0.3-1), and deliberately NOT
# omarchy-shell-config's commit() the way modules/idle takes it: that re-sorts
# the whole file with jq -S and then refreshes the shell (:58, :61), which
# would race the very write this edit just waited out.
follow_center_anchor() {
    local stock="$1" keep="$2" shell_json="$HOME/.config/omarchy/shell.json" anchor
    [[ -f $shell_json ]] || return 0
    anchor="$(jq -r '.bar.centerAnchor // ""' "$shell_json" 2>/dev/null)" || return 0
    [[ -n $anchor && $anchor != "$keep" ]] || return 0
    jq -e "$_JQ_IDS"' ids | any(. == $keep)' --arg keep "$keep" \
        "$shell_json" >/dev/null 2>&1 || return 0
    if [[ $anchor != "$stock" ]]; then
        jq -e "$_JQ_IDS"' ids | all(. != $anchor)' --arg anchor "$anchor" \
            "$shell_json" >/dev/null 2>&1 || return 0
        local list
        list="$(omarchy-plugin-list --json 2>/dev/null)" || return 0
        jq -e --arg anchor "$anchor" 'all(.[]?; .id != $anchor)' \
            <<<"$list" >/dev/null 2>&1 || return 0
    fi
    # The `&& mv` tail this replaces reported success whichever way jq went:
    # a failing jq is the non-final command of an && list, so set -e never
    # fired, the mv was skipped and the info line printed anyway — while a
    # failing mv, being final, took the whole install down over a cosmetic
    # step. Warn and carry on: a cosmetic edit never fails the run.
    if jq --arg id "$keep" '.bar.centerAnchor = $id' "$shell_json" > "$shell_json.tmp"; then
        mv "$shell_json.tmp" "$shell_json"
        info "bar centerAnchor follows $keep (was $anchor)"
    else
        rm -f "$shell_json.tmp"
        warn "could not move bar.centerAnchor to $keep in $shell_json" \
             "— will retry on the next run"
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
# beside them) with three deltas its header names, clonedFrom omarchy.clock so
# the shell swaps it into the stock slot. The stock widget cannot tick
# seconds: omarchy.clock samples SystemClock at Minutes precision
# (shell/plugins/panels/clock/BarWidget.qml), so a seconds format would sit
# frozen 59 s of every minute. Shipped and SYNCED on every run like the other
# three — an install-time copy of the stock plugin, made once, lagged the
# 4.0.2 release's hardening of its own Panel.qml by eight lines with nothing
# to refresh it (omarchy-plugin-update refuses a non-git folder). Only the
# user's choices are set ONCE, behind the marker: the enable and hyprconf's
# format — 12-hour with seconds and AM/PM, "hh:mm:ss AP" in the
# Qt.formatDateTime tokens the widget feeds its format setting to — for the
# same reason as the font and the default apps: the post-update hook re-runs
# this installer, and a clock the user later reformatted (right-click cycles
# formats; `omarchy bar set`) must stay theirs. The centre anchor is NOT one
# of them: it is a pointer at whichever widget the clock is, repaired on every
# run behind its own guard (follow_center_anchor). The sync comes first so the
# shell never loads a stale build.
#
# `omarchy plugin disable` is NOT the whole way back, so the closing line
# does not say it is: restoreCloneSource copies the clone's whole bar entry
# onto omarchy.clock and rewrites only its id
# (shell/services/PluginRegistry.qml), so "hh:mm:ss AP" rides along onto the
# Minutes-precision widget, and bar.centerAnchor keeps naming a widget the
# bar no longer carries (hasAnchor goes false and the centre section centres
# the group instead — shell/plugins/bar/Bar.qml). The two undo steps are in
# README › Reverting to stock; the format there is Omarchy's own default,
# "dddd HH:mm" (config/omarchy/shell.json, 4.0.2-1 — the same fallback the
# widget's own setting("format", ...) carries).
stage_clock() {
    log "Bar clock: hh:mm:ss AP (hyprconf.clock)"
    local id="hyprconf.clock"
    sync_plugin_dir hyprconf-clock "$id"
    local marker="$HOME/.local/state/hyprconf/clock-applied"
    if [[ -e $marker ]]; then
        info "already applied once — the clock is yours now"
    # Needs the live shell; on a TTY or over SSH there is nothing to answer,
    # so the marker stays unwritten and the next in-session run retries.
    elif ! activate_plugin_copy "$id"; then
        warn "could not enable $id (is the Omarchy shell running?) — will retry on the next run"
    else
        wait_for_swap omarchy.clock "$id"
        set_clock_format "$id"
        mkdir -p "$(dirname "$marker")"
        : > "$marker"
        info "seconds tick via the $id widget (undo: omarchy plugin disable $id, then the format and the centre anchor — README › Reverting to stock)"
    fi

    # OUTSIDE the marker: the centre anchor is a pointer at the clock, not a
    # preference, and it can go stale years after the first install (its own
    # comment). Its guard, not the marker, is what keeps a user's own choice
    # safe — and on a run where the enable failed there is nothing on the bar
    # for it to point at, so it declines by itself.
    follow_center_anchor omarchy.clock "$id"
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

    backup_before_link "$HOME/.p10k.zsh" "$HERE/zsh/.p10k.zsh"
    ln -sfn "$HERE/zsh/.p10k.zsh" "$HOME/.p10k.zsh"
    # The block names the checkout (the hyprsync alias), so it is rendered the
    # way every other payload that does is — @HYPRCONF_DIR@, as in stage_bin
    # and stage_hooks. It used to derive the path from `readlink -f
    # ~/.p10k.zsh`, which GNU readlink happily answers for a file that is not
    # there: with the link gone (the documented revert removes it several steps
    # before the .zshrc block) the two dirnames left `/home` and the alias ran
    # `bash /home/install.sh --sync`. A relocated checkout is re-applied from
    # its new location, which rewrites the block, so nothing is lost.
    local rendered
    rendered="$(mktemp)"
    sed "s|@HYPRCONF_DIR@|$HERE_SED|g" "$HERE/zsh/zshrc.block" > "$rendered"
    write_managed_block "$HOME/.zshrc" "$rendered"
    rm -f -- "$rendered"
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
    [[ -d $HERE/hypr && -f $HERE/packages ]] || bootstrap "${orig_args[@]}"
    preflight
    if (( do_pull )); then stage_pull; fi
    # The only sudo install.sh itself still needs. Modules gate their own
    # root work on HYPRCONF_NO_SUDO, which --no-packages exports.
    if (( do_packages )); then stage_packages; fi
    # After the package stage, never before it — see resolve_zsh.
    resolve_zsh
    stage_terminal
    # Self-contained modules: each one applies, gates and undoes itself
    # (modules/<name>/README.md). Order-free — call order is alphabetical.
    bash "$HERE/modules/fastfetch/install"
    bash "$HERE/modules/firefox/install"
    bash "$HERE/modules/firefox-theme/install"
    bash "$HERE/modules/font/install"
    bash "$HERE/modules/idle/install"
    bash "$HERE/modules/keychron/install"
    bash "$HERE/modules/themes/install"
    bash "$HERE/modules/vscode/install"
    stage_hotkeys
    stage_looknfeel
    stage_monitors
    stage_bin
    stage_bar_plugin
    stage_clock
    stage_workspaces
    stage_window_title
    stage_shell
    stage_hooks
    hyprctl reload >/dev/null 2>&1 || true
    if (( do_update )); then stage_update; fi

    log "Done. SUPER+D still opens Omarchy's menu; the login shell is still bash."
}

main
