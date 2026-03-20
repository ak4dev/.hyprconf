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
readonly HYPRCONF_COMPAT_BRANCH="mainline"
readonly STOW_DIR="$HYPRCONF_DIR/stow"
readonly ZSHRC="$HOME/.zshrc"
readonly ZSHENV="$HOME/.zshenv"
# Powerlevel10k must live inside OMZ's custom themes dir so that
# ZSH_THEME="powerlevel10k/powerlevel10k" resolves without error.
readonly P10K_DIR="${HOME}/.oh-my-zsh/custom/themes/powerlevel10k"
declare -ra HYPRCONF_SPARSE_PATHS=(
    README.md
    assets
    docs
    infra
    install
    packages
    setup.sh
    stow
)

# True when setup.sh is invoked by install.sh inside a chroot (no live systemd).
_in_chroot() { [[ "${HYPRCONF_CHROOT:-0}" == "1" ]]; }

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
        sudo pacman -Sy --noconfirm
    fi

    if [[ $modified -gt 0 ]]; then
        log_ok "pacman.conf updated (${modified} change(s))."
    else
        log_ok "pacman.conf already configured."
    fi
}


install_packages() {
    log_step "Installing required packages..."
    sudo pacman -Syu --noconfirm

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
        sudo pacman -S --noconfirm --needed "${missing[@]}"
    fi
    log_ok "All packages installed."
}

install_yay() {
    if command -v yay &>/dev/null; then
        log_ok "yay already installed."
        return 0
    fi

    log_step "Installing yay (AUR helper)..."

    local build_dir; build_dir=$(mktemp -d)
    # shellcheck disable=SC2064
    trap "rm -rf '$build_dir'" RETURN

    if ! git clone --depth=1 https://aur.archlinux.org/yay-bin.git "$build_dir/yay-bin"; then
        log_warn "yay: could not reach AUR — skipping (install manually: cd /tmp && git clone https://aur.archlinux.org/yay-bin.git && cd yay-bin && makepkg -si)."
        return 0
    fi

    if ! ( cd "$build_dir/yay-bin" && makepkg -si --noconfirm ); then
        log_warn "yay: build failed — skipping (install manually: yay-bin from AUR)."
        return 0
    fi

    log_ok "yay installed."
}


create_directories() {
    log_step "Creating required directories..."
    mkdir -p ~/.config ~/.config/hypr ~/.local/bin ~/.vscode-oss/extensions
    mkdir -p ~/Pictures ~/Downloads ~/wallpaper

    mkdir -p "$HOME/.config/hypr/conf.d"

    local hypr_local="$HOME/.config/hypr/conf.d/99-hyprconf-local.conf"
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

_remote_branch_exists() {
    local branch="$1"
    git -C "$HYPRCONF_DIR" show-ref --verify --quiet "refs/remotes/origin/${branch}"
}

clone_or_update_repo() {
    if [ ! -d "$HYPRCONF_DIR/.git" ]; then
        log_step "Cloning hyprconf repo..."
        if _clone_repo_branch "$HYPRCONF_STABLE_BRANCH"; then
            log_ok "Repository ready (${HYPRCONF_STABLE_BRANCH}, sparse checkout)."
            return 0
        fi

        log_warn "${HYPRCONF_STABLE_BRANCH} is unavailable — falling back to ${HYPRCONF_COMPAT_BRANCH}."
        _clone_repo_branch "$HYPRCONF_COMPAT_BRANCH" \
            || log_die "Could not clone ${HYPRCONF_REPO_URL}."
        log_ok "Repository ready."
    else
        # Skip pull when no upstream tracking branch is configured (e.g. CI /
        # Packer builds where the repo was seeded from a git archive bundle).
        # The bundle-based _sync_vm_to_dev step keeps the VM repo current.
        git -C "$HYPRCONF_DIR" fetch --quiet origin \
            "$HYPRCONF_STABLE_BRANCH" "$HYPRCONF_COMPAT_BRANCH" 2>/dev/null || true

        local current_branch
        local upstream
        current_branch="$(git -C "$HYPRCONF_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
        upstream="$(git -C "$HYPRCONF_DIR" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"

        # Mainline → stable migration runs unconditionally: it must fire even
        # when upstream is still set to origin/dev (e.g. legacy installs where
        # the mainline branch was tracking origin/dev instead of origin/mainline).
        # IMPORTANT: use HEAD (not origin/stable) so we don't change the working
        # tree — setup.sh is running FROM this directory, and checking out an
        # older commit would replace it on disk mid-execution.
        if [[ "$current_branch" == "$HYPRCONF_COMPAT_BRANCH" ]] \
            && _remote_branch_exists "$HYPRCONF_STABLE_BRANCH"; then
            if [[ -z "$(git -C "$HYPRCONF_DIR" status --porcelain)" ]]; then
                log_step "Migrating repo checkout from ${HYPRCONF_COMPAT_BRANCH} to ${HYPRCONF_STABLE_BRANCH}..."
                if git -C "$HYPRCONF_DIR" checkout -B "$HYPRCONF_STABLE_BRANCH" HEAD \
                    >/dev/null 2>&1; then
                    git -C "$HYPRCONF_DIR" branch \
                        --set-upstream-to="origin/${HYPRCONF_STABLE_BRANCH}" \
                        "$HYPRCONF_STABLE_BRANCH" >/dev/null 2>&1 || true
                    current_branch="$HYPRCONF_STABLE_BRANCH"
                    upstream="origin/${HYPRCONF_STABLE_BRANCH}"
                    log_ok "Now tracking ${HYPRCONF_STABLE_BRANCH}."
                else
                    log_warn "Could not switch to ${HYPRCONF_STABLE_BRANCH} — staying on ${HYPRCONF_COMPAT_BRANCH}."
                fi
            else
                log_warn "Local changes detected — leaving branch on ${HYPRCONF_COMPAT_BRANCH} for now."
            fi
        fi

        if [[ "$current_branch" != "dev" && "$upstream" != "origin/dev" ]]; then
            _apply_repo_sparse_checkout
        fi

        if [[ -n "$upstream" ]]; then
            log_step "Updating hyprconf repo..."
            git -C "$HYPRCONF_DIR" pull --ff-only \
                || log_warn "Fast-forward pull failed — using existing files."
            log_ok "Repository ready."
        else
            log_ok "Repository ready (no upstream — skipping pull)."
        fi
    fi
}

install_oh_my_zsh() {
    if [ ! -d ~/.oh-my-zsh ]; then
        log_step "Installing Oh My Zsh..."
        export RUNZSH=no
        sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"
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

    log_ok "~/.zshrc configured."
}

update_zshenv() {
    # ~/.zshenv is sourced by ALL zsh invocations — including non-interactive SSH
    # sessions — so PATH must live here to make `hyprconf` reachable over SSH.
    touch "${ZSHENV}"
    grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' "${ZSHENV}" 2>/dev/null \
        || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${ZSHENV}"
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

setup_user_dirs() {
    log_step "Initialising XDG user directories..."
    xdg-user-dirs-update
    log_ok "XDG user directories ready."
}

force_stow_package() {
    local package="$1"
    local stow_dir="$2"
    local target_dir="$3"

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

    if ! stow -d "$stow_dir" -t "$target_dir" --no-folding --restow "$package" 2>/dev/null; then
        log_warn "Conflict in $package — backing up and retrying..."

        stow -d "$stow_dir" -t "$target_dir" --no-folding -D "$package" || true

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

        stow -d "$stow_dir" -t "$target_dir" --no-folding --restow "$package"
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
    chassis=$(< /sys/class/dmi/id/chassis_type 2>/dev/null) || chassis=""
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

detect_gpu_and_link_monitor_config() {
    log_step "Detecting device type for monitor config..."

    local monitors_conf="$HOME/.config/hypr/monitors.conf"
    local hypr_conf_dir="$STOW_DIR/hypr/.config/hypr"

    rm -f "$monitors_conf"

    if _is_desktop; then
        ln -sf "$hypr_conf_dir/pcMonitors.conf" "$monitors_conf"
        log_ok "Desktop detected — using pcMonitors.conf"
    else
        ln -sf "$hypr_conf_dir/laptopMonitors.conf" "$monitors_conf"
        log_ok "Laptop/portable detected — using laptopMonitors.conf"
        log_step "Enabling power-profiles-daemon..."
        if _in_chroot; then
            sudo systemctl enable power-profiles-daemon
        else
            sudo systemctl enable --now power-profiles-daemon
        fi
    fi
}

stow_all_packages() {
    log_step "Stowing all config packages..."

    local _stow_failures=()
    while IFS= read -r -d '' pkg; do
        local pkg_name; pkg_name=$(basename "$pkg")
        force_stow_package "$pkg_name" "$STOW_DIR" "$HOME" || _stow_failures+=("$pkg_name")
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

enable_services() {
    log_step "Configuring firewall (ufw)..."
    if _in_chroot; then
        # ufw default/enable invoke ufw-init which requires a live netfilter stack.
        # ufw's shipped defaults (DROP inbound, ACCEPT outbound) are already correct,
        # so just enable the service unit for first boot.
        sudo systemctl enable ufw
    else
        sudo ufw default deny incoming
        sudo ufw default allow outgoing
        sudo ufw enable
        sudo systemctl enable --now ufw
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

sync_services() {
    log_step "Enabling system services..."
    if _in_chroot; then
        sudo systemctl enable NetworkManager
        sudo systemctl enable bluetooth
        sudo systemctl enable ufw
    else
        sudo systemctl enable --now NetworkManager
        sudo systemctl enable --now bluetooth
        sudo systemctl enable --now ufw
    fi
    log_ok "Services enabled."
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
    log_step "Verifying Python module imports..."
    if python3 - <<'PY' 2>/dev/null
import sys, pathlib
sys.path.insert(0, str(pathlib.Path.home() / ".local" / "lib"))
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
        print_header "sync"
        log_step "Syncing configs..."
        clone_or_update_repo
        create_directories
        purge_broken_symlinks
        sync_vscode_theme_extensions
        stow_all_packages || true
        update_zshrc
        update_zshenv
        configure_zprofile
        sync_services
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
    install_yay
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
    enable_services
    sync_services
    reload_hyprland

    printf '\n%s  ✔ Setup complete. Restart your terminal or source your ~/.zshrc.%s\n\n' "$GR" "$RS"
}

main "$@"
