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

**hyprconf** is a Hyprland configuration suite for Arch Linux — combining a standalone CLI/TUI tool with the maintainer's fully-managed personal dotfiles. The tool is independently usable by any Hyprland user (AUR-compatible); the dotfiles are the daily-driven reference implementation built on top of it.

---

## Two Components

| Component | Description |
|---|---|
| **`hyprconf`** | AUR-compatible CLI + TUI for configuring Hyprland — get/set options, manage keybinds, rules, monitors, themes, lock/idle/wallpaper daemons, and more. Installable standalone. |
| **Dotfiles** | The maintainer's Arch Linux + Hyprland configuration, managed via GNU Stow. Bootstrapped from a single command; demonstrates and depends on `hyprconf`. |

---

## Features

- **`hyprconf` CLI** — unified control: `hyprconf theme random`, `hyprconf set general gaps_in 8`, `hyprconf keybind add`, `hyprconf monitor set bedroom`, `hyprconf configure` (IOS-style REPL), and more
- **`hyprconf tui`** — full-screen Textual TUI with arrow-selectable pickers for enums, interactive sliders for numeric fields, and mode lists fetched from `hyprctl`; covers all Hyprland config sections (general, decoration, animations, input, gestures, group, misc, binds, cursor, render, opengl, xwayland, dwindle, master and their subsections), plus keybinds, window/workspace rules, monitors, hyprlock, hypridle, hyprpaper, and a built-in theme picker
- **One-command setup** — installs packages (including `yay` AUR helper), configures ZSH, stows all configs, and launches Hyprland; full Arch ISO install supported
- **`hyprconf sync`** — pull latest changes, re-stow, and re-apply services without reinstalling packages
- **`hyprconf repair`** — scan and fix stow tree corruption, broken symlinks, Python import issues, and monitor config mismatches
- **Chassis-aware monitor config** — detects desktop vs laptop via DMI chassis type (`/sys/class/dmi/id/chassis_type`), falling back to battery absence; auto-selects `pcMonitors.conf` or `laptopMonitors.conf` at setup
- **Hardware auto-detection** — touchscreen devices get `wvkbd` (AUR on-screen keyboard, auto-shows on text focus; toggle: `Super+Shift+O`); accelerometer/gyroscope devices get `iio-sensor-proxy` + `autorotate` (maps orientation → Hyprland transform); both re-evaluated on every `hyprconf sync`
- **Hot-swappable monitor presets** — switch between bedroom/kitchen layouts at runtime via keybind
- **Full-desktop theme switcher** — 44 themes applied simultaneously to Hyprland borders, Waybar, Kitty, Wofi, Dunst, VS Code / Code OSS, Firefox, GTK3/4, Qt/KDE apps, and wallpaper
- **Privacy-hardened Firefox** — out-of-the-box enterprise `policies.json`: all telemetry disabled, vertical tabs enabled, uBlock Origin force-installed; comprehensive `user.js` privacy prefs applied on every theme switch
- **Screen lock & idle** — hyprlock (blurred screenshot), hypridle (dim → lock → DPMS → suspend), clipboard wiped on lock
- **Cloud deploy** — serve your own install endpoint via `hyprconf deploy` (S3 + CloudFront + ACM + Route53)

---

## Requirements

- Arch Linux (uses `pacman`) — or the **Arch ISO** for a full install
- Git, `curl`, `stow` (installed by the script if needed)
- A running Hyprland session (for live `hyprctl` features)

---

## Installation

```bash
bash <(curl -fsSL hyprconf.sh)
```

The installer prompts for one of two modes:

### [1] Full Arch Linux install *(from the Arch ISO)*

Prompts for username, password, hostname, timezone (auto-detected), network config carry-over, target disk, and partition mode. Then:

1. Partitions disk — **full wipe** or **unallocated space** (preserves existing partitions; reuses or creates EFI)
2. LUKS2 encryption (AES-XTS 512-bit) on root
3. btrfs with subvolumes: `@` `/`, `@home` `/home`, `@snapshots` `/.snapshots`, `@var_log` `/var/log`
4. `pacstrap` — base system, CPU microcode, NetworkManager, ZSH
5. Chroot config: locale, timezone, hostname, `mkinitcpio` (systemd + sd-encrypt), `systemd-boot`, user account, TTY1 auto-login
6. Pre-clones repo; first-boot hook runs `setup.sh` automatically on login

### [2] Dotfiles only *(existing Arch system)*

Clones the repo from the stable release branch using a sparse checkout and runs `setup.sh`:

1. System update + package install from `packages`
2. Create required directories
3. Oh My Zsh + Powerlevel10k
4. `~/.zshrc` (plugins, aliases, fastfetch greeting) + `~/.zprofile` (Hyprland auto-start on TTY1)
5. Stow all packages into `$HOME`
6. VS Code theme extensions + Firefox extension payloads
7. Firefox enterprise policies (`/etc/firefox/policies/policies.json`): telemetry disabled, uBlock Origin installed
8. Chassis-type-aware monitor config symlink (DMI → desktop vs laptop)
9. Hardware feature detection: touchscreen → installs `wvkbd` (AUR) + writes `conf.d/60-hardware.conf`; accelerometer → installs + enables `iio-sensor-proxy`
10. `ufw` deny-inbound / allow-outbound; enable + start
11. Disable `sddm`; enable `NetworkManager`, `bluetooth`, `power-profiles-daemon`
11. Reload Hyprland

> **AUR dependency:** `bibata-cursor-theme` must be installed manually: `yay -S bibata-cursor-theme`

### Sync / Repair

```bash
hyprconf sync     # pull, re-stow, re-apply services, reload Hyprland
hyprconf repair   # fix stow tree, broken symlinks, Python imports, monitors.conf
hyprsync          # backward-compatible alias for hyprconf sync
```

`hyprconf sync` keeps normal user installs on the sparse `stable` checkout. During migration, clean legacy `mainline` clones are re-pointed to `stable` automatically.

---

## Repository Layout

```
.hyprconf/
├── packages                  # Arch packages to install (one per line, comments ok)
├── setup.sh                  # Local bootstrap + sync entry point
│
├── assets/                   # Shared project assets
│   ├── banner.sh             # print_banner() — glitch palette + logo
│   └── banner.svg            # README header banner
│
├── docs/
│   └── hyprland-reference.md # Hyprland config syntax cheatsheet
│
├── infra/                    # AWS cloud infrastructure (S3 + CloudFront + ACM + Route53)
│   ├── env.sh.example        # Config template (copy → env.sh, never commit)
│   ├── deploy.sh             # Idempotent create/update
│   └── teardown.sh           # Destroy all resources (confirmation required)
│
├── install/
│   └── install.sh            # Self-contained installer (served from CloudFront)
│
├── scripts/
│   └── publish               # Run tests, deploy, promote dev → stable, build release archive
│
└── stow/                     # GNU Stow packages — symlinked into $HOME
    ├── hypr/
    │   ├── .config/hypr/
    │   │   ├── hyprland.conf           # Animations, layout, env vars
    │   │   ├── keybinds.conf           # All keybindings
    │   │   ├── gestures.conf
    │   │   ├── hyprpaper.conf
    │   │   ├── hyprlock.conf
    │   │   ├── hypridle.conf
    │   │   ├── laptopMonitors.conf
    │   │   ├── pcMonitors.conf / .bedroom / .kitchen
    │   │   ├── conf.d/
    │   │   │   ├── 00-hyprconf.conf        # Source guard (includes conf.d glob)
    │   │   │   └── 99-hyprconf-local.conf  # Machine-local overrides (hyprconf set)
    │   │   └── scripts/
    │   │       ├── hyprconf-tui/main.py    # Textual TUI
    │   │       ├── switch_monitor.sh
    │   │       ├── toggle-native-display   # Toggle built-in laptop screen (eDP-1)
    │   │       └── theme-switcher/
    │   │           ├── switch_theme.py
    │   │           └── themes/             # Theme JSON files
    │   └── .local/
    │       ├── bin/hyprconf               # CLI entry point → ~/.local/bin/
    │       └── lib/hyprconf/              # Shared Python library
    │           ├── schema.py              # OPTION_SCHEMA — all Hyprland keys + types + defaults
    │           ├── config.py              # Read/write 99-hyprconf-local.conf
    │           ├── hyprctl.py             # hyprctl IPC wrapper
    │           ├── autodetect.py          # First-run config migration
    │           ├── cli.py                 # Python CLI backend
    │           ├── file_edit.py           # Atomic file operations
    │           ├── block_conf.py          # Generic block-format config parser
    │           ├── keybinds.py            # Keybind read/write
    │           ├── rules.py               # Window/workspace rule read/write
    │           ├── monitors.py            # Monitor config read/write
    │           ├── hyprlock.py            # hyprlock block read/write
    │           ├── hypridle.py            # hypridle block read/write
    │           ├── hyprpaper.py           # hyprpaper read/write
    │           └── __init__.py
    ├── btop/   kitty/   dunst/   fastfetch/   code-oss/
    ├── waybar/ wallpaper/
    └── theme/                  # Vendor extension payloads (not stowed)
        ├── firefox/extensions/
        └── .vscode-oss/extensions/
├── infra/
│   ├── firefox/policies.json   # Enterprise policies (telemetry off, uBlock Origin)
│   └── ...                     # Deploy / VM infra scripts
```

---

## hyprconf CLI

The `hyprconf` script lives at `~/.local/bin/hyprconf` (stowed). It is the single entry point for all configuration tasks.

### Command Reference

```
# Themes
hyprconf theme                   Interactive TUI picker
hyprconf theme <name>            Apply a specific theme
hyprconf theme random / next / prev / current / list
hyprconf theme pick              Select via hyprlauncher
hyprconf theme filter <str>      Filter themes in TUI

# Hyprland options (persistent + live via hyprctl)
hyprconf get [section] [key]
hyprconf set <section> <key> <value>
hyprconf set mainMod <key>        Change the main modifier key

# Interactive Cisco IOS-style REPL
hyprconf configure / conf         Enter configure mode
#   general                      Enter section context
#   gaps_in 8                    Set option
#   no gaps_in                   Reset to default
#   show / ? / exit

# Keybinds
hyprconf keybind list / add / delete / update
hyprconf show keybinds           Pretty table from config

# Window & workspace rules
hyprconf rule window  list / add / delete / update
hyprconf rule workspace list / add / delete

# Monitor presets
hyprconf monitor list / <preset> / set <preset>
hyprconf monitor config list / set <name> <res> <pos> <scale> [extras…] / delete <name>

# Display
hyprconf display toggle          Toggle eDP-1 on/off

# Lock screen (hyprlock)
hyprconf lock list / add / set / delete

# Idle daemon (hypridle)
hyprconf idle list / add / set / delete

# Wallpaper daemon (hyprpaper)
hyprconf paper list
hyprconf paper set-wallpaper <monitor|-> <path>
hyprconf paper add-preload <path>
hyprconf paper delete-wallpaper <index>
hyprconf paper delete-preload <index>
hyprconf paper setting <key> <value>

# Full Textual TUI
hyprconf tui
hyprconf tui --section general
hyprconf tui --slim

# Sync / repair
hyprconf sync
hyprconf repair

# Cloud deploy
hyprconf deploy [list | new | <domain>]
hyprconf teardown

# Schema (for AI/tooling)
hyprconf schema dump / validate / list-sections / keys <section>
hyprconf autodetect              Detect + migrate existing config

# Hardware
hyprconf hardware status         Show detected hardware and daemon status
hyprconf hardware osk [on|off|toggle]  Control on-screen keyboard (wvkbd)
hyprconf hardware rotate <on|off>      Control auto-rotation (autorotate)

hyprconf help
```

### Persistence

All changes via `hyprconf set`, `hyprconf configure`, or the TUI are applied immediately via `hyprctl keyword` and written persistently to:

```
~/.config/hypr/conf.d/99-hyprconf-local.conf
```

This file is sourced by Hyprland on every restart via the `conf.d/*.conf` glob.

---

## Theme Switcher

```bash
hyprconf theme          # interactive TUI
hyprconf theme dracula  # apply directly
hyprconf theme random   # random pick
```

Themes are applied simultaneously to: Hyprland borders · Waybar CSS · Kitty · Wofi · Dunst · hyprlock · VS Code / Code OSS · Firefox · GTK 3 & 4 · Qt/KDE apps (`kdeglobals`) · wallpaper.

### Theme Flags

| Flag | Equivalent | Description |
|---|---|---|
| `--list` / `-l` | `theme list` | Print colour table |
| `--current` / `-c` | `theme current` | Show active theme |
| `--next` / `-n` | `theme next` | Next alphabetically |
| `--prev` / `-p` | `theme prev` | Previous |
| `--random` / `-r` | `theme random` | Random pick |
| `--pick` / `-w` | `theme pick` | Hyperlauncher picker |
| `--filter STR` / `-f` | `theme filter <str>` | Substring filter |
| `--no-reload` | | Skip `hyprctl reload` |

### Available Themes

**Community (24):**

| | | | |
|---|---|---|---|
| `ayu-dark` | `ayu-mirage` | `catppuccin-frappe` | `catppuccin-latte` |
| `catppuccin-macchiato` | `catppuccin-mocha` | `cyberdream` | `dracula` |
| `everforest-dark` | `gruvbox` | `kanagawa` | `monokai-pro` |
| `nord` | `one-dark` | `oxocarbon` | `palenight` |
| `rose-pine` | `rose-pine-dawn` | `rose-pine-moon` | `shades-of-purple` |
| `solarized-dark` | `tokyo-moon` | `tokyo-night` | `tokyo-storm` |

**AI-original (20) — prefix `ai:`:**

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

> `ai:` themes auto-generate a Kitty colour config from their palette. All include a `vscode` block mapped to the nearest community extension. Use `--filter ai:` to show only AI themes.

### Adding a Theme

Create a JSON file in `stow/hypr/.config/hypr/scripts/theme-switcher/themes/`:

```json
{
  "background": "#1e1e2e",
  "foreground": "#cdd6f4",
  "comment":    "#6c7086",
  "accent":     "#f5c2e7",
  "wallpaper":  "~/wallpaper/my-theme.png",
  "kitty":      "~/.config/kitty/themes/my-theme.conf",
  "vscode":  { "theme": "Theme Name", "extension": "publisher.id", "font": "JetBrainsMono Nerd Font" },
  "firefox": { "theme_name": "Theme Name", "theme_id": "{uuid}" }
}
```

`kitty`, `vscode`, `firefox`, and `wallpaper` are all optional.

---

## Monitor Configuration

| Device type detected | Config symlinked |
|---|---|
| Desktop (chassis type 3–7, 13, 24) | `pcMonitors.conf` — HDMI-A-1 4K@120Hz HDR + DP-3 4K rotated |
| Laptop / portable (all other types) | `laptopMonitors.conf` — eDP-1 1920×1200 + external |
| Unknown chassis (fallback) | No battery present → desktop; battery present → laptop |

Hot-swap presets activate at runtime via keybind or `hyprconf monitor set <preset>`:

| Keybind | Preset |
|---|---|
| `Super + Shift + B` | `pcMonitors.bedroom` |
| `Super + Shift + K` | `pcMonitors.kitchen` |

---

## Hardware Auto-Detection

Runs at every `setup.sh` invocation and `hyprconf sync`. Results are written to
`~/.config/hypr/conf.d/60-hardware.conf` (machine-local, not stowed).

### Touchscreen

Detection (checked in order):
1. `/sys/class/input/*/device/uevent` → `ID_INPUT_TOUCHSCREEN=1` — standard HID touchscreens (ELAN, etc.)
2. Same path → `NAME="Wacom * Finger"` + `PHYS="i2c-*"` — Wacom I2C pen+touch digitizers (ThinkPad Yoga, Surface-style devices) whose driver bypasses the generic udev HID rules and never sets `ID_INPUT_TOUCHSCREEN=1`

Installs **`wvkbd`** (AUR, requires `yay`) — a minimal wlroots on-screen keyboard.

| Behaviour | Detail |
|---|---|
| Auto-show | Appears when a text input is focused (`text-input-v3` protocol) |
| Manual toggle | `Super + Shift + O` |
| Theme integration | `hyprconf theme` writes `~/.config/wvkbd/colors` and restarts the daemon |

### Accelerometer / Auto-Rotation

Detection: `/sys/bus/iio/devices/*/in_accel_x_raw`

Installs **`iio-sensor-proxy`** (official repos) and enables `iio-sensor-proxy.service`.
The `autorotate` daemon watches `monitor-sensor` events and applies the matching
Hyprland transform to the built-in display (`eDP-*`):

| Sensor orientation | Hyprland transform |
|---|---|
| normal | 0 (0°) |
| left-up | 1 (90°) |
| bottom-up | 2 (180°) |
| right-up | 3 (270°) |

---

## Screen Lock & Idle

| Timeout | Action |
|---|---|
| 4 min | Dim display to 10% |
| 5 min | Wipe clipboard + lock (hyprlock) |
| 5 min 30 s | Displays off (DPMS) — 30 s after lock |
| 30 min | Suspend (`systemctl suspend`) |

Lock manually: `Super + L` or `Super + Shift + Escape`.

hyprlock shows a blurred desktop screenshot, live clock, and password input.

---

## Packages

| Category | Packages |
|---|---|
| Core | `base-devel`, `git`, `curl`, `wget`, `unzip`, `vim`, `stow`, `pciutils`, `xdg-user-dirs` |
| Hyprland | `hyprland`, `hyprpaper`, `hyprshot`, `hyprlock`, `hypridle`, `xdg-desktop-portal-hyprland` |
| Audio | `pipewire`, `pipewire-pulse`, `pipewire-alsa`, `wireplumber`, `pavucontrol` |
| KDE Wallet | `kwallet`, `kwallet-pam` |
| Polkit | `hyprpolkitagent` |
| Terminal & shell | `kitty`, `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting`, `fastfetch` |
| Bar / Launcher | `waybar`, `hyprlauncher` |
| Notifications | `dunst` |
| Applications | `firefox`, `code`, `dolphin`, `htop`, `btop` |
| Clipboard | `cliphist`, `wl-clipboard` |
| Media & input | `playerctl`, `brightnessctl` |
| Bluetooth | `bluez`, `bluez-utils`, `blueman` |
| Networking | `networkmanager`, `network-manager-applet` |
| System monitoring | `upower`, `lm_sensors` |
| Python | `python`, `python-textual` |
| File manager support | `gvfs` |
| Icons & themes | `papirus-icon-theme` |
| GTK sync | `xsettingsd` |
| Fonts | `ttf-jetbrains-mono-nerd` |
| Power management | `power-profiles-daemon` |
| Firewall | `ufw` |
| AUR (manual) | `bibata-cursor-theme` — `yay -S bibata-cursor-theme` *(yay is installed automatically during full setup)* |
| Optional (Nvidia) | `nvidia-utils` *(uncomment in `packages` if needed)* |

---

## Keybindings

`$mainMod` is **Super (Win)**. Change it persistently: `hyprconf set mainMod ALT`

All bindings live in `stow/hypr/.config/hypr/keybinds.conf`.

### Applications

| Keybind | Action |
|---|---|
| `Super + T` | Terminal (Kitty) |
| `Super + F` | Browser (Firefox) |
| `Super + C` | Editor (VS Code) |
| `Super + E` | Files (Dolphin) |
| `Super + D` | Launcher (Wofi) |

### Window Management

| Keybind | Action |
|---|---|
| `Super + Q` | Close window |
| `Super + Shift + Q` | Exit Hyprland |
| `Super + V` / `Super + Shift + Space` | Toggle floating |
| `Super + Shift + F` | Toggle fullscreen |
| `Super + P` | Toggle pseudo-tile |
| `Super + J` | Toggle split direction |
| `Super + ← ↑ ↓ →` | Move focus |
| `Super + Shift + ← ↑ ↓ →` | Resize window |
| `Super + Shift + A / D` | Swap window left / right |
| `Super + Shift + W / S` | Swap window up / down |
| `Super + LMB drag` | Move window |
| `Super + RMB drag` | Resize window |

### Workspaces

| Keybind | Action |
|---|---|
| `Super + 1–0` | Switch to workspace 1–10 |
| `Super + F1 / F2` | Workspace 3 / 4 |
| `Super + Shift + 1–0` | Move window to workspace |
| `Super + M` | Toggle scratchpad |
| `Super + Shift + M` | Move to scratchpad |
| `Super + Scroll` | Cycle workspaces |

### Media & System

| Keybind | Action |
|---|---|
| `XF86AudioRaiseVolume / LowerVolume` | Volume ±5% |
| `XF86AudioMute / MicMute` | Toggle mute / mic mute |
| `XF86MonBrightnessUp / Down` | Brightness ±5% |
| `XF86AudioPlay / Pause / Next / Prev` | Media playback |
| `Super + L` | Lock screen |
| `Super + Shift + Escape` | Lock screen (alt) |
| `Super + Shift + 4` | Screenshot region |
| `Super + Shift + V` | Clipboard history (cliphist + hyprlauncher) |
| `Super + Shift + Backspace` | Toggle native display (eDP-1) |
| `Super + Shift + B` | Bedroom monitor preset |
| `Super + Shift + K` | Kitchen monitor preset |

---

## ZSH

`setup.sh` idempotently configures `~/.zshrc`:

- `~/.local/bin` prepended to `$PATH`
- Oh My Zsh + `git` plugin, Powerlevel10k theme
- `zsh-autosuggestions`, `zsh-syntax-highlighting`
- `hyprsync` alias → `hyprconf sync` (backward-compat)
- `fastfetch` greeting on every shell

`~/.zprofile` auto-starts Hyprland on TTY1 login (replaces `sddm`).

---

## Cloud Deploy

`install/install.sh` is served over HTTPS at `https://hyprconf.sh` via S3 + CloudFront + ACM + Route53, managed in `infra/`.

```bash
hyprconf deploy          # deploy/refresh default endpoint
hyprconf deploy new      # add + deploy a new domain
hyprconf deploy list     # list configured deployments
hyprconf deploy <domain> # refresh an additional domain
hyprconf teardown        # destroy all AWS resources
```

Config is stored at `~/.config/hyprconf/infra.env` (never committed). See `infra/env.sh.example` for all variables.

| Variable | Description |
|---|---|
| `AWS_PROFILE` | Named AWS profile |
| `AWS_DEFAULT_REGION` | Must be `us-east-1` (CloudFront ACM) |
| `HYPRCONF_DOMAIN` | Custom domain (e.g. `hyprconf.sh`) |
| `HYPRCONF_BUCKET` | S3 bucket name (globally unique) |
| `HYPRCONF_ZONE_ID` | Route53 hosted zone ID |
| `HYPRCONF_REPO` | Fork's GitHub URL |

## Testing

hyprconf uses a **5-tier test architecture**. Tiers 1–3 require only Python and run without a Hyprland session; Tiers 4–5 are opt-in and require KVM.

```
tests/
├── conftest.py              # shared fixtures (isolated config dirs, mock hyprctl)
├── unit/                    # Tier 1 — pure Python, no Hyprland (611 tests)
│   ├── test_config.py
│   ├── test_schema.py
│   ├── test_file_edit.py
│   ├── test_block_conf.py
│   ├── test_keybinds.py
│   ├── test_rules.py
│   ├── test_monitors.py
│   ├── test_hyprlock.py
│   ├── test_hypridle.py
│   └── test_hyprpaper.py
├── integration/             # Tier 2 — Python CLI layer with mock hyprctl
│   └── test_cli_get_set.py
├── tui/                     # Tier 3 — Textual Pilot (headless, no terminal needed)
│   └── test_tui_basic.py
├── vm/                      # Tier 4 — live Hyprland in QEMU/KVM (opt-in, 42 tests)
│   ├── run_vm.sh            # QEMU launch script (virtio-gpu-gl, SSH port 2222)
│   └── test_hyprland_integration.py
└── install/                 # Tier 5 — full Arch install smoke test (opt-in, 9 tests)
    ├── arch.pkr.hcl         # Packer template — builds image using real install.sh
    ├── build_image.sh       # Packer build + move image + write .meta (date, commit)
    ├── run_install_vm.sh    # QEMU launch script (COW overlay, SSH port 2223)
    └── test_full_install.py
```

**Run tests:**

```bash
# Tier 1 — unit tests (fastest, no deps beyond pytest)
pytest tests/unit/

# Tier 2 — integration tests (mock hyprctl)
pytest tests/integration/

# Tier 3 — TUI tests (requires python-pytest-asyncio + python-textual)
pytest tests/tui/

# Tiers 1–3 together with coverage
pytest tests/unit/ tests/integration/ tests/tui/ --cov=stow/hypr/.local/lib/hyprconf

# Tier 4 — live Hyprland in QEMU (requires KVM; sudo modprobe kvm_amd first)
bash tests/vm/run_vm.sh           # start VM, wait for SSH
pytest tests/vm/ --run-vm -v

# Tier 5 — full Arch install smoke test
# Option A: use an existing image (fast — skips install.sh, validates post-install state)
bash tests/install/build_image.sh   # first time only; ~20 min — tests install.sh end-to-end
bash tests/install/run_install_vm.sh
pytest tests/install/ --run-install -v

# Option B: rebuild and test install.sh on every run
bash tests/install/build_image.sh   # ~20 min; requires packer + KVM
bash tests/install/run_install_vm.sh
pytest tests/install/ --run-install -v

# scripts/publish prompts automatically — no need to manage the VM manually

# Convenience via Makefile
make test            # Tiers 1–3
make test-vm         # Tier 4 (VM must be running)
make test-install    # Tier 5 (image must be built)
make build-vm-image  # runs build_image.sh
```

**Tier 5 install image** — `build_image.sh` runs Packer to build a full Arch+hyprconf image (exercising `install.sh` end-to-end) and writes `tests/vm/arch-hyprconf.meta` with the build date and commit. The VM launches on port 2223 via `run_install_vm.sh` using a **COW overlay**, so the base image is never dirtied by test runs. `scripts/publish` detects the image, shows its metadata, and prompts: _use existing_ (fast validation only) or _rebuild_ (re-runs `install.sh` via Packer, ~20 min).

**Key fixtures** (`tests/conftest.py`):
- `hypr_dir` — isolated `~/.config/hypr` in a `tmp_path`, monkeypatches all 9 module-level path constants so each test gets a clean slate
- `mock_hyprctl` — patches `subprocess.run` with canned JSON responses; tests pass even without `HYPRLAND_INSTANCE_SIGNATURE`

**CI** (`.github/workflows/test.yml`): Tiers 1–3 run on every push/PR via GitHub Actions. Tiers 4–5 require a self-hosted runner with KVM.

**Test packages** (`packages`): `python-pytest`, `python-pytest-asyncio`, `python-coverage`

---

## Developer Workflow

### Branches

| Branch | Purpose |
|--------|---------|
| `dev` | All active development — tests, docs, scripts, configs |
| `stable` | Release-ready source branch with normal shared git history |
| `mainline` | Temporary compatibility mirror of `stable` during migration |

The long-term model is `dev` → `stable` with shared history. User installs no longer depend on a filtered branch; they use a sparse checkout of `stable`, and release archives are exported from the same commit. `mainline` remains only as a migration bridge and mirrors `stable` while older installs are moved over.

### Publishing to stable

```bash
bash scripts/publish
```

`scripts/publish` handles the full pipeline automatically:
1. Verifies `dev` branch with a clean working tree
2. Starts the tier-4 test VM if not already running (stops it when done)
3. Runs tiers 1–4 (abort on any failure)
4. **Tier 5 — install image detection**: checks for `tests/vm/arch-hyprconf.qcow2`; if found, displays its build date and commit, then prompts:
   - **Use existing** — skip `install.sh` re-execution, run post-install validation (~fast)
   - **Rebuild** — re-run Packer to exercise `install.sh` end-to-end (~20 min)
   - If no image exists, builds automatically (no prompt)
5. Starts the tier-5 VM on port 2223 via COW overlay; stops it on exit
6. Deploys to `hyprconf.sh` via `hyprconf deploy hyprconf.sh`
7. Builds a filtered release archive from `HEAD` using `git archive` + `.gitattributes`
8. Pushes `HEAD` to `origin/stable`
9. Mirrors the same commit to `origin/mainline` during migration (unless disabled)
10. Creates and pushes the annotated tag `v<hyprconf.__version__>` unless it already points at `HEAD`

Files excluded from the release archive: `tests/` `scripts/` `.github/` `AGENTS.md` `Makefile` `pyproject.toml`

| Flag | Effect |
|------|--------|
| `--skip-tests` | Skip the test suite |
| `--skip-deploy` | Skip the deploy step |
| `--skip-tag` | Skip annotated release-tag creation |
| `--skip-compat` | Do not mirror `stable` to `mainline` |
| `--dry-run` | Build the release archive locally but do not push branches/tags |
