#!/usr/bin/env bash
set -euo pipefail

# ── Palette (matches deploy.sh / teardown.sh / install.sh) ───────────────────
if [[ -t 1 ]]; then
  WH=$'\e[1;37m' GL=$'\e[1;31m' AM=$'\e[1;33m'
  GR=$'\e[1;32m' DM=$'\e[2;37m' RS=$'\e[0m'
else
  WH='' GL='' AM='' GR='' DM='' RS=''
fi

log_step() { printf '%s  ▸ %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_ok()   { printf '%s  ✔ %s%s%s\n'        "$GR" "$WH" "$1" "$RS"; }
log_warn() { printf '%s  ! %s%s%s\n'        "$AM" "$WH" "$1" "$RS"; }
log_die()  { printf '%s  ✘ FATAL: %s%s%s\n' "$GL" "$WH" "$1" "$RS" >&2; exit 1; }

readonly HYPRCONF_DIR="$HOME/.hyprconf"
readonly HYPRCONF_REPO_URL="https://github.com/ak4dev/.hyprconf"
readonly HYPRCONF_STABLE_BRANCH="stable"
readonly STOW_DIR="$HYPRCONF_DIR/stow"
readonly ZSHRC="$HOME/.zshrc"
readonly ZSHENV="$HOME/.zshenv"
# Powerlevel10k must live inside OMZ's custom themes dir so that
# ZSH_THEME="powerlevel10k/powerlevel10k" resolves without error.
readonly P10K_DIR="${HOME}/.oh-my-zsh/custom/themes/powerlevel10k"
declare -ra HYPRCONF_SPARSE_PATHS=(
    /README.md
    /assets
    /docs
    /infra
    /install
    /packages
    /setup.sh
    /stow
    /theme
)

# True when setup.sh is invoked by install.sh inside a chroot (no live systemd).
_in_chroot() { [[ "${HYPRCONF_CHROOT:-0}" == "1" ]]; }

# Retry a pacman command up to 3x — large transactions occasionally hit
# transient mirror errors (SSL_ERROR_SYSCALL) mid-download. Already-fetched
# packages stay cached, so retries only re-fetch what failed.
pacman_retry() {
    local attempt
    for attempt in 1 2 3; do
        "$@" && return 0
        (( attempt < 3 )) || return 1
        log_warn "pacman command failed (mirror error?) — retrying in 10s..."
        sleep 10
    done
}

print_header() {
  local mode="${1:-setup}"
  printf '\n%s  ──────────────────────────────────────────────────────────────%s\n' "$DM" "$RS"
  printf '%s  .hyprconf  ▸  %s%s\n' "$WH" "$mode" "$RS"
  printf '%s  ──────────────────────────────────────────────────────────────%s\n\n' "$DM" "$RS"
}

configure_pacman() {
    log_step "Configuring pacman..."
    local conf="/etc/pacman.conf"
    local modified=0

    # Uncomment a standalone flag (e.g., Color, ILoveCandy, VerbosePkgLists)
    _pac_flag() {
        grep -q "^${1}$" "$conf" && return
        if grep -q "^#${1}$" "$conf"; then
            sudo sed -i "0,/^#${1}$/s/^#${1}$/${1}/" "$conf"
        else
            sudo sed -i "/^\[options\]/a ${1}" "$conf"
        fi
        (( modified++ )) || true
    }

    # Ensure a key = value option is set (uncomment or insert)
    _pac_kv() {
        local key="$1" val="$2"
        grep -q "^${key} = " "$conf" && return
        if grep -q "^#${key} = " "$conf"; then
            sudo sed -i "0,/^#${key} = .*/s/^#${key} = .*/${key} = ${val}/" "$conf"
        else
            sudo sed -i "/^\[options\]/a ${key} = ${val}" "$conf"
        fi
        (( modified++ )) || true
    }

    _pac_flag "Color"           # coloured output
    _pac_flag "ILoveCandy"      # Pac-Man progress bar
    _pac_flag "VerbosePkgLists" # table view when installing many packages
    _pac_flag "CheckSpace"      # pre-flight disk-space check
    _pac_kv   "ParallelDownloads" "5"

    # Enable [multilib] repo (32-bit libraries, required by Steam and friends)
    if ! grep -q '^\[multilib\]' "$conf"; then
        sudo sed -i 's/^#\[multilib\]$/[multilib]/' "$conf"
        sudo sed -i '/^\[multilib\]$/{n; s/^#Include/Include/}' "$conf"
        (( modified++ )) || true
        log_step "Refreshing package databases (multilib enabled)..."
        pacman_retry sudo pacman -Sy --noconfirm
    fi

    if [[ $modified -gt 0 ]]; then
        log_ok "pacman.conf updated (${modified} change(s))."
    else
        log_ok "pacman.conf already configured."
    fi
}


install_packages() {
    log_step "Installing required packages..."
    pacman_retry sudo pacman -Syu --noconfirm

    if [[ ! -f "$HYPRCONF_DIR/packages" ]]; then
        log_die "packages file not found at $HYPRCONF_DIR/packages"
    fi

    mapfile -t packages < <(grep -v '^\s*#' "$HYPRCONF_DIR/packages" | grep -v '^\s*$')

    local missing=()
    for pkg in "${packages[@]}"; do
        pacman -Qi "$pkg" &>/dev/null || missing+=("$pkg")
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_step "Installing ${#missing[@]} missing package(s)..."
        pacman_retry sudo pacman -S --noconfirm --needed "${missing[@]}"
    fi
    log_ok "All packages installed."
}

# hyprconf installs ONLY official-repo packages — it never installs from the AUR
# automatically. Any foreign (AUR / locally-built) package on the system is
# offered for removal here, EXCEPT the yay helper itself, which is kept so that
# `hyprconf addon` can still build AUR packages on demand (with an explicit
# warning + confirmation). Removal is destructive, so it always prompts and
# defaults to "no" when stdin is not a terminal.
remove_aur_packages() {
    command -v pacman &>/dev/null || return 0

    # Packages to keep even though they are foreign (the AUR helper family).
    local -a keep=(yay yay-bin yay-git)

    local -a foreign=()
    local pkg
    while IFS= read -r pkg; do
        [[ -z "$pkg" ]] && continue
        local kept=false k
        for k in "${keep[@]}"; do
            [[ "$pkg" == "$k" ]] && kept=true && break
        done
        $kept || foreign+=("$pkg")
    done < <(pacman -Qmq 2>/dev/null)

    if [[ ${#foreign[@]} -eq 0 ]]; then
        log_ok "No AUR packages installed — nothing to remove."
        return 0
    fi

    log_warn "hyprconf does not use AUR packages. Found ${#foreign[@]} foreign (AUR) package(s):"
    printf '    %s\n' "${foreign[@]}"
    printf '%s  Remove them now? This uninstalls them and their unused deps. [y/N] %s' "$WH" "$RS"

    local ans
    if [[ -t 0 ]]; then
        read -r ans
    else
        ans="n"
    fi

    case "${ans,,}" in
        y|yes)
            log_step "Removing ${#foreign[@]} AUR package(s)..."
            sudo pacman -Rns --noconfirm "${foreign[@]}" \
                && log_ok "AUR packages removed." \
                || log_warn "Some AUR packages could not be removed — check output above."
            ;;
        *)
            log_warn "Skipped. To remove manually: sudo pacman -Rns ${foreign[*]}"
            ;;
    esac
}


create_directories() {
    log_step "Creating required directories..."
    mkdir -p ~/.config ~/.config/hypr ~/.local/bin ~/.vscode-oss/extensions
    mkdir -p ~/Pictures ~/Downloads ~/wallpaper

    mkdir -p "$HOME/.config/hypr/conf.d"

    local hypr_local="$HOME/.config/hypr/conf.d/99-hyprconf-local.conf"
    # A broken symlink (pointing to a now-deleted stow file) is not a regular
    # file, so `! -f` would be true and the redirect below would follow the
    # symlink and recreate the file inside the stow tree.  Remove it first so
    # we always create a real machine-local file.
    [[ -L "$hypr_local" && ! -e "$hypr_local" ]] && rm "$hypr_local"
    if [[ ! -f "$hypr_local" ]]; then
        cat >"$hypr_local" <<'EOF'
# 99-hyprconf-local.conf — local Hyprland overrides
# This file is intentionally machine-local and not managed by GNU Stow.
#
# Examples:
#   $mainMod = ALT
EOF
    fi

    log_ok "Directories ready."
}


# Ensure 99-hyprconf-local.conf is a real machine-local file, not a stow-managed
# symlink.  Must run BEFORE clone_or_update_repo so user settings are preserved
# even if git pull would delete the (now-untracked) stow copy of the file.
migrate_user_conf() {
    local stow_file="$STOW_DIR/hypr/.config/hypr/conf.d/99-hyprconf-local.conf"
    local live_file="$HOME/.config/hypr/conf.d/99-hyprconf-local.conf"

    if [[ -L "$live_file" ]]; then
        local target
        target=$(realpath "$live_file" 2>/dev/null || true)
        if [[ -n "$target" && "$target" == "$HYPRCONF_DIR"/* ]]; then
            # Working stow-managed symlink — preserve content as a real file.
            local content
            content=$(cat "$live_file" 2>/dev/null || true)
            rm "$live_file"
            if [[ -n "$content" ]]; then
                printf '%s\n' "$content" > "$live_file"
            fi
            log_ok "Migrated 99-hyprconf-local.conf to machine-local file."
        elif [[ -z "$target" ]]; then
            # Broken symlink — remove it; create_directories will recreate it fresh.
            rm "$live_file"
            log_ok "Removed stale 99-hyprconf-local.conf symlink."
        fi
    fi

    # Remove the stow copy if it still exists (e.g. after an older install that
    # tracked this file), so future stow runs do not try to manage it.
    if [[ -f "$stow_file" ]]; then
        rm "$stow_file"
    fi
}

_apply_repo_sparse_checkout() {
    git -C "$HYPRCONF_DIR" sparse-checkout init --no-cone >/dev/null 2>&1 || true
    git -C "$HYPRCONF_DIR" sparse-checkout set "${HYPRCONF_SPARSE_PATHS[@]}" >/dev/null
}

_clone_repo_branch() {
    local branch="$1"
    git clone --depth=1 --single-branch --branch "$branch" --sparse \
        "$HYPRCONF_REPO_URL" "$HYPRCONF_DIR"
    _apply_repo_sparse_checkout
}


clone_or_update_repo() {
    local _force="${1:-false}"
    if [ ! -d "$HYPRCONF_DIR/.git" ]; then
        log_step "Cloning hyprconf repo..."
        _clone_repo_branch "$HYPRCONF_STABLE_BRANCH" \
            || log_die "Could not clone ${HYPRCONF_REPO_URL}."
        log_ok "Repository ready (${HYPRCONF_STABLE_BRANCH}, sparse checkout)."
    else
        # Skip pull when no upstream tracking branch is configured (e.g. CI /
        # Packer builds where the repo was seeded from a git archive bundle).
        # The bundle-based _sync_vm_to_dev step keeps the VM repo current.
        git -C "$HYPRCONF_DIR" fetch --quiet origin \
            "$HYPRCONF_STABLE_BRANCH" 2>/dev/null || true

        local current_branch
        local upstream
        current_branch="$(git -C "$HYPRCONF_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
        upstream="$(git -C "$HYPRCONF_DIR" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"

        if [[ "$current_branch" != "dev" && "$upstream" != "origin/dev" ]]; then
            _apply_repo_sparse_checkout
        fi

        if [[ -n "$upstream" ]]; then
            log_step "Updating hyprconf repo..."
            if [[ "$_force" == "true" ]]; then
                log_warn "Force-resetting to $upstream (local divergence discarded)..."
                git -C "$HYPRCONF_DIR" fetch origin 2>/dev/null \
                    || log_warn "Fetch failed — resetting to last known remote state."
                git -C "$HYPRCONF_DIR" reset --hard "$upstream" \
                    || log_die "Force reset to $upstream failed."
            else
                # The theme switcher writes generated output THROUGH the stow
                # symlinks into git-tracked files (theme-colors.conf,
                # kitty generated.conf, dunstrc, hyprlock.conf, btop.conf), so a
                # themed machine has a chronically dirty working tree.  A plain
                # `git pull --ff-only` then aborts ("local changes would be
                # overwritten") and silently strands every new file in the update
                # (e.g. a newly-added script).  --autostash shelves the local
                # changes, fast-forwards (so new files DO arrive), then re-applies
                # them.  Conflicting theme files are taken from upstream here and
                # regenerated by reapply_current_theme later in the sync.
                local _theme_state="$STOW_DIR/hypr/.config/hypr/.current-theme"
                local _saved_theme=""
                [[ -f "$_theme_state" ]] && _saved_theme="$(cat "$_theme_state" 2>/dev/null || true)"

                git -C "$HYPRCONF_DIR" pull --ff-only --autostash \
                    || log_warn "Fast-forward pull failed — using existing files."

                # NOTE: `git pull --autostash` exits 0 even when re-applying the
                # autostash conflicts (upstream changed the same theme files), so the
                # conflict must be detected from repo state, not the exit code.
                # Resolve any unmerged paths to the upstream version so the tree — and
                # the NEXT sync's pull — is clean again; the conflicting files are
                # theme outputs, regenerated by reapply_current_theme later.
                if [[ -n "$(git -C "$HYPRCONF_DIR" diff --name-only --diff-filter=U 2>/dev/null)" ]]; then
                    local _conflict
                    while IFS= read -r _conflict; do
                        [[ -n "$_conflict" ]] || continue
                        git -C "$HYPRCONF_DIR" checkout HEAD -- "$_conflict" 2>/dev/null || true
                    done < <(git -C "$HYPRCONF_DIR" diff --name-only --diff-filter=U 2>/dev/null)
                    log_warn "Local theme edits conflicted with the update — took the new versions (theme is re-applied below)."
                fi

                # A leftover autostash entry only exists when the re-apply conflicted
                # (a clean pop auto-drops).  Remove it so stashes don't accumulate.
                if git -C "$HYPRCONF_DIR" stash list 2>/dev/null | head -1 | grep -q 'autostash'; then
                    git -C "$HYPRCONF_DIR" stash drop 2>/dev/null || true
                fi

                # Re-derive the active theme: keep the user's selection so
                # reapply_current_theme regenerates colors for the right theme even
                # if the update changed the tracked .current-theme.
                if [[ -n "$_saved_theme" && -f "$_theme_state" ]] \
                    && [[ "$(cat "$_theme_state" 2>/dev/null || true)" != "$_saved_theme" ]]; then
                    printf '%s\n' "$_saved_theme" > "$_theme_state" 2>/dev/null || true
                fi
            fi
            log_ok "Repository ready."
        else
            log_ok "Repository ready (no upstream — skipping pull)."
        fi
    fi
}

install_oh_my_zsh() {
    if [ ! -d ~/.oh-my-zsh ]; then
        log_step "Installing Oh My Zsh..."
        # SECURITY: clone the repo directly instead of piping the remote install
        # script into a shell — no execution of unpinned remote code, and the
        # user's ~/.zshrc is never moved aside (update_zshrc manages it).
        git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$HOME/.oh-my-zsh" \
            || log_die "Could not clone Oh My Zsh."
        # The upstream install script also switched the login shell; keep that
        # behaviour for interactive dotfiles-mode installs (the full installer
        # already creates the user with -s /bin/zsh).
        if [[ "${SHELL:-}" != */zsh ]] && command -v zsh &>/dev/null && [[ -t 0 ]]; then
            chsh -s "$(command -v zsh)" \
                || log_warn "Could not change the login shell — run: chsh -s $(command -v zsh)"
        fi
        log_ok "Oh My Zsh installed."
    else
        log_ok "Oh My Zsh already installed."
    fi
}

install_powerlevel10k() {
    # Ensure parent dirs exist (sync mode might not have OMZ yet).
    mkdir -p "$(dirname "$P10K_DIR")"

    if [ ! -d "$P10K_DIR" ]; then
        log_step "Installing Powerlevel10k..."
        git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
        log_ok "Powerlevel10k installed."
    else
        log_step "Updating Powerlevel10k..."
        git -C "$P10K_DIR" pull --ff-only || true
        log_ok "Powerlevel10k up to date."
    fi
}

update_zshrc() {
    log_step "Configuring ~/.zshrc..."

    touch "$ZSHRC"

    # In sync mode it's possible the user never installed OMZ / p10k yet.
    # Prompt to install (interactive only) instead of silently breaking the prompt.
    if [[ ! -f "$HOME/.oh-my-zsh/oh-my-zsh.sh" ]]; then
        log_warn "Oh My Zsh not found at $HOME/.oh-my-zsh — the prompt will fall back until setup.sh installs it."
        if [[ -t 0 ]]; then
            read -r -p "Install Oh My Zsh now? [Y/n] " _ans
            if [[ -z "${_ans:-}" || "${_ans:-}" =~ ^[Yy]$ ]]; then
                install_oh_my_zsh
            fi
        fi
    fi

    if [[ ! -f "$P10K_DIR/powerlevel10k.zsh-theme" ]]; then
        log_warn "Powerlevel10k theme not found at $P10K_DIR — prompt will fall back until setup.sh installs it."
        if [[ -t 0 ]]; then
            read -r -p "Install Powerlevel10k now? [Y/n] " _ans
            if [[ -z "${_ans:-}" || "${_ans:-}" =~ ^[Yy]$ ]]; then
                install_powerlevel10k
            fi
        fi
    fi

    local tmp
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' RETURN

    # Rewrite OMZ / p10k bits into a single managed block at the first OMZ source line.
    awk '
        BEGIN {
            in_block = 0
            inserted = 0
        }

        # Drop any previous managed block.
        /^# >>> hyprconf zsh >>>$/ { in_block = 1; next }
        /^# <<< hyprconf zsh <<<$/{ in_block = 0; next }
        in_block == 1 { next }

        # Drop legacy/manual Powerlevel10k sourcing (we use OMZ theme).
        /powerlevel10k\.zsh-theme/ { next }

        # Drop OMZ / theme / p10k lines we manage.
        /^[[:space:]]*export[[:space:]]+ZSH=/ { next }
        /^[[:space:]]*ZSH_THEME=/ { next }
        /\.p10k\.zsh/ { next }

        # Remove any OMZ source line (we will insert exactly one block).
        /^[[:space:]]*(source|\.)[[:space:]].*oh-my-zsh\.sh[[:space:]]*$/ {
            if (inserted == 0) {
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
                print "  echo \"[hyprconf] Oh My Zsh not found at $ZSH — run: ~/.hyprconf/setup.sh\""
                print "fi"
                print ""
                print "if [[ -r \"$P10K_THEME\" && -f \"$HOME/.p10k.zsh\" ]]; then"
                print "  source \"$HOME/.p10k.zsh\""
                print "fi"
                print "typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION=$\047\\uf303\047"
                print "# <<< hyprconf zsh <<<"
                inserted = 1
            }
            next
        }

        # De-duplicate hyprconf-managed aliases (sync has historically appended many).
        /^[[:space:]]*alias[[:space:]]+hyprsync=/ { next }
        /^[[:space:]]*alias[[:space:]]+confsync=/ { next }

        { print }

        END {
            if (inserted == 0) {
                print ""
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
                print "  echo \"[hyprconf] Oh My Zsh not found at $ZSH — run: ~/.hyprconf/setup.sh\""
                print "fi"
                print ""
                print "if [[ -r \"$P10K_THEME\" && -f \"$HOME/.p10k.zsh\" ]]; then"
                print "  source \"$HOME/.p10k.zsh\""
                print "fi"
                print "typeset -g POWERLEVEL9K_OS_ICON_CONTENT_EXPANSION=$\047\\uf303\047"
                print "# <<< hyprconf zsh <<<"
            }
        }
    ' "$ZSHRC" > "$tmp"

    mv "$tmp" "$ZSHRC"

    add_if_missing() {
        local line="$1"
        grep -qxF "$line" "$ZSHRC" 2>/dev/null || echo "$line" >> "$ZSHRC"
    }

    add_if_missing 'source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh'
    add_if_missing 'source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh'
    add_if_missing 'export PATH="$HOME/.local/bin:$PATH"'
    add_if_missing "alias hyprsync='~/.hyprconf/setup.sh --sync'"
    add_if_missing "fastfetch --logo arch2 --logo-color-1 green --logo-color-2 green"

    trap - RETURN
    # shellcheck disable=SC2088  # literal ~ is intentional in this user-facing message
    log_ok "~/.zshrc configured."
}

update_zshenv() {
    # ~/.zshenv is sourced by ALL zsh invocations — including non-interactive SSH
    # sessions — so PATH must live here to make `hyprconf` reachable over SSH.
    touch "${ZSHENV}"
    grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' "${ZSHENV}" 2>/dev/null \
        || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${ZSHENV}"
    # shellcheck disable=SC2088  # literal ~ is intentional in this user-facing message
    log_ok "~/.zshenv configured."
}

configure_zprofile() {
    log_step "Configuring ~/.zprofile..."
    local zprofile="$HOME/.zprofile"

    local old_autostart='[[ $(tty) == /dev/tty1 ]] && exec Hyprland'
    local autostart='[[ $(tty) == /dev/tty1 ]] && { command -v start-hyprland >/dev/null && exec start-hyprland || exec Hyprland; }'

    # Remove legacy autostart line (Hyprland now warns if not started via start-hyprland)
    if [[ -f "$zprofile" ]]; then
        sed -i "\\|^${old_autostart}$\\|d" "$zprofile" 2>/dev/null || true
    fi

    grep -qxF "$autostart" "$zprofile" 2>/dev/null || echo "$autostart" >> "$zprofile"
    log_ok "Hyprland auto-start configured in ~/.zprofile"
}

# Additive per-file linker.  GNU stow is all-or-nothing: a single pre-existing
# real file aborts the WHOLE package, so newly-added files (e.g. a new script
# like yubikey-fido2-setup) never get a symlink even though they were pulled into
# the repo.  This walks the package and creates a relative symlink for every file
# whose target is still missing, while leaving existing real files (and links)
# untouched — exactly what additive mode promises.
_additive_link_package() {
    local stow_dir="$1" package="$2" target_dir="$3"
    local pkg_root="$stow_dir/$package"
    local linked=0

    # Ensure parent directories exist as real dirs (matches stow --no-folding).
    # __pycache__ is pruned to match the stow --ignore below: running the CLI
    # regenerates bytecode caches inside the repo tree, and stale .pyc symlinks
    # must never be shipped into $HOME.
    while IFS= read -r dir; do
        local rel="${dir#"$pkg_root"/}"
        mkdir -p "$target_dir/$rel"
    done < <(find "$pkg_root" -mindepth 1 -name __pycache__ -prune -o -type d -print)

    while IFS= read -r file; do
        local rel="${file#"$pkg_root"/}"
        local target="$target_dir/$rel"
        # Skip anything already present — real user files are preserved and
        # existing symlinks are left alone (broken links were cleaned earlier by
        # purge_broken_symlinks).
        [[ -e "$target" || -L "$target" ]] && continue
        if ln -s "$(realpath -s --relative-to="$(dirname "$target")" "$file")" "$target"; then
            linked=$((linked + 1))
        fi
    done < <(find "$pkg_root" -name __pycache__ -prune -o \( -type f -o -type l \) -print)

    [[ $linked -gt 0 ]] && log_ok "Linked $linked new file(s) in $package."
    return 0
}

force_stow_package() {
    local package="$1"
    local stow_dir="$2"
    local target_dir="$3"
    # "restow" (default, full replace) or "stow" (additive-only, preserves user files)
    local stow_mode="${4:-restow}"

    log_step "Stowing $package..."

    # Pre-flight: remove directory-level symlinks in the target that correspond
    # to real directories in the stow package.  These are left by the binary-only
    # install mode (which links e.g. ~/.local/lib/hyprconf → repo dir directly).
    # stow --no-folding requires a real directory there, not a dir symlink.
    find "$stow_dir/$package" -mindepth 1 -type d | while IFS= read -r dir; do
        local rel_path="${dir#$stow_dir/$package/}"
        local target_path="$target_dir/$rel_path"
        if [[ -L "$target_path" ]]; then
            rm "$target_path"
        fi
    done

    # --ignore=__pycache__: running the Python CLI regenerates bytecode caches
    # inside the repo tree; they are gitignored and must not be stowed into $HOME.
    if ! stow -d "$stow_dir" -t "$target_dir" --no-folding --ignore='__pycache__' --"$stow_mode" "$package" 2>/dev/null; then
        if [[ "$stow_mode" == "stow" ]]; then
            # Additive-only mode: GNU stow aborts the entire package on the first
            # conflict, which would leave newly-added files unlinked.  Fall back to
            # per-file linking so new files still get symlinked while user files
            # (the conflicts) are preserved.
            log_warn "Conflicts in $package — linking new files individually (user files preserved). Run 'hyprconf sync --full' to reset to defaults."
            _additive_link_package "$stow_dir" "$package" "$target_dir"
            return 0
        fi

        log_warn "Conflict in $package — backing up and retrying..."

        stow -d "$stow_dir" -t "$target_dir" --no-folding --ignore='__pycache__' -D "$package" || true

        find "$stow_dir/$package" \( -type f -o -type l \) | while read -r file; do
            local rel_path="${file#$stow_dir/$package/}"
            local target_file="$target_dir/$rel_path"
            if [[ -L "$target_file" ]]; then
                # Guard: only skip RELATIVE symlinks that resolve into the stow tree —
                # those were created by stow and must not be touched.
                # ABSOLUTE symlinks (e.g. created by detect_gpu_and_link_monitor_config)
                # are NOT stow-managed; they are safe to remove so stow can re-own them.
                local link_dest; link_dest=$(readlink "$target_file")
                if [[ "$link_dest" != /* ]]; then
                    local real_target; real_target=$(realpath "$target_file" 2>/dev/null || true)
                    if [[ -n "$real_target" && "$real_target" == "$stow_dir"/* ]]; then
                        continue
                    fi
                fi
                rm "$target_file"
            elif [[ -e "$target_file" ]]; then
                mv "$target_file" "${target_file}.backup.$(date +%Y%m%d%H%M%S)"
            fi
        done

        stow -d "$stow_dir" -t "$target_dir" --no-folding --ignore='__pycache__' --restow "$package"
    fi

    log_ok "Stowed $package."
}

sync_vscode_theme_extensions() {
    local force_copy="${1:-false}"
    local theme_source="$HYPRCONF_DIR/theme/.vscode-oss/extensions"
    local extensions_dir="$HOME/.vscode-oss/extensions"

    if [ ! -d "$theme_source" ]; then
        log_warn "VS Code theme source not found — skipping."
        return
    fi

    mkdir -p "$extensions_dir"

    while IFS= read -r -d '' theme_pkg; do
        local pkg_name; pkg_name=$(basename "$theme_pkg")
        local dest_pkg="$extensions_dir/$pkg_name"

        if [ -d "$dest_pkg" ] && [ "$force_copy" != "true" ]; then
            log_ok "VS Code extension $pkg_name already present."
            continue
        fi

        [ -d "$dest_pkg" ] && rm -rf "$dest_pkg"
        log_step "Copying VS Code extension $pkg_name..."
        cp -a "$theme_pkg" "$dest_pkg"
        log_ok "Copied $pkg_name."
    done < <(find "$theme_source" -mindepth 1 -maxdepth 1 -type d -print0)
}

purge_broken_symlinks() {
    log_step "Pruning broken symlinks..."

    local pruned=0
    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME/.config" -maxdepth 2 -xtype l -print0)

    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME/.local/bin" -maxdepth 1 -xtype l -print0 2>/dev/null)

    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME/.local/lib" -maxdepth 2 -xtype l -print0 2>/dev/null)

    while IFS= read -r -d '' link; do
        rm "$link"
        (( pruned++ )) || true
    done < <(find "$HOME" -maxdepth 1 -xtype l -print0)

    log_ok "Pruned $pruned broken symlink(s)."
}

_is_desktop() {
    # Primary: DMI chassis type (3-7 = Desktop/Tower variants, 13 = All-in-one, 24 = Space-saving)
    local chassis
    chassis=$(cat /sys/class/dmi/id/chassis_type 2>/dev/null) || chassis=""
    chassis="${chassis//[[:space:]]}"  # strip any surrounding whitespace
    case "$chassis" in
        3|4|5|6|7|13|24) return 0 ;;
        "")  ;;  # DMI unavailable — fall through to battery check
        *)   return 1 ;;  # Known non-desktop (laptop, notebook, tablet, etc.)
    esac

    # Fallback: no battery present → assume desktop
    compgen -G "/sys/class/power_supply/BAT*" > /dev/null && return 1
    return 0
}

_has_touchscreen() {
    # Standard udev-tagged touchscreens (ELAN HID, etc.)
    grep -rql "^ID_INPUT_TOUCHSCREEN=1" /sys/class/input/*/device/uevent 2>/dev/null \
        && return 0
    # Generic touch devices tagged ID_INPUT_TOUCH=1 (e.g. ASUS ROG Ally, some
    # AMD-based handhelds) that don't use ID_INPUT_TOUCHSCREEN.
    grep -rql "^ID_INPUT_TOUCH=1" /sys/class/input/*/device/uevent 2>/dev/null \
        && return 0
    # Wacom I2C pen+touch digitizers (e.g. ThinkPad X13 Yoga): the touch component is
    # exposed as NAME="Wacom HID * Finger" on an i2c bus, but udev never sets
    # ID_INPUT_TOUCHSCREEN=1 because the wacom driver bypasses the generic HID rules.
    # Requiring PHYS="i2c-" prevents false-positives from external USB Wacom tablets.
    local f
    for f in /sys/class/input/*/device/uevent; do
        grep -q '^NAME="Wacom.*Finger' "$f" 2>/dev/null \
            && grep -q '^PHYS="i2c-' "$f" 2>/dev/null \
            && return 0
    done
    return 1
}

_has_accelerometer() {
    # iio-based accelerometers expose an in_accel_x_raw sysfs attribute.
    compgen -G "/sys/bus/iio/devices/*/in_accel_x_raw" > /dev/null 2>&1
}

_has_nvidia() {
    # Match any VGA/3D/Display controller whose description contains "NVIDIA".
    lspci 2>/dev/null | grep -qiE "(VGA compatible controller|3D controller|Display controller).*nvidia"
}


# Symlink monitors.conf -> $hypr_conf_dir/$default_file, unless it's already a
# valid symlink to a $glob_prefix* file in $hypr_conf_dir (e.g. a preset chosen
# via switch_monitor.sh / `hyprconf monitor set`) — in which case the existing
# choice is kept across setup/sync runs, mirroring reapply_current_theme's
# persistence model for the theme switcher.
_link_monitor_config() {
    local monitors_conf="$1" hypr_conf_dir="$2" glob_prefix="$3" default_file="$4" label="$5"

    if [[ -L "$monitors_conf" ]]; then
        # Resolve the full symlink chain: switch_monitor.sh links monitors.conf
        # to the *deployed* ~/.config/hypr/pcMonitors.* path (itself a Stow
        # symlink back into $hypr_conf_dir), so a one-level readlink won't match
        # $hypr_conf_dir directly — only the fully-resolved path will.
        local current_target
        current_target=$(readlink -f "$monitors_conf" 2>/dev/null)
        if [[ -n "$current_target" && "$current_target" == "$hypr_conf_dir/$glob_prefix"* ]]; then
            log_ok "$label — keeping existing monitor config: $(basename "$current_target")"
            return 0
        fi
    fi

    rm -f "$monitors_conf"
    ln -sf "$hypr_conf_dir/$default_file" "$monitors_conf"
    log_ok "$label — using $default_file"
}

detect_gpu_and_link_monitor_config() {
    log_step "Detecting device type for monitor config..."

    local monitors_conf="$HOME/.config/hypr/monitors.conf"
    local hypr_conf_dir="$STOW_DIR/hypr/.config/hypr"

    if _is_desktop; then
        _link_monitor_config "$monitors_conf" "$hypr_conf_dir" "pcMonitors" "pcMonitors.conf" "Desktop detected"
    else
        _link_monitor_config "$monitors_conf" "$hypr_conf_dir" "laptopMonitors" "laptopMonitors.conf" "Laptop/portable detected"
        log_step "Enabling power-profiles-daemon..."
        if _in_chroot; then
            sudo systemctl enable power-profiles-daemon
        elif systemctl is-active --quiet power-profiles-daemon 2>/dev/null; then
            log_ok "power-profiles-daemon already active — skipping."
        else
            sudo systemctl enable --now power-profiles-daemon
        fi
        setup_power_monitor
    fi
}

# ---------------------------------------------------------------------------
# Automatic power profile switching (laptop/battery devices only)
# ---------------------------------------------------------------------------
# Installs a udev rule that triggers hyprconf-power-monitor on AC adapter
# state changes.  The script sets "performance" when plugged in and
# "power-saver" when on battery via powerprofilesctl.

setup_power_monitor() {
    # SECURITY: a udev RUN+= program is executed by udevd AS ROOT.  The target
    # must therefore be a root-owned, non-user-writable path.  The previous rule
    # pointed at ~/.local/bin/hyprconf-power-monitor — a file the user (or any
    # code running as the user: a malicious AUR/pip/npm dep, a browser exploit)
    # could overwrite to get root on the next AC plug/unplug, with no password
    # and no YubiKey.  We now install a root-owned copy under /usr/local/lib and
    # point the rule there.  ~/.local/bin/hyprconf-power-monitor stays as the
    # user-facing copy for manual `hyprconf power-profile` use only.
    local src_script="$STOW_DIR/hypr/.local/bin/hyprconf-power-monitor"
    local user_script="$HOME/.local/bin/hyprconf-power-monitor"
    local system_script="/usr/local/lib/hyprconf/hyprconf-power-monitor"
    local udev_rule="/etc/udev/rules.d/99-hyprconf-power.rules"

    [[ -e "$src_script" ]] || src_script="$user_script"
    if [[ ! -e "$src_script" ]]; then
        log_warn "hyprconf-power-monitor source not found — skipping power monitor setup."
        return 0
    fi

    # Install/refresh the root-owned copy that udev will execute.
    if sudo install -Dm755 -o root -g root "$src_script" "$system_script" 2>/dev/null; then
        log_ok "Power monitor installed (root-owned): $system_script"
    else
        log_warn "Could not install root-owned power monitor — skipping power rule."
        return 0
    fi

    log_step "Installing udev rule for automatic power profile switching..."
    local rule_content
    rule_content="# hyprconf — automatic power profile switching (performance on AC, power-saver on battery)
# SECURITY: RUN+= runs as root, so it must point at a root-owned path, never \$HOME.
ACTION==\"change\", SUBSYSTEM==\"power_supply\", ATTR{type}==\"Mains\", RUN+=\"$system_script\""

    # (Re)write the rule when it is missing, points somewhere else, or — most
    # importantly — still references a user-writable \$HOME path (migration from
    # the pre-hardening rule).
    local needs_write=1
    if [[ -f "$udev_rule" ]] \
        && grep -qF "RUN+=\"$system_script\"" "$udev_rule" 2>/dev/null \
        && ! grep -qE 'RUN\+?=.*(/home/|\$HOME)' "$udev_rule" 2>/dev/null; then
        needs_write=0
    fi

    if (( needs_write )); then
        if [[ -f "$udev_rule" ]] && grep -qE 'RUN\+?=.*(/home/|\$HOME)' "$udev_rule" 2>/dev/null; then
            log_warn "Migrating insecure power rule (was executing a \$HOME path as root)."
        fi
        printf '%s\n' "$rule_content" | sudo tee "$udev_rule" > /dev/null \
            && log_ok "udev rule installed: $udev_rule" \
            || { log_warn "Could not install udev rule — automatic power switching unavailable."; return 0; }
    else
        log_ok "Secure power udev rule already installed — skipping."
    fi

    if ! _in_chroot; then
        sudo udevadm control --reload-rules 2>/dev/null \
            && log_ok "udev rules reloaded." \
            || log_warn "Could not reload udev rules — reboot to apply."

        # Set the initial power profile based on current AC state
        log_step "Setting initial power profile..."
        "$user_script" auto 2>/dev/null \
            && log_ok "Initial power profile applied." \
            || log_warn "Could not set initial power profile."
    fi
}

# ---------------------------------------------------------------------------
# Hardware feature detection — touchscreen OSK and auto-rotation
# ---------------------------------------------------------------------------

write_hardware_conf() {
    local conf_file="$HOME/.config/hypr/conf.d/60-hardware.conf"
    local has_touch=false has_accel=false has_nvidia=false

    _has_touchscreen   && has_touch=true
    _has_accelerometer && has_accel=true
    _has_nvidia        && has_nvidia=true

    {
        printf '# Generated by setup.sh — DO NOT EDIT MANUALLY\n'
        printf '# Re-run setup.sh or hyprconf sync to regenerate.\n'

        if $has_nvidia; then
            printf '\n# Nvidia GPU — required env vars for Wayland (wiki.hypr.land/Nvidia)\n'
            printf 'env = LIBVA_DRIVER_NAME,nvidia\n'
            printf 'env = __GLX_VENDOR_LIBRARY_NAME,nvidia\n'
        fi

        if $has_touch; then
            printf '\n# On-screen keyboard (touchscreen detected)\n'
            printf 'exec-once = wvkbd-launcher\n'
            printf 'bind = $mainMod SHIFT, O, exec, wvkbd-toggle\n'
            # Bind all touch input to eDP-1 so coordinates are always relative
            # to the built-in display, not the full compositor space.  Without
            # this, multi-monitor setups map touch across all monitors, causing
            # offset/flipped input.  transform=0 matches the default eDP-1
            # orientation; override in 99-hyprconf-local.conf if needed.
            printf '\ninput {\n'
            printf '    touchdevice {\n'
            printf '        output    = eDP-1\n'
            printf '        transform = 0\n'
            printf '    }\n'
            printf '}\n'
            # touch-panel-launcher checks keyboard presence at session start and
            # starts touch-panel only if no physical keyboard is found.
            # touch-panel-watch monitors for keyboard removal during the session
            # and starts touch-panel when the last keyboard is unplugged.
            printf '\n# Touch control panel (runtime keyboard detection)\n'
            printf 'exec-once = touch-panel-launcher\n'
            printf 'exec-once = touch-panel-watch\n'
        fi

        if $has_accel; then
            printf '\n# Auto-rotation (accelerometer detected)\n'
            printf 'exec-once = autorotate\n'
        fi
    } > "$conf_file"

    if $has_touch || $has_accel || $has_nvidia; then
        log_ok "Hardware conf written → $conf_file"
    else
        log_ok "No hardware-specific features detected — hardware conf cleared."
    fi
}

setup_hardware_features() {
    log_step "Checking for hardware features..."

    if _has_nvidia; then
        log_ok "Nvidia GPU detected."
        log_step "Installing Nvidia packages (nvidia-open, nvidia-utils, egl-wayland)..."
        sudo pacman -S --noconfirm --needed nvidia-open nvidia-utils egl-wayland \
            && log_ok "Nvidia packages installed." \
            || log_warn "Nvidia package install failed — Hyprland may not start. Install manually: sudo pacman -S nvidia-open nvidia-utils egl-wayland"
        # Add Nvidia modules for early KMS so the display controller is ready
        # before the compositor starts.  Skip if already present to stay idempotent.
        local mkinitcpio=/etc/mkinitcpio.conf
        if [[ -f "$mkinitcpio" ]] && ! grep -qE "^MODULES=.*nvidia" "$mkinitcpio" 2>/dev/null; then
            log_step "Adding Nvidia early-KMS modules to $mkinitcpio..."
            sudo sed -i '/^MODULES=/s/)$/ nvidia nvidia_modeset nvidia_uvm nvidia_drm)/' "$mkinitcpio" \
                && log_ok "Nvidia modules added to MODULES." \
                || log_warn "Could not update $mkinitcpio — add 'nvidia nvidia_modeset nvidia_uvm nvidia_drm' to MODULES manually."
            log_step "Rebuilding initramfs..."
            sudo mkinitcpio -P \
                && log_ok "Initramfs rebuilt." \
                || log_warn "mkinitcpio -P failed — rebuild manually: sudo mkinitcpio -P"
        else
            log_ok "Nvidia early-KMS modules already present — skipping."
        fi

        # nvidia-drm modeset=1 is required for Wayland (wiki.hypr.land/Nvidia) —
        # without it Hyprland fails to start on Nvidia. The early-KMS modules above
        # load nvidia_drm before the compositor, but the modeset parameter still
        # needs to be set via modprobe.d. Appends rather than overwrites so any
        # existing nvidia.conf options (e.g. NVreg_EnableGpuFirmware for VFIO) are kept.
        local nvidia_modprobe=/etc/modprobe.d/nvidia.conf
        if [[ ! -f "$nvidia_modprobe" ]] || ! grep -q "^options nvidia-drm modeset=1" "$nvidia_modprobe" 2>/dev/null; then
            log_step "Setting nvidia-drm modeset=1 in $nvidia_modprobe..."
            printf 'options nvidia-drm modeset=1\n' | sudo tee -a "$nvidia_modprobe" > /dev/null \
                && log_ok "nvidia-drm modeset=1 set." \
                || log_warn "Could not write $nvidia_modprobe — add 'options nvidia-drm modeset=1' manually."
        else
            log_ok "nvidia-drm modeset=1 already set."
        fi
    else
        log_ok "No Nvidia GPU detected — skipping Nvidia setup."
    fi

    if _has_touchscreen; then
        log_ok "Touchscreen detected."
        # The on-screen keyboard (wvkbd) is AUR-only. hyprconf never installs AUR
        # packages automatically, so the OSK is NOT installed here — even on touch
        # devices. The launcher/toggle scripts degrade gracefully when it is
        # absent; install it manually to enable the OSK.
        log_warn "On-screen keyboard (wvkbd) is AUR-only and is NOT installed automatically."
        log_warn "To enable the OSK, install it manually: yay -S wvkbd"
        mkdir -p "$HOME/.config/wvkbd"
        log_step "Installing gtk-layer-shell (required by touch-panel)..."
            sudo pacman -S --noconfirm --needed gtk-layer-shell \
                && log_ok "gtk-layer-shell installed." \
                || log_warn "gtk-layer-shell install failed — touch panel unavailable."
    else
        log_ok "No touchscreen detected — skipping OSK setup."
    fi

    if _has_accelerometer; then
        log_ok "Accelerometer detected."
        log_step "Installing iio-sensor-proxy..."
        sudo pacman -S --noconfirm --needed iio-sensor-proxy \
            && log_ok "iio-sensor-proxy installed." \
            || log_warn "iio-sensor-proxy install failed — auto-rotation unavailable."
        log_step "Enabling iio-sensor-proxy.service..."
        if _in_chroot; then
            sudo systemctl enable iio-sensor-proxy \
                || log_warn "Could not enable iio-sensor-proxy.service."
        else
            sudo systemctl enable --now iio-sensor-proxy \
                || log_warn "Could not enable iio-sensor-proxy.service."
        fi
    else
        log_ok "No accelerometer detected — skipping auto-rotation setup."
    fi

    write_hardware_conf

    # ── GPU passthrough boot-time binding (multi-NVIDIA idempotent sync) ──
    # If the user has already configured GPU passthrough on a multi-NVIDIA system,
    # ensure the boot-time vfio-pci binding stays in sync.  This is a no-op when
    # GPU passthrough is not configured or on single-GPU setups.
    local _gpu_conf="${HOME}/.config/hyprconf/gpu-passthrough.conf"
    if [[ -f "$_gpu_conf" ]]; then
        local _gpu_script="$HOME/.config/hypr/scripts/gpu-passthrough.sh"
        if [[ -f "$_gpu_script" ]]; then
            (
                # shellcheck source=/dev/null
                source "$_gpu_script"
                if _gpu_load_config 2>/dev/null && _gpu_has_other_nvidia_gpu 2>/dev/null; then
                    log_step "Syncing GPU passthrough boot-time binding..."
                    _gpu_configure_boot_binding 2>/dev/null \
                        && log_ok "GPU boot-time binding synced." \
                        || log_warn "GPU boot-time binding sync failed — run 'hyprconf hardware gpu setup' manually."
                fi
            ) || true
        fi
    fi
}

# Re-apply the persisted theme so KDE (Dolphin), GTK (Bluetooth manager), and
# all other themed subsystems are consistent after install or sync.
# Falls back to catppuccin-mocha on a fresh install with no persisted state.
reapply_current_theme() {
    local state_file="$HOME/.config/hypr/.current-theme"
    local script="$HOME/.config/hypr/scripts/theme-switcher/switch_theme.py"

    [[ -f "$script" ]] || { log_warn "Theme switcher not found — skipping theme apply."; return 0; }

    local theme_name=""
    [[ -f "$state_file" ]] && theme_name="$(tr -d '[:space:]' < "$state_file")"
    [[ -z "$theme_name" ]] && theme_name="gruvbox"

    log_step "Applying theme: $theme_name"
    python3 "$script" "$theme_name" --no-reload \
        && log_ok "Theme applied: $theme_name" \
        || log_warn "Theme apply failed — run 'hyprconf theme' manually."
}

stow_all_packages() {
    local stow_mode="${1:-restow}"
    log_step "Stowing all config packages (mode: $stow_mode)..."

    local _stow_failures=()
    while IFS= read -r -d '' pkg; do
        local pkg_name; pkg_name=$(basename "$pkg")
        force_stow_package "$pkg_name" "$STOW_DIR" "$HOME" "$stow_mode" || _stow_failures+=("$pkg_name")
    done < <(find "$STOW_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

    # Safety net: stow -D runs before the retry, so a failed hypr stow leaves
    # ~/.local/bin/hyprconf unlinked.  Re-link it so the CLI stays accessible
    # and the user can run 'hyprconf repair' to fully recover.
    local _hc_src="$STOW_DIR/hypr/.local/bin/hyprconf"
    local _hc_dst="$HOME/.local/bin/hyprconf"
    if [[ -f "$_hc_src" && ! -e "$_hc_dst" ]]; then
        ln -sf "$_hc_src" "$_hc_dst"
        log_warn "hyprconf binary re-linked as fallback — run 'hyprconf repair' to fully restore."
    fi

    detect_gpu_and_link_monitor_config

    if [[ ${#_stow_failures[@]} -gt 0 ]]; then
        log_warn "Stow failed for: ${_stow_failures[*]} — run 'hyprconf repair' to fix."
        return 1
    fi
    log_ok "All packages stowed."
}

seed_hicolor_index() {
    # Steam (and similar apps) install per-game icons into
    # ~/.local/share/icons/hicolor/ but never create the index.theme descriptor
    # required by the freedesktop icon-lookup spec.  Without it, icon loaders
    # (including hyprlauncher/hyprtoolkit) skip the directory entirely, causing
    # blank icons for Steam games and other third-party apps.
    local hicolor_dir="$HOME/.local/share/icons/hicolor"
    local index="$hicolor_dir/index.theme"

    mkdir -p \
        "$hicolor_dir/16x16/apps" \
        "$hicolor_dir/24x24/apps" \
        "$hicolor_dir/32x32/apps" \
        "$hicolor_dir/48x48/apps" \
        "$hicolor_dir/64x64/apps" \
        "$hicolor_dir/96x96/apps" \
        "$hicolor_dir/128x128/apps" \
        "$hicolor_dir/256x256/apps"

    if [[ ! -f "$index" ]]; then
        cat > "$index" << 'EOF'
[Icon Theme]
Name=Hicolor
Comment=Fallback icon theme
Hidden=true
Directories=16x16/apps,24x24/apps,32x32/apps,48x48/apps,64x64/apps,96x96/apps,128x128/apps,256x256/apps

[16x16/apps]
Size=16
Context=Applications
Type=Fixed

[24x24/apps]
Size=24
Context=Applications
Type=Fixed

[32x32/apps]
Size=32
Context=Applications
Type=Fixed

[48x48/apps]
Size=48
Context=Applications
Type=Fixed

[64x64/apps]
Size=64
Context=Applications
Type=Fixed

[96x96/apps]
Size=96
Context=Applications
Type=Fixed

[128x128/apps]
Size=128
Context=Applications
Type=Fixed

[256x256/apps]
Size=256
Context=Applications
Type=Fixed
EOF
        log_ok "Created ~/.local/share/icons/hicolor/index.theme"
    fi

    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache --force --ignore-theme-index "$hicolor_dir" 2>/dev/null || true
    fi
}

setup_firefox() {
    local policies_src="$HYPRCONF_DIR/infra/firefox/policies.json"
    local policies_dir="/etc/firefox/policies"
    local policies_dst="$policies_dir/policies.json"

    if [[ ! -f "$policies_src" ]]; then
        log_warn "Firefox policies source not found ($policies_src) — skipping."
        return
    fi

    log_step "Installing Firefox policies (privacy defaults + uBlock Origin)..."
    if sudo mkdir -p "$policies_dir" && sudo cp "$policies_src" "$policies_dst"; then
        log_ok "Firefox policies installed at $policies_dst."
    else
        log_warn "Could not install Firefox policies — skipping."
    fi
}

enable_services() {
    log_step "Configuring firewall (ufw)..."
    if _in_chroot; then
        # ufw default/enable invoke ufw-init which requires a live netfilter stack.
        # ufw's shipped defaults (DROP inbound, ACCEPT outbound) are already correct,
        # so just enable the service unit for first boot.
        sudo systemctl enable ufw || log_warn "Could not enable ufw."
    else
        sudo ufw default deny incoming  || log_warn "Could not set ufw default (deny incoming)."
        sudo ufw default allow outgoing || log_warn "Could not set ufw default (allow outgoing)."
        sudo ufw enable                 || log_warn "Could not enable ufw."
        sudo systemctl enable --now ufw || log_warn "Could not start ufw service."
    fi

    log_step "Disabling display manager (sddm)..."
    if _in_chroot; then
        sudo systemctl disable sddm 2>/dev/null \
            || log_warn "sddm not found or already disabled — skipping."
    else
        sudo systemctl disable --now sddm 2>/dev/null \
            || log_warn "sddm not found or already disabled — skipping."
    fi
    log_ok "Security services configured."
}

# ---------------------------------------------------------------------------
# Keychron / Lemokey keyboard — HID raw device permissions
# ---------------------------------------------------------------------------
# Installs a udev rule that grants the active login session read/write access
# to the hidraw device for Keychron (VID 0x3434) and Lemokey (VID 0x362d)
# keyboards.  This is required so the web-based remapper at
# launcher.keychron.com (WebHID API) can remap keys without elevated privileges.

setup_keyboard_hid_permissions() {
    local udev_rule="/etc/udev/rules.d/70-keychron.rules"
    local rule_content
    rule_content='# hyprconf — Keychron / Lemokey keyboard HID access for web-based remapping
# Grants the active session user read/write access to the hidraw device so
# launcher.keychron.com (WebHID API) can remap keys without elevated privileges.
# Keychron keyboards (VID 0x3434)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3434", TAG+="uaccess"
# Lemokey keyboards (VID 0x362d)
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="362d", TAG+="uaccess"'

    log_step "Installing udev rule for Keychron/Lemokey HID access..."

    if [[ -f "$udev_rule" ]] && grep -qF 'idVendor=="3434"' "$udev_rule" 2>/dev/null \
        && grep -qF 'idVendor=="362d"' "$udev_rule" 2>/dev/null \
        && grep -qF 'TAG+="uaccess"' "$udev_rule" 2>/dev/null; then
        log_ok "Keychron udev rule already installed — skipping."
        return 0
    fi

    printf '%s\n' "$rule_content" | sudo tee "$udev_rule" > /dev/null \
        && log_ok "Keychron udev rule installed: $udev_rule" \
        || { log_warn "Could not install Keychron udev rule — HID permissions not set."; return 0; }

    if ! _in_chroot; then
        sudo udevadm control --reload-rules 2>/dev/null \
            && log_ok "udev rules reloaded." \
            || log_warn "Could not reload udev rules — reboot to apply."
        sudo udevadm trigger --subsystem-match=hidraw 2>/dev/null \
            && log_ok "hidraw devices retriggered." \
            || log_warn "Could not retrigger hidraw devices — reconnect keyboard to apply."
    fi
}

# ---------------------------------------------------------------------------
# System hardening — conservative, reversible sysctl + resolver tightening
# ---------------------------------------------------------------------------
# All settings here are widely-recommended and low-breakage.  The one item that
# can affect functionality — unprivileged user namespaces, used by Flatpak and
# the Chromium/Chrome sandbox — is shipped commented out as an opt-in.
setup_hardening() {
    log_step "Applying system hardening (sysctl + resolver)..."

    local sysctl_file="/etc/sysctl.d/90-hyprconf-hardening.conf"
    if sudo tee "$sysctl_file" >/dev/null <<'EOF'; then
# Managed by hyprconf — defensive kernel sysctls (reversible: delete this file).
# Hide kernel pointers and restrict the kernel log to root.
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
# Restrict ptrace to direct children, so in-session malware cannot scrape the
# memory of other processes (e.g. read SSH/AWS keys out of a running agent).
kernel.yama.ptrace_scope = 1
# Shrink kernel attack surface reachable from unprivileged code.
kernel.unprivileged_bpf_disabled = 1
net.core.bpf_jit_harden = 2
# Block unprivileged TTY line-discipline autoload (a known privilege-escalation vector).
dev.tty.ldisc_autoload = 0
# Anti-MITM: ignore ICMP redirects (safe for clients).  Strict rp_filter is
# intentionally NOT set here — it can break asymmetric routing in VM/VPN/Docker
# setups, which this machine uses.
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
# Prevent runtime kernel replacement via kexec — closes a path to load an
# unsigned kernel without going through the boot chain. One-way: once set,
# requires a reboot to clear.
kernel.kexec_load_disabled = 1
# OPT-IN: also disable unprivileged user namespaces.  Blocks a large class of
# kernel LPEs but BREAKS Flatpak and the Chromium/Chrome sandbox.  Uncomment
# only if you do not rely on those.
#kernel.unprivileged_userns_clone = 0
#user.max_user_namespaces = 0
EOF
        log_ok "sysctl hardening installed: $sysctl_file"
        _in_chroot || sudo sysctl --system >/dev/null 2>&1 \
            || log_warn "Could not apply sysctls now — they apply on next boot."
    else
        log_warn "Could not write $sysctl_file — skipping sysctl hardening."
    fi

    # Disable LLMNR + mDNS responders (LAN name-spoofing surface).
    local resolved_dir="/etc/systemd/resolved.conf.d"
    local resolved_file="$resolved_dir/90-hyprconf-hardening.conf"
    if sudo mkdir -p "$resolved_dir" \
        && printf '[Resolve]\nLLMNR=no\nMulticastDNS=no\n' | sudo tee "$resolved_file" >/dev/null; then
        log_ok "LLMNR/mDNS disabled: $resolved_file"
        _in_chroot || sudo systemctl try-restart systemd-resolved 2>/dev/null || true
    else
        log_warn "Could not write resolved hardening drop-in."
    fi
}

sync_services() {
    log_step "Enabling system services..."

    # Ensure NetworkManager uses iwd as its wifi backend so it handles both
    # wifi association and DHCP.  Without this, systems that have iwd installed
    # (but no wpa_supplicant) get wifi association without DHCP.
    if command -v iwctl &>/dev/null; then
        local _nm_conf_dir="/etc/NetworkManager/conf.d"
        local _nm_wifi_conf="$_nm_conf_dir/wifi-backend.conf"
        if ! grep -qs "wifi.backend=iwd" "$_nm_wifi_conf" 2>/dev/null; then
            sudo mkdir -p "$_nm_conf_dir"
            printf '[device]\nwifi.backend=iwd\n' | sudo tee "$_nm_wifi_conf" > /dev/null
            log_ok "NetworkManager wifi backend set to iwd."
        fi
    fi

    # Configure ufw defaults (idempotent — safe to run on every sync).
    # enable_services sets these during full setup, but a dotfiles-only or
    # sync-only user also needs them.
    if command -v ufw &>/dev/null && ! _in_chroot; then
        sudo ufw default deny incoming  2>/dev/null || log_warn "Could not set ufw default (deny incoming)."
        sudo ufw default allow outgoing 2>/dev/null || log_warn "Could not set ufw default (allow outgoing)."
        sudo ufw --force enable         2>/dev/null || log_warn "Could not enable ufw."
    fi

    if _in_chroot; then
        sudo systemctl enable NetworkManager  || log_warn "Could not enable NetworkManager."
        command -v iwctl &>/dev/null && sudo systemctl enable iwd || true
        sudo systemctl enable bluetooth       || log_warn "Could not enable bluetooth."
        sudo systemctl enable ufw             || log_warn "Could not enable ufw."
    else
        sudo systemctl enable --now NetworkManager  || log_warn "Could not enable NetworkManager."
        command -v iwctl &>/dev/null && sudo systemctl enable --now iwd || true
        sudo systemctl enable --now bluetooth       || log_warn "Could not enable bluetooth."
        sudo systemctl enable --now ufw             || log_warn "Could not enable ufw."

        # Warn if no wifi profiles are configured so the user knows how to connect.
        if ! nmcli -t -f TYPE con show 2>/dev/null | grep -q "^wifi$"; then
            log_warn "No wifi profiles configured — run: nmtui"
        fi
    fi
    log_ok "Services enabled."

    setup_keyboard_hid_permissions
}

reload_hyprland() {
    if hyprctl reload 2>/dev/null; then
        log_ok "Hyprland reloaded."
    else
        log_warn "Hyprland not running — reload skipped."
    fi
}

repair_install() {
    print_header "repair"
    log_step "Scanning installation for discrepancies..."
    local fixed=0

    # ── 0. Restore stow tree from git ────────────────────────────────────
    # A previous failed sync may have used the old backup-and-retry code to
    # `mv` .py files OUT of the stow tree (reached through a directory
    # symlink).  Restore all tracked files to their committed state so stow
    # can create clean symlinks to them.
    log_step "Restoring stow tree from git..."
    if git -C "$HYPRCONF_DIR" restore . 2>/dev/null; then
        log_ok "Stow tree restored."
    else
        log_warn "git restore failed — stow tree may have local modifications."
    fi

    # ── 1. Remove directory-level symlinks inside stow territory ─────────
    # These are left behind by the binary-only install mode, which links
    # ~/.local/lib/hyprconf → repo dir directly rather than using stow.
    log_step "Checking for directory-level symlinks..."
    while IFS= read -r -d '' pkg; do
        while IFS= read -r dir; do
            local rel="${dir#$pkg/}"
            local tgt="$HOME/$rel"
            if [[ -L "$tgt" ]]; then
                log_warn "Directory symlink removed: ~/$rel → $(readlink "$tgt")"
                rm "$tgt"
                (( fixed++ )) || true
            fi
        done < <(find "$pkg" -mindepth 1 -type d)
    done < <(find "$STOW_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

    # ── 2. Purge broken symlinks ──────────────────────────────────────────
    purge_broken_symlinks

    # ── 3. Re-stow all packages and refresh shell config ─────────────────
    stow_all_packages || true
    update_zshrc
    update_zshenv
    configure_zprofile
    seed_hicolor_index
    log_step "Verifying Python module imports..."
    if python3 - <<'PY' 2>/dev/null
import sys, pathlib
import hyprconf.schema, hyprconf.config, hyprconf.hyprctl
PY
    then
        log_ok "Python module imports OK."
    else
        log_warn "Python imports still failing — library path: $HOME/.local/lib/hyprconf"
        log_warn "Try: ls -la $HOME/.local/lib/hyprconf/"
        (( fixed++ )) || true
    fi

    # ── 5. Verify monitors.conf ───────────────────────────────────────────
    log_step "Verifying monitors.conf..."
    if [[ ! -e "$HOME/.config/hypr/monitors.conf" ]]; then
        log_warn "monitors.conf missing — recreating..."
        detect_gpu_and_link_monitor_config
        (( fixed++ )) || true
    else
        log_ok "monitors.conf OK → $(readlink -f "$HOME/.config/hypr/monitors.conf")"
    fi

    reload_hyprland

    if (( fixed > 0 )); then
        printf '\n%s  ✔ Repair complete — %d issue(s) resolved.%s\n\n' "$GR" "$fixed" "$RS"
    else
        printf '\n%s  ✔ No issues found — installation looks healthy.%s\n\n' "$GR" "$RS"
    fi
}


main() {
    if [[ "${1:-}" == "--repair" ]]; then
        repair_install
        return 0
    fi

    if [[ "${1:-}" == "--sync" ]]; then
        local _sync_full=false
        local _sync_force=false
        for _arg in "${@:2}"; do
            [[ "$_arg" == "--full"  ]] && _sync_full=true
            [[ "$_arg" == "--force" ]] && _sync_force=true
        done

        print_header "sync"
        log_step "Syncing configs..."

        # Migrate 99-hyprconf-local.conf BEFORE git pull so user settings survive
        # a pull that removes the now-untracked stow copy of the file.
        migrate_user_conf
        clone_or_update_repo "$_sync_force"
        create_directories
        purge_broken_symlinks
        sync_vscode_theme_extensions

        # Sync always uses additive-only stow: new symlinks are created for any
        # files added to the packages, but existing symlinks and real files are
        # never replaced.  This preserves user-modified dotfiles regardless of
        # which branch the repo is on.  Pass --full to force a complete restow
        # (resets all dotfiles to repo defaults).
        local _stow_mode="stow"
        [[ "$_sync_full" == "true" ]] && _stow_mode="restow"
        stow_all_packages "$_stow_mode" || true

        update_zshrc
        update_zshenv
        configure_zprofile
        seed_hicolor_index
        setup_firefox
        setup_hardware_features
        reapply_current_theme
        sync_services
        setup_hardening
        reload_hyprland

        # After stowing, check for any packages not yet installed.
        if [[ -f "$HYPRCONF_DIR/packages" ]] && command -v pacman &>/dev/null; then
            local _sync_missing=()
            while IFS= read -r _pkg; do
                [[ -z "$_pkg" ]] && continue
                pacman -Qi "$_pkg" &>/dev/null || pacman -Qg "$_pkg" &>/dev/null || _sync_missing+=("$_pkg")
            done < <(grep -v '^\s*#' "$HYPRCONF_DIR/packages" | grep -v '^\s*$')

            if [[ ${#_sync_missing[@]} -gt 0 ]]; then
                printf '\n%s  ! Missing packages detected:%s\n' "$AM" "$RS"
                printf '    %s\n' "${_sync_missing[@]}"
                printf '\n%s  Install missing packages now? [Y/n] %s' "$WH" "$RS"
                local _ans
                if [[ -t 0 ]]; then
                    read -r _ans
                else
                    _ans="n"
                fi
                case "${_ans,,}" in
                    ""|y|yes)
                        log_step "Installing ${#_sync_missing[@]} missing package(s)..."
                        sudo pacman -S --noconfirm --needed "${_sync_missing[@]}"
                        log_ok "Packages installed."
                        ;;
                    *)
                        log_warn "Skipped. Run: sudo pacman -S ${_sync_missing[*]}"
                        ;;
                esac
            fi
        fi

        # Enforce the no-AUR policy on every sync (prompts only when foreign
        # packages are actually present, so it stays quiet on clean systems).
        remove_aur_packages

        printf '\n%s  ✔ Sync complete.%s\n\n' "$GR" "$RS"
        return 0
    fi

    # Show full banner only when invoked directly (not from install.sh)
    if [[ -z "${HYPRCONF_INSTALLER:-}" ]]; then
        local banner_src="$HYPRCONF_DIR/assets/banner.sh"
        if [[ -f "$banner_src" ]]; then
            # shellcheck source=assets/banner.sh
            source "$banner_src"
            print_banner
        else
            print_header "setup"
        fi
    fi

    configure_pacman
    install_packages
    remove_aur_packages
    create_directories
    clone_or_update_repo
    sync_vscode_theme_extensions
    install_oh_my_zsh
    install_powerlevel10k
    update_zshrc
    update_zshenv
    configure_zprofile
    purge_broken_symlinks
    stow_all_packages || true
    seed_hicolor_index
    setup_firefox
    setup_hardware_features
    reapply_current_theme
    enable_services
    setup_hardening
    sync_services
    reload_hyprland

    printf '\n%s  ✔ Setup complete. Restart your terminal or source your ~/.zshrc.%s\n\n' "$GR" "$RS"
}

main "$@"
