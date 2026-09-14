#!/usr/bin/env bash
# hyprconf — one person's overlay on a stock Omarchy, as self-contained modules.
#
#   bash <(curl -fsSL --proto '=https' https://hyprconf.sh)
#
# hyprconf.sh serves this very file to curl and wget. Run with no payload
# beside it, it clones github.com/ak4dev/.hyprconf (branch stable) into
# ~/.hyprconf — or uses the checkout already there — and hands over to that
# checkout's own copy. The same by hand:
#
#   git clone -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf
#   bash ~/.hyprconf/install.sh
#
# From then on it is `hyprconf` (~/.local/bin, on Omarchy's session PATH), and
# -h is the whole of its contract. What it does: every modules/*/install in
# turn — alphabetically, each order-free, idempotent and its own `install
# undo` — the ~/.local/bin/hyprconf link, and the post-update hook
# (hooks/10-hyprconf) that re-applies after every omarchy-update. Nothing else
# lands in $HOME from here, and no sudo is asked for here: every package and
# root write is a module's, behind HYPRCONF_NO_SUDO, which --no-packages
# exports (the hook passes it). Verified against Omarchy 4.0.3-1.
set -euo pipefail
: "${OMARCHY_PATH:=/usr/share/omarchy}"   # Omarchy's own, default/bash/env-bootstrap:12,16
# The curl path's clone — for users too (a fork, a branch under test, another
# directory), hence plain names rather than the suite's _HYPRCONF_* seams.
: "${HYPRCONF_REPO:=https://github.com/ak4dev/.hyprconf}"
: "${HYPRCONF_BRANCH:=stable}"
: "${HYPRCONF_DIR:=$HOME/.hyprconf}"
# The checkout this file sits in, through the ~/.local/bin link (readlink -f).
# On the curl path BASH_SOURCE is a pipe, not a file: nothing sits beside it.
HERE=/dev/null
[[ -f ${BASH_SOURCE[0]:-} ]] && HERE=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

log() { printf '==> %s\n' "$*"; }
die() { printf 'hyprconf: %s\n' "$*" >&2; exit 1; }
usage() {
    cat <<'USAGE'
Usage: bash <(curl -fsSL --proto '=https' https://hyprconf.sh) [OPTIONS]
       hyprconf [OPTIONS] [MODULE...]

Installs, re-applies or removes the hyprconf overlay on an Omarchy system.

The curl form clones github.com/ak4dev/.hyprconf (branch stable) into
~/.hyprconf — or uses the checkout already there, without pulling it — and
runs that checkout's install.sh with the same arguments. HYPRCONF_REPO,
HYPRCONF_BRANCH and HYPRCONF_DIR override those three. `hyprconf` is the
~/.local/bin link that checkout's first run makes.

Options:
  --sync          Pull the checkout, re-apply, then run omarchy-update (whose
                  post-update hook re-applies once more, after Omarchy's
                  migrations). What the `hyprsync` alias runs.
  --no-update     Apply only; never invoke omarchy-update. What the post-update
                  hook passes, since it already runs inside an update.
  --no-packages   Skip everything that needs sudo: every module's packages and
                  its own root work. Exported to the modules as
                  HYPRCONF_NO_SUDO, which each one honours itself. The hook
                  passes this too.
  --undo          Run every module's `install undo` in reverse order, then
                  remove the hook and the link. With MODULE names, only those.
  -h, --help      Show this help.

With no options: apply every module once, without pulling or updating —
re-running is how changes are picked up. A MODULE name (a directory under
modules/) applies only the ones named, e.g. `hyprconf hypr` after an edit to
that module's files.
USAGE
}

sync=0 update=1 undo=0 only=() failed=()
for arg in "$@"; do
    case $arg in
        --sync)        sync=1 ;;
        --no-update)   update=0 ;;   # whichever order the flags come in
        --no-packages) export HYPRCONF_NO_SUDO=1 ;;
        --undo)        undo=1 ;;
        -h|--help)     usage; exit 0 ;;
        -*)            die "unknown option: $arg (try --help)" ;;
        *)             only+=("$arg") ;;   # a module name, checked once a checkout is beside this file
    esac
done

# Preflight, before anything lands. Under sudo, env_reset points HOME at /root
# and the overlay half-installs there — the curl|bash habit of prefixing sudo
# is the dangerous one; no seam past this, the suite runs unprivileged (CI
# included). default/ is where every module reads Omarchy from (owned by
# omarchy-settings 4.0.3-1, which the omarchy package pulls in).
((EUID)) || die "run as your regular user — the modules ask for sudo themselves where they need it."
[[ -d $OMARCHY_PATH/default ]] || die "no Omarchy found at $OMARCHY_PATH — this overlay installs on top of Omarchy."

# The curl path. The checkout is cloned — or the one already there used as it
# is, never pulled: that is --sync's job — and its own copy takes over with the
# arguments as given; git is Omarchy's (install/omarchy-base.packages:43).
if [[ ! -d $HERE/modules ]]; then
    if [[ ! -d $HYPRCONF_DIR/.git ]]; then
        log "Cloning $HYPRCONF_REPO ($HYPRCONF_BRANCH) into $HYPRCONF_DIR"
        git clone --branch "$HYPRCONF_BRANCH" --single-branch -- "$HYPRCONF_REPO" "$HYPRCONF_DIR" ||
            die "git clone failed — see the message above"
    fi
    [[ -f $HYPRCONF_DIR/install.sh ]] || die "$HYPRCONF_DIR/install.sh not found — is $HYPRCONF_DIR a hyprconf checkout?"
    exec bash "$HYPRCONF_DIR/install.sh" "$@"
fi

# The modules named, checked before anything runs, or every one of them.
mods=()
if (( ${#only[@]} )); then
    for m in "${only[@]}"; do
        [[ -x $HERE/modules/$m/install ]] || die "no module named $m (the directories under modules/)"
        mods+=("$HERE/modules/$m/install")
    done
else
    mods=("$HERE"/modules/*/install)
fi
link=$HOME/.local/bin/hyprconf
hook=$HERE/hooks/10-hyprconf
# Where omarchy-hook-install puts it: ~/.config/omarchy/hooks/<type>.d/<basename>
# (bin/omarchy-hook-install:18-20). Omarchy has no `hook remove` (`omarchy hook
# --help` relates only `install`), so --undo removes the copy itself.
installed_hook=$HOME/.config/omarchy/hooks/post-update.d/${hook##*/}

if (( undo )); then
    for (( i = ${#mods[@]} - 1; i >= 0; i-- )); do   # reverse order, every one even if one fails
        m=${mods[i]%/install}; m=${m##*/}
        log "undo $m"
        bash "${mods[i]}" undo || failed+=("$m")
    done
    (( ${#only[@]} )) || rm -f "$installed_hook" "$link"
    (( ${#failed[@]} == 0 )) || die "undo failed: ${failed[*]} — see above"
    exit 0
fi

if (( sync )); then
    log "Updating the hyprconf checkout"
    # --ff-only, never a reset: this checkout is also where the overlay is
    # edited, so a divergence is a stop with git's own message above it.
    # `-c pull.rebase=false` because a global `pull.rebase = true` makes
    # --ff-only refuse a dirty tree outright. A pull that changes this file
    # leaves the run in progress on the old one; the modules are read fresh.
    git -C "$HERE" -c pull.rebase=false pull --ff-only || die "git pull failed — resolve it and re-run"
fi

# The command: a symlink, since nothing here needs rendering and it must stay
# the file a pull updates — re-pointed only when wrong, so a re-run writes
# nothing. ~/.local/bin is on the session PATH (default/bash/env-bootstrap:37-40).
mkdir -p "${link%/*}"
[[ $(readlink "$link" 2>/dev/null) == "$HERE/install.sh" ]] || ln -sfn "$HERE/install.sh" "$link"

for m in "${mods[@]}"; do
    n=${m%/install}; n=${n##*/}
    log "$n"
    bash "$m" || failed+=("$n")   # one module's failure is its own; the rest still run
done

# The hook, through Omarchy's own installer — mkdir -p, cp under the file's
# basename, chmod 755 (bin/omarchy-hook-install:27-29): a re-run rewrites the
# same bytes. Nothing is rendered into it — it runs the link above.
omarchy-hook-install post-update "$hook" >/dev/null ||
    echo "    WARNING: omarchy-hook-install failed — nothing re-applies after omarchy-update until a run succeeds" >&2

(( ${#failed[@]} == 0 )) || die "failed: ${failed[*]} — each said why above; re-run, or \`hyprconf <module>\` for one"
if (( sync && update )); then
    log "Updating Omarchy"
    omarchy-update   # whose post-update hook re-applies once more, after the migrations (bin/omarchy-update:48-49)
fi
log "Done."
