<p align="center">
  <img src="assets/banner.svg" width="920" alt=".hyprconf" />
</p>

<p align="center">
  <a href="https://hyprconf.sh"><img alt="installer" src="https://img.shields.io/badge/installer-hyprconf.sh-0ea5e9?style=for-the-badge" /></a>
  <img alt="arch linux" src="https://img.shields.io/badge/arch-linux-1793d1?style=for-the-badge&logo=archlinux&logoColor=white" />
  <img alt="hyprland" src="https://img.shields.io/badge/hyprland-wayland-111827?style=for-the-badge&logo=wayland&logoColor=white" />
  <img alt="gnu stow" src="https://img.shields.io/badge/gnu%20stow-dotfiles-3a7f2e?style=for-the-badge&logo=gnu&logoColor=white" />
  <img alt="themes" src="https://img.shields.io/badge/themes-44-8b5cf6?style=for-the-badge" />
</p>

# .hyprconf

Personal Hyprland dotfiles for Arch Linux, managed with [GNU Stow](https://www.gnu.org/software/stow/). Includes a one-shot bootstrap script, a GPU-aware monitor configuration system, and a full-desktop theme switcher covering **44** colour schemes.

---

## Features

- **One-command setup** — installs packages, sets up ZSH with Oh My Zsh + Powerlevel10k, stows all configs, and reloads Hyprland
- **`hyprconf` CLI** — unified control centre: `hyprconf theme random`, `hyprconf sync`, `hyprconf monitor set bedroom`, and more
- **`--sync` mode** — pull latest changes, re-stow, and re-apply all services without reinstalling packages; run via `hyprconf sync`
- **GPU-aware monitor config** — auto-selects `pcMonitors.conf` (RTX 5090, HDR) or `laptopMonitors.conf` at setup time
- **Hot-swappable monitor presets** — keybinds to switch between bedroom/kitchen PC configurations on the fly
- **Screen lock & idle management** — hyprlock with blurred screenshot background; hypridle dims then locks then suspends; cliphist wiped on lock
- **Full-desktop theme switcher** — 44 themes applied simultaneously to Hyprland borders, Waybar, Kitty, Wofi, Dunst, VS Code / Code OSS, Firefox, GTK3/4, and wallpaper
- **Conflict-safe stowing** — existing files are backed up with timestamps before being replaced

---

## Requirements

- Arch Linux (uses `pacman`) — or the **Arch ISO** for a full install
- A working Hyprland session (for `hyprctl reload` and keybinds)
- Git, `curl`, `stow` (installed by the script if needed)

---

## Installation

```bash
bash <(curl -fsSL https://hyprconf.sh)
```

The installer displays the banner and prompts for one of two modes:

### [1] Full Arch Linux install  *(run from the Arch ISO)*

Prompts for: username, password (shared for user account + LUKS), hostname, timezone (auto-detected from IP, user-confirmed), target disk, and partition mode.

Most interactive choices support arrow-key navigation (↑/↓/Enter) when run in a TTY. If `dialog` or `fzf` is installed, the installer will use it automatically; otherwise it falls back to a built-in arrow selector or manual input. Free-space/ESP probing uses timeouts and will fail with a clear error instead of hanging.

The install:
1. Partitions the disk — **full disk** (wipe) or **unallocated space** (preserves existing partitions; detects existing EFI partitions and prompts you to reuse or create a new one)
2. Encrypts the root partition with LUKS2 (AES-XTS 512-bit)
3. Formats root as btrfs with subvolumes: `@` `/`, `@home` `/home`, `@snapshots` `/.snapshots`, `@var_log` `/var/log`
4. Installs base system via `pacstrap` (including CPU microcode, NetworkManager, ZSH)
5. Configures in chroot: locale (`en_US.UTF-8`), timezone, hostname, `mkinitcpio` with `systemd`+`sd-encrypt` hooks, `systemd-boot` with LUKS kernel parameters, user account, `sudo`, TTY1 auto-login
6. Pre-clones this repo into the new user's home and sets a first-boot hook in `~/.zprofile`

On first login after reboot, `setup.sh` runs automatically then Hyprland launches.

### [2] Dotfiles only  *(existing Arch system)*

Clones the repo and runs `setup.sh`:

1. Update the system and install all packages from the `packages` file
2. Create required directories (`~/.config`, `~/.vscode-oss/extensions`, `~/Pictures`, `~/Downloads`, `~/wallpaper`)
3. Install Oh My Zsh and Powerlevel10k (into `~/.oh-my-zsh/custom/themes/powerlevel10k`)
4. Configure `~/.zshrc` (ZSH theme, plugins, aliases, fastfetch greeting)
5. Configure `~/.zprofile` to auto-start Hyprland on TTY1 login
6. Initialise XDG user directories (`~/Documents`, `~/Downloads`, etc.)
7. Stow all config packages into `$HOME`
8. Copy VS Code theme extensions and Firefox extension payloads
9. Auto-link the correct monitor config based on detected GPU
10. Configure firewall: `ufw` deny inbound / allow outbound — then enable and start
11. Stop and disable `sddm` (display manager replaced by TTY auto-login)
12. Enable `power-profiles-daemon` (laptop only), `NetworkManager`, `bluetooth`
13. Reload Hyprland (skipped gracefully if not running)

> **Note:** `bibata-cursor-theme` (set as `GTK_CURSOR_THEME`) is AUR-only and must be installed manually:
> ```bash
> yay -S bibata-cursor-theme
> ```

### Syncing after changes

```bash
hyprconf sync        # canonical command
hyprsync             # backward-compatible alias (same thing)
```

Sync pulls the latest repo, purges broken symlinks, re-stows packages, re-applies all services (`NetworkManager`, `bluetooth`, `ufw`), and reloads Hyprland — no package installation.

---

## Repository Layout

```
.hyprconf/
├── packages                  # Arch packages to install (one per line)
├── setup.sh                  # Local bootstrap + sync entry point
│
├── assets/                   # Shared project assets (reused across scripts)
│   ├── banner.sh             # Canonical print_banner() — glitch palette + logo
│   └── banner.svg            # README header banner (colorized, alignment-safe)
│
├── docs/                     # Documentation
│   └── hyprland-reference.md # Hyprland config syntax cheatsheet
│
├── infra/                    # AWS cloud infrastructure management
│   ├── env.sh.example        # Configuration template (copy → env.sh, never commit)
│   ├── deploy.sh             # Idempotent: create/update S3 + CloudFront + ACM + Route53
│   └── teardown.sh           # Destroy all AWS resources (confirmation required)
│
├── install/                  # Bootstrap installer (served from S3 / CloudFront)
│   └── install.sh            # Self-contained; embeds banner from assets/banner.sh
│
├── scripts/                  # Project utility scripts
│   └── toggle-native-display # Toggle the built-in laptop screen on/off
│
├── stow/                     # GNU Stow packages (symlinked into $HOME)
│   ├── btop/                 # btop system monitor config
│   ├── code-oss/             # VS Code OSS base settings
│   ├── dunst/                # Dunst notification daemon config
│   ├── fastfetch/            # Fastfetch system info config
│   ├── hypr/                 # Hyprland config + scripts
│   │   └── .config/hypr/
│   │       ├── hyprland.conf         # Main config (animations, layout, env vars)
│   │       ├── keybinds.conf         # All keybindings
│   │       ├── gestures.conf         # Touchpad gesture settings
│   │       ├── hyprpaper.conf        # Wallpaper config
│   │       ├── hyprlock.conf         # Lock screen config
│   │       ├── hypridle.conf         # Idle daemon (dim → lock → DPMS → suspend)
│   │       ├── laptopMonitors.conf   # Laptop + external monitor layout
│   │       ├── pcMonitors.conf       # Desktop layout
│   │       ├── pcMonitors.bedroom    # Bedroom PC alternate layout
│   │       ├── pcMonitors.kitchen    # Kitchen PC alternate layout
│   │       └── scripts/
│   │           ├── switch_monitor.sh
│   │           └── theme-switcher/
│   │               ├── switch_theme.py
│   │               └── themes/       # Theme JSON files
│   │   └── .local/bin/
│   │       └── hyprconf              # Unified CLI → ~/.local/bin/hyprconf
│   ├── kitty/                # Kitty terminal config + theme files
│   ├── wallpaper/            # Wallpaper images
│   ├── waybar/               # Waybar bar config, CSS, and custom scripts
│   └── wofi/                 # Wofi launcher stylesheet
│
└── theme/                    # Vendor theme extension payloads (binary, not stowed)
    ├── firefox/extensions/   # Firefox theme .xpi files
    └── .vscode-oss/extensions/  # VS Code themes (Dracula, Gruvbox Material)
```

---

## Deploying the Install Endpoint

`install/install.sh` is served over HTTPS at `https://hyprconf.sh`, enabling:

```bash
bash <(curl -fsSL https://hyprconf.sh)
```

The AWS infrastructure (S3 + CloudFront + ACM + Route53) is managed via scripts in `infra/`.

### Forking / Deploying Your Own

1. Fork this repo and update `REPO_URL` in `install/install.sh` to point to your fork
2. Run `hyprconf deploy` (or `bash infra/deploy.sh`) — it will interactively prompt for all settings on first run and save them to `~/.config/hyprconf/infra.env` (never committed).
   - Deploy to an additional domain: `hyprconf deploy new` (saved under `~/.config/hyprconf/deployments/<domain>/`)
   - List configured deployments: `hyprconf deploy list`
   - Refresh an additional domain later: `hyprconf deploy <domain>`

| Variable | Description |
|---|---|
| `AWS_PROFILE` | Named AWS profile (or set `AWS_ACCESS_KEY_ID`/`SECRET`) |
| `AWS_DEFAULT_REGION` | Must be `us-east-1` (required for CloudFront ACM) |
| `HYPRCONF_DOMAIN` | Your custom domain (e.g. `hyprconf.yourdomain.com`) |
| `HYPRCONF_BUCKET` | S3 bucket name (globally unique, e.g. `hyprconf-yourdomain-com`) |
| `HYPRCONF_ZONE_ID` | Route53 hosted zone ID for the parent domain |
| `HYPRCONF_REPO` | Your fork's GitHub URL (auto-detected from git remote) |

The deploy script is idempotent — re-run at any time to refresh `install.sh` or resume after interruption. The deploy is also fully reversible:

```bash
hyprconf teardown   # destroys all AWS resources (requires domain confirmation)
```

> See `infra/env.sh.example` for a complete variable reference and CI/CD usage notes.



## Packages Installed

| Category | Packages |
|---|---|
| Core | `base-devel`, `git`, `curl`, `wget`, `unzip`, `vim`, `stow`, `pciutils`, `xdg-user-dirs` |
| Hyprland | `hyprland`, `hyprpaper`, `hyprshot`, `hyprlock`, `hypridle`, `xdg-desktop-portal-hyprland` |
| Audio | `pipewire`, `pipewire-pulse`, `pipewire-alsa`, `wireplumber`, `pavucontrol` |
| KDE Wallet | `kwallet`, `kwallet-pam` |
| Polkit | `polkit-kde-agent` |
| Terminal & shell | `kitty`, `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting`, `fastfetch` |
| Bar / Launcher | `waybar`, `wofi` |
| Notifications | `dunst` |
| Applications | `firefox`, `code`, `dolphin`, `htop`, `btop` |
| File manager support | `gvfs` |
| Clipboard | `cliphist`, `wl-clipboard` |
| Media & input | `playerctl`, `brightnessctl` |
| Bluetooth | `bluez`, `bluez-utils`, `blueman` |
| Networking | `networkmanager`, `network-manager-applet` |
| System monitoring | `upower`, `lm_sensors` |
| Python | `python` |
| Icons & themes | `papirus-icon-theme` |
| GTK theme sync | `xsettingsd` |
| Fonts | `nerd-fonts` |
| Power management | `power-profiles-daemon` |
| Firewall | `ufw` |
| AUR (manual) | `bibata-cursor-theme` — `yay -S bibata-cursor-theme` |
| Optional (Nvidia) | `nvidia-utils` *(uncomment in `packages` if using an Nvidia GPU)* |

---

## Keybindings

`$mainMod` defaults to **Super (Win)**.

Change it live (and persist locally):

```bash
hyprconf set mainMod ALT
```

This writes a machine-local override file at:
`~/.config/hypr/conf.d/99-hyprconf-local.conf`

### Applications

| Keybind | Action |
|---|---|
| `Super + T` | Open terminal (Kitty) |
| `Super + F` | Open browser (Firefox) |
| `Super + C` | Open editor (VS Code) |
| `Super + E` | Open file manager (Dolphin) |
| `Super + D` | Open app launcher (Wofi) |

### Window Management

| Keybind | Action |
|---|---|
| `Super + Q` | Close active window |
| `Super + Shift + Q` | Exit Hyprland |
| `Super + V` / `Super + Shift + Space` | Toggle floating |
| `Super + Shift + F` | Toggle fullscreen |
| `Super + P` | Toggle pseudo-tile |
| `Super + J` | Toggle split direction |
| `Super + ← ↑ ↓ →` | Move focus |
| `Super + Shift + ← ↑ ↓ →` | Resize active window |
| `Super + Shift + A` | Swap window left |
| `Super + Shift + D` | Swap window right |
| `Super + LMB drag` | Move window |
| `Super + RMB drag` | Resize window |

### Workspaces

| Keybind | Action |
|---|---|
| `Super + 1–0` | Switch to workspace 1–10 |
| `Super + F1 / F2` | Switch to workspace 3 / 4 |
| `Super + Shift + 1–0` | Move window to workspace 1–10 |
| `Super + M` | Toggle scratchpad |
| `Super + Shift + M` | Move window to scratchpad |
| `Super + Scroll` | Cycle workspaces |

### Media & System

| Keybind | Action |
|---|---|
| `XF86AudioRaiseVolume / LowerVolume` | Volume ±5% |
| `XF86AudioMute` | Toggle mute |
| `XF86AudioMicMute` | Toggle mic mute |
| `XF86MonBrightnessUp / Down` | Brightness ±5% (auto-detects backlight device) |
| `XF86AudioPlay / Pause / Next / Prev` | Media playback (playerctl) |
| `Super + L` | Lock screen (wipes clipboard, invokes hyprlock) |
| `Super + Shift + Escape` | Lock screen (alternative) |
| `Super + Shift + 4` | Screenshot (region, hyprshot) |
| `Super + Shift + V` | Clipboard history picker (cliphist + wofi) |
| `Super + Shift + Backspace` | Toggle native laptop display |
| `Super + Shift + B` | Switch to bedroom monitor config |
| `Super + Shift + K` | Switch to kitchen monitor config |

---

## hyprconf CLI

`hyprconf` is the unified control centre for the entire hyprconf suite. It is symlinked to `~/.local/bin/hyprconf` via GNU Stow and is available in every shell session.

```
hyprconf theme                   Interactive TUI picker
hyprconf theme <name>            Apply a specific theme
hyprconf theme random            Apply a random theme
hyprconf theme next / prev       Cycle themes (alphabetical)
hyprconf theme current           Show the active theme
hyprconf theme list              Pretty colour table of all themes
hyprconf theme pick              Select via wofi launcher
hyprconf theme filter <str>      Filter themes in TUI

hyprconf sync                    Pull latest configs and re-stow

hyprconf monitor list            List available monitor presets
hyprconf monitor set <preset>    Switch to a monitor preset
hyprconf monitor <preset>        Shorthand for 'set <preset>'

hyprconf display toggle          Toggle built-in screen (eDP-1) on/off

hyprconf deploy                  Deploy/refresh the default (legacy) cloud install endpoint on AWS
hyprconf deploy list             List configured deployments
hyprconf deploy new              Add + deploy an additional domain
hyprconf deploy <domain>         Deploy/refresh a previously added domain
hyprconf teardown                Destroy all AWS resources (confirmation required)

hyprconf set mainMod <KEY...>    Set $mainMod (e.g. SUPER, ALT, CTRL)

hyprconf help                    Show usage
```

---

## Theme Switcher

Launch via the CLI or directly from Wofi (search **"Theme"**):

```bash
hyprconf theme          # interactive TUI
hyprconf theme dracula  # apply directly
hyprconf theme random   # random pick
```

Or call the Python script directly:

```bash
python3 ~/.config/hypr/scripts/theme-switcher/switch_theme.py
```

The script presents an interactive picker (or use `--wofi` for inline Wofi selection) and applies the selected theme to:

- **Hyprland** — live border colours via `hyprctl keyword` + persistent `theme-colors.conf`
- **Waybar** — full CSS colour variables
- **Kitty** — sourced theme file (auto-generated from palette if no `kitty` key)
- **Wofi** — generated `style.css`
- **Dunst** — notification frame and urgency colours
- **hyprlock** — input-field and label colours
- **VS Code / Code OSS** — colour theme and font settings
- **Firefox** — installs matching theme extension
- **GTK 3 & 4** — `settings.ini` colour scheme hints
- **Qt / KDE apps** — `kdeglobals` colour scheme (read by `KDEPlasmaPlatformTheme6`, which ships with Dolphin's KDE Frameworks deps); covers Dolphin, Ark, Gwenview, and any other Qt app
- **Wallpaper** — swaps via `hyprpaper` IPC

### CLI Flags

These flags map directly to `hyprconf theme` subcommands:

| Flag | Short | `hyprconf theme` | Description |
|---|---|---|---|
| `--list` | `-l` | `list` | Print colour table of all themes |
| `--current` | `-c` | `current` | Print the currently active theme |
| `--next` | `-n` | `next` | Apply next theme (alphabetical) |
| `--prev` | `-p` | `prev` | Apply previous theme |
| `--random` | `-r` | `random` | Apply a random theme |
| `--wofi` | `-w` | `pick` | Pick via `wofi --dmenu` (no terminal) |
| `--filter STR` | `-f` | `filter <str>` | Pre-filter themes by substring |
| `--no-reload` | | *(pass `--no-reload` directly)* | Skip `hyprctl reload` after applying |

### Available Themes

**Community themes (24):**

| | | | |
|---|---|---|---|
| `ayu-dark` | `ayu-mirage` | `catppuccin-frappe` | `catppuccin-latte` |
| `catppuccin-macchiato` | `catppuccin-mocha` | `cyberdream` | `dracula` |
| `everforest-dark` | `gruvbox` | `kanagawa` | `monokai-pro` |
| `nord` | `one-dark` | `oxocarbon` | `palenight` |
| `rose-pine` | `rose-pine-dawn` | `rose-pine-moon` | `shades-of-purple` |
| `solarized-dark` | `tokyo-moon` | `tokyo-night` | `tokyo-storm` |

**AI-original themes (20) — prefix `ai:`:**

| Theme | Palette concept |
|---|---|
| `ai:void` | Near-black void with electric violet |
| `ai:phosphor` | CRT phosphor green on deep black |
| `ai:ember` | Charred black with smoldering orange |
| `ai:glacier` | Crisp ice-white light theme with steel blue |
| `ai:midnight-bloom` | Deep navy with exotic fuchsia |
| `ai:ash` | Cold grey ash with burning crimson |
| `ai:deep-sea` | Ocean trench black with teal-cyan |
| `ai:neon-noir` | Dark concrete with electric neon green |
| `ai:copper` | Warm dark brown with oxidized copper |
| `ai:steel` | Industrial blue-grey with electric blue |
| `ai:aurora` | Dark grey-navy with aurora green |
| `ai:bioluminescence` | Pitch black with glowing cyan organisms |
| `ai:solar-flare` | Near-black space with plasma orange |
| `ai:crimson-tide` | Deep ocean dark with blood crimson |
| `ai:forest-floor` | Earthy dark brown with moss green |
| `ai:lavender-haze` | Dark purple-grey with soft amethyst |
| `ai:obsidian` | Pure volcanic black with sharp amber |
| `ai:sakura` | Dark ink wash with cherry blossom pink |
| `ai:circuit` | PCB dark green with circuit-trace cyan |
| `ai:dusk` | Dark dusty purple with desert sunset orange |

> **Tip:** `ai:` themes auto-generate a Kitty colour config from their palette — no separate `.conf` file required. All `ai:` themes include a `vscode` block mapped to the closest matching community extension. Use `--filter ai:` to show only AI themes.

To add a new theme, create a JSON file in `stow/hypr/.config/hypr/scripts/theme-switcher/themes/` following the existing format:

```json
{
  "background": "#1e1e2e",
  "foreground": "#cdd6f4",
  "comment":    "#6c7086",
  "cyan":       "#89dceb",
  "green":      "#a6e3a1",
  "orange":     "#fab387",
  "pink":       "#f5c2e7",
  "purple":     "#cba6f7",
  "red":        "#f38ba8",
  "yellow":     "#f9e2af",
  "accent":     "#f5c2e7",
  "wallpaper":  "~/wallpaper/my-theme.png",
  "kitty":      "~/.config/kitty/themes/my-theme.conf",
  "vscode": {
    "theme":     "Theme Name",
    "extension": "publisher.extension-id",
    "font":      "JetBrainsMono Nerd Font"
  },
  "firefox": {
    "theme_name": "Theme Name",
    "theme_id":   "{extension-uuid}"
  }
}
```

> `kitty`, `vscode`, `firefox`, and `wallpaper` are all optional. If `kitty` is omitted, a theme conf is auto-generated from the palette colours.

---

## Monitor Configuration

The setup script detects the GPU via `lspci` and symlinks the appropriate config to `~/.config/hypr/monitors.conf`:

| GPU detected | Config used |
|---|---|
| RTX 5090 | `pcMonitors.conf` — HDMI-A-1 4K@120Hz HDR + DP-3 4K rotated |
| Anything else | `laptopMonitors.conf` — eDP-1 1920×1200 + external displays |

Hot-swap presets (`pcMonitors.bedroom`, `pcMonitors.kitchen`) can be activated at runtime with `Super + Shift + B` / `Super + Shift + K`.

The `scripts/toggle-native-display` script toggles the built-in `eDP-1` panel on or off without restarting Hyprland (`Super + Shift + Backspace`).

---

## Screen Lock & Idle

Configured via `hypridle.conf` (autostarted at login):

| Timeout | Action |
|---|---|
| 4 min | Dim display to 10% brightness |
| 5 min | Wipe clipboard history + lock screen (hyprlock) |
| 5 min 30 s | Turn displays off (DPMS) |
| 30 min | Suspend (`systemctl suspend`) |

The lock screen (`hyprlock.conf`) shows a blurred screenshot of the desktop, a live clock, and a password input field. Displays also turn off immediately before the system sleeps.

Lock manually at any time with `Super + L`.

---

## ZSH Configuration

The setup script idempotently appends to `~/.zshrc`:

- `~/.local/bin` prepended to `$PATH` (where `hyprconf` lives)
- Oh My Zsh with `git` plugin
- Powerlevel10k theme (sourced from `~/powerlevel10k/`)
- `zsh-autosuggestions` and `zsh-syntax-highlighting`
- `hyprsync` alias → `~/.hyprconf/setup.sh --sync` (backward-compat; prefer `hyprconf sync`)
- `fastfetch` greeting with Arch logo on every new shell

It also writes to `~/.zprofile` to auto-start Hyprland on login at TTY1:

```zsh
[[ $(tty) == /dev/tty1 ]] && { command -v start-hyprland >/dev/null && exec start-hyprland || exec Hyprland; }
```

This replaces the need for a display manager (`sddm` is disabled by the setup script).
