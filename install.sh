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
# the overlay's write outside $HOME), modules/vscode, modules/font,
# modules/keychron and modules/terminal-kitty all bow out of their own root
# work behind it.
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
    # whole install at the first hypr override — the hooks and every module
    # after it never reached, on every post-update run.
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
# would pin the empty string for the whole run — stage_shell would skip itself
# on the very run that installed zsh, leaving the prompt unconfigured until some
# later re-run. main() calls this right after the package stage instead.
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
    # here: they ship inside modules/bar-resources/plugin/bin and land with it.
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
    # kitty is what launches zsh (modules/terminal-kitty), and .zshrc sources
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
    # Self-contained modules: each one applies, gates and undoes itself
    # (modules/<name>/README.md). Order-free — call order is alphabetical.
    bash "$HERE/modules/bar-active-window/install"
    bash "$HERE/modules/bar-clock/install"
    bash "$HERE/modules/bar-resources/install"
    bash "$HERE/modules/bar-workspaces/install"
    bash "$HERE/modules/fastfetch/install"
    bash "$HERE/modules/firefox/install"
    bash "$HERE/modules/firefox-theme/install"
    bash "$HERE/modules/font/install"
    bash "$HERE/modules/idle/install"
    bash "$HERE/modules/keychron/install"
    bash "$HERE/modules/terminal-kitty/install"
    bash "$HERE/modules/themes/install"
    bash "$HERE/modules/vscode/install"
    bash "$HERE/modules/vulkan-gpu/install"
    bash "$HERE/modules/yubikey/install"
    stage_hotkeys
    stage_looknfeel
    stage_monitors
    stage_bin
    stage_shell
    stage_hooks
    hyprctl reload >/dev/null 2>&1 || true
    if (( do_update )); then stage_update; fi

    log "Done. SUPER+D still opens Omarchy's menu; the login shell is still bash."
}

main
