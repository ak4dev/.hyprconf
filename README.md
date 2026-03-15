# .hyprconf

Personal Hyprland dotfiles for Arch Linux, managed with [GNU Stow](https://www.gnu.org/software/stow/). Includes a one-shot bootstrap script, a GPU-aware monitor configuration system, and a full-desktop theme switcher covering 24 colour schemes.

---

## Features

- **One-command setup** — installs packages, sets up ZSH with Oh My Zsh + Powerlevel10k, stows all configs, and reloads Hyprland
- **`--sync` mode** — pull latest changes, re-stow, and re-apply all services without reinstalling packages; aliased to `hyprsync` in ZSH
- **GPU-aware monitor config** — auto-selects `pcMonitors.conf` (RTX 5090, HDR) or `laptopMonitors.conf` at setup time
- **Hot-swappable monitor presets** — keybinds to switch between bedroom/kitchen PC configurations on the fly
- **Screen lock & idle management** — hyprlock with blurred screenshot background; hypridle dims then locks then suspends; cliphist wiped on lock
- **Full-desktop theme switcher** — 24 themes applied simultaneously to Hyprland borders, Waybar, Kitty, Wofi, Dunst, VS Code, Firefox, GTK3/4, and wallpaper
- **Conflict-safe stowing** — existing files are backed up with timestamps before being replaced

---

## Requirements

- Arch Linux (uses `pacman`)
- A working Hyprland session (for `hyprctl reload` and keybinds)
- Git, `curl`, `stow` (installed by the script if needed)

---

## Installation

```bash
git clone https://github.com/ak4dev/.hyprconf ~/.hyprconf
bash ~/.hyprconf/setup.sh
```

The script will:
1. Update the system and install all packages from the `packages` file
2. Create required directories (`~/.config`, `~/.vscode-oss/extensions`, `~/Pictures`, `~/Downloads`, `~/wallpaper`)
3. Install Oh My Zsh and Powerlevel10k
4. Configure `~/.zshrc` (ZSH theme, plugins, aliases, fastfetch greeting)
5. Configure `~/.zprofile` to auto-start Hyprland on TTY1 login
6. Initialise XDG user directories (`~/Documents`, `~/Downloads`, etc.)
7. Stow all config packages into `$HOME`
8. Copy VS Code theme extensions and Firefox extension payloads
9. Auto-link the correct monitor config based on detected GPU
10. Enable and start `NetworkManager`, `bluetooth`, and `ufw` (deny inbound, allow outbound)
11. Disable `sddm`, enable `power-profiles-daemon` (laptop only)
12. Reload Hyprland

> **Note:** `bibata-cursor-theme` (set as `GTK_CURSOR_THEME`) is AUR-only and must be installed manually:
> ```bash
> yay -S bibata-cursor-theme
> ```

### Syncing after changes

```bash
hyprsync        # alias defined in ~/.zshrc
# or directly:
~/.hyprconf/setup.sh --sync
```

Sync pulls the latest repo, purges broken symlinks, re-stows packages, re-applies all services (`NetworkManager`, `bluetooth`, `ufw`), and reloads Hyprland — no package installation.

---

## Repository Layout

```
.hyprconf/
├── packages                  # Arch packages to install (one per line)
├── setup.sh                  # Bootstrap + sync script
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
│   │       ├── hyprlock.conf         # Lock screen config (blurred screenshot + clock)
│   │       ├── hypridle.conf         # Idle daemon (dim → lock → DPMS off → suspend)
│   │       ├── laptopMonitors.conf   # Laptop + external monitor layout
│   │       ├── pcMonitors.conf       # Desktop (RTX 5090, HDR) layout
│   │       ├── pcMonitors.bedroom    # Bedroom PC alternate layout
│   │       ├── pcMonitors.kitchen    # Kitchen PC alternate layout
│   │       └── scripts/
│   │           ├── switch_monitor.sh       # Hot-swap monitor preset
│   │           └── theme-switcher/
│   │               ├── switch_theme.py     # Theme application script
│   │               └── themes/             # 24 theme JSON files
│   ├── kitty/                # Kitty terminal config + theme files
│   ├── wallpaper/            # Wallpaper images
│   ├── waybar/               # Waybar bar config, CSS, and custom scripts
│   └── wofi/                 # Wofi launcher stylesheet
├── theme/
│   ├── firefox/extensions/   # Firefox theme extension payloads (.xpi)
│   └── .vscode-oss/extensions/  # VS Code theme extensions (Dracula, Gruvbox Material)
└── util/
    └── toggle-native-display # Toggle the built-in laptop screen on/off
```

---

## Packages Installed

| Category | Packages |
|---|---|
| Core | `base-devel`, `git`, `curl`, `wget`, `unzip`, `stow`, `pciutils`, `xdg-user-dirs` |
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
| Icons & themes | `papirus-icon-theme`, `kvantum`, `qt6ct` |
| GTK theme sync | `xsettingsd` |
| Fonts | `nerd-fonts` |
| Power management | `power-profiles-daemon` |
| Firewall | `ufw` |
| AUR (manual) | `bibata-cursor-theme` — `yay -S bibata-cursor-theme` |
| Optional (Nvidia) | `nvidia-utils` *(uncomment in `packages` if using an Nvidia GPU)* |

---

## Keybindings

`$mainMod` = **Super (Win)** key.

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
| `Super + Shift + 4` | Screenshot (region, hyprshot) |
| `Super + Shift + V` | Clipboard history picker (cliphist + wofi) |
| `Super + Shift + Backspace` | Toggle native laptop display |
| `Super + Shift + B` | Switch to bedroom monitor config |
| `Super + Shift + K` | Switch to kitchen monitor config |

---

## Theme Switcher

Launch from Wofi (search **"Theme"**) or from any terminal:

```bash
python3 ~/.config/hypr/scripts/theme-switcher/switch_theme.py
```

The script presents an interactive picker and applies the selected theme to:

- **Hyprland** — active/inactive border colours
- **Waybar** — full CSS colour variables
- **Kitty** — sourced theme file
- **Wofi** — generated `style.css`
- **Dunst** — notification frame and urgency colours
- **VS Code / Code OSS** — colour theme and font settings
- **Firefox** — installs matching theme extension
- **GTK 3 & 4** — `settings.ini` colour scheme hints
- **Wallpaper** — swaps via `hyprpaper` IPC

### Available Themes

| | | | |
|---|---|---|---|
| `ayu-dark` | `ayu-mirage` | `catppuccin-frappe` | `catppuccin-latte` |
| `catppuccin-macchiato` | `catppuccin-mocha` | `cyberdream` | `dracula` |
| `everforest-dark` | `gruvbox` | `kanagawa` | `monokai-pro` |
| `nord` | `one-dark` | `oxocarbon` | `palenight` |
| `rose-pine` | `rose-pine-dawn` | `rose-pine-moon` | `shades-of-purple` |
| `solarized-dark` | `tokyo-moon` | `tokyo-night` | `tokyo-storm` |

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

---

## Monitor Configuration

The setup script detects the GPU via `lspci` and symlinks the appropriate config to `~/.config/hypr/monitors.conf`:

| GPU detected | Config used |
|---|---|
| RTX 5090 | `pcMonitors.conf` — HDMI-A-1 4K@120Hz HDR + DP-3 4K rotated |
| Anything else | `laptopMonitors.conf` — eDP-1 1920×1200 + external displays |

Hot-swap presets (`pcMonitors.bedroom`, `pcMonitors.kitchen`) can be activated at runtime with `Super + Shift + B` / `Super + Shift + K`.

The `util/toggle-native-display` script toggles the built-in `eDP-1` panel on or off without restarting Hyprland (`Super + Shift + Backspace`).

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

- Oh My Zsh with `git` plugin
- Powerlevel10k theme (sourced from `~/powerlevel10k/`)
- `zsh-autosuggestions` and `zsh-syntax-highlighting`
- `hyprsync` alias → `~/.hyprconf/setup.sh --sync`
- `fastfetch` greeting with Arch logo on every new shell

It also writes to `~/.zprofile` to auto-start Hyprland on login at TTY1:

```zsh
[[ $(tty) == /dev/tty1 ]] && exec Hyprland
```

This replaces the need for a display manager (`sddm` is disabled by the setup script).
