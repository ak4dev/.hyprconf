<p align="center">
  <img src="assets/banner.svg" width="920" alt=".hyprconf" />
</p>

<p align="center">
  <a href="https://hyprconf.sh"><img alt="installer" src="https://img.shields.io/badge/installer-hyprconf.sh-0ea5e9?style=for-the-badge" /></a>
  <img alt="arch linux" src="https://img.shields.io/badge/arch-linux-1793d1?style=for-the-badge&logo=archlinux&logoColor=white" />
  <img alt="hyprland" src="https://img.shields.io/badge/hyprland-wayland-111827?style=for-the-badge&logo=wayland&logoColor=white" />
  <img alt="gnu stow" src="https://img.shields.io/badge/gnu%20stow-dotfiles-3a7f2e?style=for-the-badge&logo=gnu&logoColor=white" />
  <img alt="themes" src="https://img.shields.io/badge/themes-68-8b5cf6?style=for-the-badge" />
</p>

<p align="center">
  <img src="assets/hyprconf.png" width="920" alt=".hyprconf desktop and TUI" />
</p>

# .hyprconf

**hyprconf** is a Hyprland configuration suite for Arch Linux — combining a standalone TUI with the maintainer's fully-managed personal dotfiles. The tool is independently usable by any Hyprland user (AUR-compatible); the dotfiles are the daily-driven reference implementation built on top of it.

---

## Two Components

| Component | Description |
|---|---|
| **`hyprconf`** | AUR-compatible TUI for configuring Hyprland — edit options, keybinds, rules, monitors, themes, lock/idle/wallpaper daemons, and more. Installable standalone. |
| **Dotfiles** | The maintainer's Arch Linux + Hyprland configuration, managed via GNU Stow. Bootstrapped from a single command; demonstrates and depends on `hyprconf`. |

---

## Features

- **`hyprconf` TUI** — full-screen Textual TUI with arrow-selectable pickers for enums, interactive sliders for numeric fields, and mode lists fetched from `hyprctl`; covers all Hyprland config sections (general, decoration, animations, input, gestures, group, misc, binds, cursor, render, opengl, xwayland, dwindle, master and their subsections), plus keybinds, window/workspace rules, monitors, hyprlock, hypridle, hyprpaper, and a built-in theme picker
- **One-command setup** — installs packages (official repos only — **never** the AUR), configures ZSH, stows all configs, and launches Hyprland; full Arch ISO install supported
- **`setup.sh --sync`** (alias `hyprsync`) — pull latest changes, re-stow, and re-apply services without reinstalling packages; `--force` to hard-reset a diverged branch, `--full` to restow all dotfiles
- **Chassis-aware monitor config** — detects desktop vs laptop via DMI chassis type (`/sys/class/dmi/id/chassis_type`), falling back to battery absence; auto-selects `pcMonitors.lua` or `laptopMonitors.lua` at setup
- **Automatic power profile switching** — on battery devices, a udev rule triggers `hyprconf-power-monitor` on AC plug/unplug, and the session applies the right profile at login (power-profiles-daemon starts each boot on its own default, and udev only fires on *changes*). Defaults to `performance` on AC and `power-saver` on battery, falling back to what the machine actually offers — many laptops expose no `performance`. `hyprconf-power-monitor set <profile>` applies a profile **and remembers it for the current power state**, so choosing `balanced` on battery survives the next unplug instead of being overridden; `hyprconf-power-monitor status` shows the current profile, AC state, available profiles and both remembered choices. Machines with no battery are never switched automatically
- **Keychron / Lemokey HID access** — installs a udev rule (`70-keychron.rules`) granting the active session user read/write access to the `hidraw` device for Keychron keyboards (vendor ID `0x3434`) and Lemokey keyboards (vendor ID `0x362d`); enables in-browser key remapping at [launcher.keychron.com](https://launcher.keychron.com) (WebHID) with no extra privileges; applied automatically on every `setup.sh --sync`
- **Hardware auto-detection** — touchscreen devices get a floating `touch-panel` overlay (started at session start if no keyboard is detected; also started at runtime when a keyboard is unplugged) and are wired up for `wvkbd` (on-screen keyboard, auto-shows on text focus; toggle: `Super+Shift+O`) — but because `wvkbd` is AUR-only it is **not** installed automatically; install it manually (`yay -S wvkbd`) to enable the OSK; accelerometer/gyroscope devices get `iio-sensor-proxy` + `autorotate` (maps orientation → Hyprland transform); all re-evaluated on every `setup.sh --sync`
- **GPU passthrough (VFIO)** — mode-based multi-GPU passthrough using direct sysfs binding (no libvirt): `gpu-passthrough.sh mode vm` binds the GPU + entire IOMMU group to vfio-pci; `mode host` restores the host driver; setup wizard auto-applies IOMMU kernel params and driver isolation (NVIDIA blacklist for single-GPU, dual boot entries with `vfio-pci.ids` for multi-NVIDIA — select "GPU Passthrough" at the boot menu); includes a Docker-based Windows VM launcher (`gpu-passthrough.sh vm`) using `dockurr/windows` with Looking Glass for near-native display; comprehensive VM anti-detection (SMBIOS, CPU flags, device elimination, disk identity) for anti-cheat evasion (EAC, VAC); required packages are checked by `gpu-passthrough.sh setup` (official repos only); `gpu-passthrough.sh vm arch` launches a second GPU-passthrough VM — a real Arch+Hyprland desktop, Packer-built via a genuine unattended hyprconf install, reached over SSH + VNC (`wayvnc`) instead of Looking Glass — mutually exclusive with the Windows VM on single-GPU systems
- **Hot-swappable monitor presets** — switch between bedroom/kitchen layouts at runtime via keybind
- **Quickshell bar** — QtQuick status bar (`stow/quickshell`), one per monitor: workspaces island, window title, clock with calendar popout, custom SNI tray, cpu/temp/mem/gpu/vpn/net/volume/battery modules, screencast indicator, volume OSD, rounded screen corners, and a macOS-style **Control Center** (click the network module or `Super+Shift+N`) with inline Wi-Fi connect (native NetworkManager D-Bus — passwords never touch a process list), Bluetooth devices, and audio output/input pickers. Colors repaint live on theme switch; popouts also toggle via `qs ipc` keybinds
- **Full-desktop theme switcher** — 68 themes applied simultaneously to Hyprland borders, the quickshell bar (live, no restart), Kitty, Dunst, hyprlock, VS Code / Code OSS, Firefox, LibreWolf, GTK3/4, Qt/KDE apps, Dolphin, wvkbd, touch-panel, btop, and wallpaper. Apps that are already open are retinted in place — kitty and btop are signalled to re-read their config, so a switch lands on the running session rather than only on windows opened afterwards, and switches are serialized so two of them cannot interleave; `switch_theme.py --generate <image>` extracts a palette from any wallpaper to create a new theme automatically
- **Privacy-hardened Firefox** — out-of-the-box enterprise `policies.json`: all telemetry disabled, vertical tabs enabled, uBlock Origin force-installed; comprehensive `user.js` privacy prefs applied on every theme switch. Add **LibreWolf** (privacy fork — RFP, no telemetry) manually (`yay -S librewolf-bin`); it's auto-themed by the same engine
- **VPN & kill-switch** — `hyprconf-vpn` manages any NetworkManager VPN profile (OpenVPN or WireGuard) provider-agnostically: `status`/`list`/`connect`/`disconnect`/`import`, plus a bar indicator (click to toggle). `hyprconf-vpn killswitch on` enforces fail-closed VPN-only networking — delegating to ProtonVPN's maintained kill-switch when its official CLI is installed (manual AUR: `proton-vpn-cli`), or a self-contained nftables egress guard otherwise
- **Screen lock & idle** — hyprlock (blurred screenshot), hypridle (dim → lock → DPMS), clipboard wiped on lock; idle power action is AC-aware via `hyprconf-idle-action`: on battery the machine powers **off** after 60 min idle (LUKS key flushed from RAM, disk re-encrypted at rest), on AC it suspends after 3 h
- **YubiKey FIDO2 login** *(optional)* — `yubikey-fido2-setup` interactively enrols a FIDO2+PIN key for `sudo`, TTY login, display manager, SSH, and LUKS unlock at boot (`systemd-cryptenroll`); every edited file is backed up and rolled back on failure. Screen lockers (hyprlock, and COSMIC's `cosmic-greeter`) are actively kept password-only — each is repointed at `system-auth` so it can't inherit the key requirement from `login` and lock you out

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

The installer prompts for one of three modes:

### [1] Full Arch Linux install *(from the Arch ISO)*

Prompts for username, password, hostname, timezone (auto-detected), target disk, and partition mode (WiFi profiles are carried over from the ISO automatically). Then:

1. Partitions disk — **full wipe** or **unallocated space** (preserves existing partitions; reuses or creates EFI)
2. LUKS2 encryption (AES-XTS 512-bit) on root
3. btrfs with subvolumes: `@` `/`, `@home` `/home`, `@snapshots` `/.snapshots`, `@var_log` `/var/log`
4. `pacstrap` — base system, CPU microcode, NetworkManager, iwd, ZSH
5. Chroot config: locale, timezone, hostname, `mkinitcpio` (systemd + sd-encrypt), `systemd-boot`, user account (in `wheel` with full sudo), TTY1 auto-login. The **root account is locked** (`passwd -l root`) — admin is sudo-only, so the install password belongs to the user account + LUKS only. Recover a broken sudo/PAM from the Arch live USB + `arch-chroot` (rescue mode refuses a locked root)
6. Clones the repo and runs `setup.sh` inside the chroot as the new user — the first boot lands on a fully configured desktop, no follow-up steps

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
9. Hardware feature detection: touchscreen → writes `conf.d/hardware.lua` + installs `gtk-layer-shell` (the OSK `wvkbd` is AUR-only and is **not** installed automatically); accelerometer → installs + enables `iio-sensor-proxy`
10. Automatic power profile switching on battery devices: installs udev rule (`99-hyprconf-power.rules`) → `performance` on AC, `power-saver` on battery, unless a profile was remembered with `hyprconf-power-monitor set`
11. Keychron / Lemokey HID permissions: installs udev rule (`70-keychron.rules`) for Keychron (`0x3434`) and Lemokey (`0x362d`) → `TAG+="uaccess"` so `launcher.keychron.com` (WebHID) can remap keys
12. `ufw` deny-inbound / allow-outbound; enable + start
13. Disable `sddm`; enable `NetworkManager`, `iwd`, `bluetooth`, `power-profiles-daemon`; configure NM to use iwd as wifi backend
14. Reload Hyprland

> **WiFi:** if no wifi profiles were copied from the ISO (e.g. ethernet install), connect after first boot with `nmtui`.

> **No AUR, ever:** setup installs **only** official-repo packages — it never installs from the AUR automatically (not even the `yay` helper or the touch-device on-screen keyboard). It also *offers to remove* any foreign/AUR packages already on the system (prompted; the `yay` helper is kept), and gives packages hyprconf itself has retired (e.g. `waybar`, replaced by the quickshell bar) the same prompted, never-automatic treatment on sync. AUR-only extras such as `bibata-cursor-theme` and `wvkbd` must be installed manually: `yay -S bibata-cursor-theme wvkbd`.

### [3] hyprconf only *(any existing Hyprland system)*

Installs just the `hyprconf` TUI into `~/.local/bin` and its library into `~/.local/lib` — no dotfiles, no config changes.

1. Sparse-clones the repo (TUI/library paths only)
2. Copies the `hyprconf` launcher to `~/.local/bin/`
3. Copies the Python library to `~/.local/lib/hyprconf/`
4. Ready to use: `hyprconf`

### Sync

```bash
setup.sh --sync          # pull, re-apply services, reload Hyprland (always config-safe)
setup.sh --sync --force  # discard local divergence, hard-reset to remote branch
setup.sh --sync --full   # as above + full dotfile restow (resets configs to repo defaults)
hyprsync                 # shell alias for setup.sh --sync
```

`setup.sh --sync` is **always config-safe** — additive-only stow creates symlinks for new files but never replaces files you've modified. `--force` hard-resets a diverged branch; `--full` restows all dotfiles. `~/.config/hypr/conf.d/local.lua` (written by the TUI) is machine-local, never managed by stow or git, and survives all sync modes.

---

## Repository Layout

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the full directory tree, test architecture, and developer workflow.

Key paths:

| Path | Purpose |
|---|---|
| `stow/hypr/.local/bin/hyprconf` | TUI launcher |
| `stow/hypr/.config/hypr/scripts/` | Theme engine, TUI, monitor switching |
| `stow/hypr/.local/lib/hyprconf/` | Python library (schema, config, keybinds, …) |
| `stow/quickshell/.config/quickshell/` | Status bar (QML) + its polling scripts |
| `setup.sh` | Bootstrap + sync entry point |
| `packages` | Arch packages (one per line) |
| `install/install.sh` | Self-contained installer |
| `web/` | Static landing page (served via AWS S3 + CloudFront) |
| `infra/firefox/` | System Firefox privacy policy (`policies.json`) |

---

## Website

The project website at **[hyprconf.sh](https://hyprconf.sh)** is a single
self-contained static page (`web/index.html`) — a lightweight reflection of this
README so visitors can see what the project is. No framework or build step. It's
served from an S3 bucket behind CloudFront, whose UA-router sends `curl`/`wget` to
`install.sh` and browsers to the page — so `curl hyprconf.sh` installs while the
domain still shows the site. A personal setup shared as-is for reference and
inspiration, not a supported product.

---

## hyprconf TUI

`hyprconf` (stowed to `~/.local/bin`) launches a full-screen Textual TUI — the
single configuration surface. It covers every Hyprland config section
(general, decoration, animations, input, gestures, group, misc, binds, cursor,
render, opengl, xwayland, dwindle, master and their subsections) with
schema-driven pickers for enums and sliders for numerics, plus keybinds,
window/workspace rules, monitors, hyprlock, hypridle, hyprpaper, hardware
daemons, and a built-in theme picker.

```bash
hyprconf                    # launch the TUI
hyprconf --section general  # jump straight to a section
hyprconf --slim             # compact layout
```

Standalone companion tools keep their own entry points:

```
switch_theme.py            Theme switcher (see below)
switch_monitor.sh <preset> Hot-swap monitor presets
hyprconf-vpn               NetworkManager VPN control + kill-switch
hyprconf-power-monitor     Power profile: auto | set <profile> | status
hyprconf-secureboot        Secure Boot (signed UKI) setup + verify
yubikey-fido2-setup        FIDO2+PIN login / LUKS enrolment
gpu-passthrough.sh         GPU passthrough (VFIO) + Windows VM + Arch VM
setup.sh --sync            Pull + re-stow + re-apply services
hc <tool> [args...]        Short alias for the above (hc vm/gpu/secureboot/vpn/power/yubikey/theme/sync) — pure forwarding, see AGENTS.md
```

### Persistence

All changes made in the TUI are applied immediately via `hyprctl keyword` and written persistently to:

```
~/.config/hypr/conf.d/local.lua
```

This file is `require()`d by `hyprland.lua` on every restart (individually
`pcall`-wrapped so it's optional — see `hyprland.lua`'s `try_require`).

---

## Theme Switcher

Run via `python3 ~/.config/hypr/scripts/theme-switcher/switch_theme.py` (no
argument = interactive picker; a theme name applies it directly).

### Theme Flags

| Flag | Description |
|---|---|
| `--list` / `-l` | Print colour table |
| `--current` / `-c` | Show active theme |
| `--next` / `-n` | Next alphabetically |
| `--prev` / `-p` | Previous |
| `--random` / `-r` | Random pick |
| `--pick` / `-w` | Hyprlauncher picker |
| `--generate IMAGE` / `-g` | Generate a theme from wallpaper colours |
| `--filter STR` / `-f` | Substring filter (matches name **or** `appearance` tag — use `light` / `dark`) |
| `--no-reload` | Skip `hyprctl reload` |

### Available Themes

**Community (47):**

| | | | |
|---|---|---|---|
| `adapta` | `adwaita` | `adwaita-dark` | `ayu-dark` |
| `ayu-mirage` | `catppuccin-frappe` | `catppuccin-latte` | `catppuccin-macchiato` |
| `catppuccin-mocha` | `cyberdream` | `dracula` | `dusklight` |
| `elementarish` | `everforest-dark` | `everforest-light` | `flat-remix` |
| `flat-remix-light` | `gotham` | `greyscale` | `gruvbox` |
| `gruvbox-light` | `gruvbox-material-dark` | `horizon` | `hot-purple-traffic-light` |
| `kanagawa` | `kanagawa-lotus` | `kyli0x` | `matcha-dark-sea` |
| `monokai-pro` | `night-owl` | `nord` | `one-dark` |
| `oxocarbon` | `palenight` | `paper` | `phoenix-night` |
| `rose-pine` | `rose-pine-dawn` | `rose-pine-moon` | `shades-of-purple` |
| `solarized-dark` | `solarized-light` | `tokyo-moon` | `tokyo-night` |
| `tokyo-storm` | `tomorrow-night` | `whiteout` | |

**AI-original (21) — prefix `ai:`:**

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
| `ai:btop-tty` | Classic ANSI 16-colour palette from btop's TTY mode |

> `ai:` themes auto-generate a Kitty colour config from their palette. All include a `vscode` block mapped to the nearest community extension. Use `--filter ai:` to show only AI themes.

### Adding a Theme

Create a JSON file in `stow/hypr/.config/hypr/scripts/theme-switcher/themes/`:

```json
{
  "background": "#1e1e2e",
  "foreground": "#cdd6f4",
  "comment":    "#6c7086",
  "accent":     "#f5c2e7",
  "appearance": "dark",
  "wallpaper":  "~/wallpaper/my-theme.png",
  "kitty":      "~/.config/kitty/themes/my-theme.conf",
  "vscode":  { "theme": "Theme Name", "extension": "publisher.id", "font": "JetBrainsMono Nerd Font" },
  "firefox": { "theme_name": "Theme Name", "theme_id": "{uuid}" }
}
```

`appearance` is `"light"` or `"dark"` — used by `--filter` and shown in `--list`. Auto-generated themes set it from background luminance.

`kitty`, `vscode`, `firefox`, `wallpaper`, and `btop` are all optional.

The `btop` key accepts a system theme name (looked up in `/usr/share/btop/themes/`) or an absolute path. If omitted, a `.theme` file is auto-generated from the palette into `~/.config/btop/themes/`.

---

## Monitor Configuration

| Device type detected | Config symlinked |
|---|---|
| Desktop (chassis type 3–7, 13, 24) | `pcMonitors.lua` — HDMI-A-1 4K@120Hz HDR + DP-1 4K@240Hz |
| Laptop / portable (all other types) | `laptopMonitors.lua` — eDP-1 preferred + external connectors use `preferred` + catch-all wildcard |
| Unknown chassis (fallback) | No battery present → desktop; battery present → laptop |

Hot-swap presets activate at runtime via keybind or `switch_monitor.sh <preset>`:

| Keybind | Preset |
|---|---|
| `Super + Shift + B` | `pcMonitors.bedroom.lua` |
| `Super + Shift + K` | `pcMonitors.kitchen.lua` |

`pcMonitors.K.lua` is an alternate desktop preset (DP-1 4K@240Hz, DP-2 4K@75Hz rotated, HDMI-A-1 4K@120Hz with HDR). Apply manually: `switch_monitor.sh K` → symlinks it onto `monitors.lua` and reloads.

---

## Gestures

Touchpad workspace swiping is configured in `gestures.lua`:

| Setting | Value | Effect |
|---|---|---|
| `workspace_swipe_invert` | `true` | Natural (content-follows-finger) swipe direction |
| `workspace_swipe_distance` | `300` | Pixels to travel for a full swipe |
| `workspace_swipe_min_speed_to_force` | `15` | Minimum speed (px/s) to force completion |
| `workspace_swipe_cancel_ratio` | `0.5` | Below 50% → cancel and return to current workspace |
| `workspace_swipe_create_new` | `true` | Swipe past last workspace creates a new one |
| `workspace_swipe_direction_lock` | `true` | Locks swipe axis after threshold distance |
| `workspace_swipe_direction_lock_threshold` | `10` | Distance (px) before axis locks |
| `workspace_swipe_forever` | `true` | Keeps animating beyond the threshold distance |

---

## Autostart Services

`hyprland.lua` starts these from `hl.on("hyprland.start", …)`, i.e. once the
compositor is up. Nothing is launched while the config is being *parsed*: on the
first parse Hyprland has not created its Wayland socket yet, so a client spawned
there dies immediately (a bare desktop until `hyprctl reload`). The wallpaper and
bar are additionally re-issued by top-level `hl.exec_cmd()` calls, which re-run on
every `hyprctl reload` — guarded on a non-empty `WAYLAND_DISPLAY` so they no-op
during that first parse.

| Command | Purpose | Restart policy |
|---|---|---|
| `pgrep -x hyprpaper … \| xargs -r kill; hyprpaper --config ~/.config/hypr/hyprpaper.conf` | Wallpaper daemon | Launched at startup, then killed and relaunched on every `hyprctl reload` so a theme switch repaints with the new wallpaper |
| `pgrep -x 'qs\|quickshell' >/dev/null \|\| ~/.config/quickshell/launch.sh` | Status bar (quickshell) | Launched once; survives `hyprctl reload` (hot-reloads its own QML). The guard matches both process names — the system package runs as `qs`. A stray waybar from pre-quickshell installs is killed first |
| `/usr/lib/pam_kwallet_init` | KDE Wallet PAM init | Once |
| `kwalletd6` | KDE Wallet daemon (SSH/GPG key storage) | Once |
| `systemctl --user start hyprpolkitagent` | Polkit agent (privilege elevation dialogs) | Once |
| `xsettingsd` | GTK/X11 settings bridge (cursor, icon theme) | Once |
| `hypridle` | Idle/lock daemon | Once |
| `hyprconf-power-monitor auto` | Match the power profile to AC/battery at login | Once (udev handles later changes) |
| `wl-paste … cliphist store` ×2 | Clipboard history (text + image) | Once |
| `nm-applet --indicator` | NetworkManager tray icon | Once |
| `blueman-applet` | Bluetooth tray icon | Once |

---

## Hardware Auto-Detection

Runs at every `setup.sh` invocation (including `--sync`). Results are written to
`~/.config/hypr/conf.d/hardware.lua` (machine-local, not stowed).

### Touchscreen

Detection (checked in order):
1. `/sys/class/input/*/device/uevent` → `ID_INPUT_TOUCHSCREEN=1` — standard HID touchscreens (ELAN, etc.)
2. Same path → `ID_INPUT_TOUCH=1` — generic touch devices (e.g. ASUS ROG Ally, some AMD-based handhelds) that don't set `ID_INPUT_TOUCHSCREEN`
3. Same path → `NAME="Wacom * Finger"` + `PHYS="i2c-*"` — Wacom I2C pen+touch digitizers (ThinkPad Yoga, Surface-style devices) whose driver bypasses the generic udev HID rules and never sets `ID_INPUT_TOUCHSCREEN=1`

Uses **`wvkbd`** — a minimal wlroots on-screen keyboard. It is **AUR-only**, so `setup.sh` does **not** install it (hyprconf never installs AUR packages automatically). The launcher/toggle scripts and `conf.d/hardware.lua` are still wired up; install `wvkbd` yourself to enable the OSK: `yay -S wvkbd`.

| Behaviour | Detail |
|---|---|
| Install | Manual (AUR): `yay -S wvkbd` — degrades gracefully when absent |
| Auto-show | Appears when a text input is focused (`text-input-v3` protocol) |
| Manual toggle | `Super + Shift + O` |
| Theme integration | the theme switcher writes `~/.config/wvkbd/colors` and restarts the daemon |

#### Touch panel (runtime keyboard detection)

On any device with a touchscreen, `setup.sh` installs **`gtk-layer-shell`** and adds two entries to `conf.d/hardware.lua`:

- **`touch-panel-launcher`** — runs at Hyprland session start; checks for a physical keyboard (`ID_INPUT_KEYBOARD=1` + non-empty `PHYS` in sysfs); starts `touch-panel` only if none is found.
- **`touch-panel-watch`** — background daemon using `udevadm monitor`; watches for input device removals during the session; starts `touch-panel` when the last physical keyboard is unplugged.

This means the panel appears correctly whether a keyboard was present at install time or unplugged mid-session.

`touch-panel` is a minimal GTK3 + layer-shell floating overlay anchored to the bottom-right:

- **Normal state** — small circular FAB (☰)
- **Expanded** — compact pill with ⌨ OSK toggle and ⊞ launcher buttons
- Colours sourced from `~/.config/touch-panel/colors` (written by the theme switcher); reloaded live on `SIGUSR1`

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

### GPU Passthrough (VFIO)

Mode-based GPU passthrough for multi-GPU desktops using direct sysfs binding (no libvirt). On single-GPU + iGPU systems, the NVIDIA driver is blacklisted at boot (`install nvidia /bin/false`) and GPU modes switch at runtime — no reboot required. On dual-NVIDIA systems, `gpu-passthrough.sh setup` creates two boot entries sharing the same kernel: a **Normal** entry (both GPUs on nvidia) and a **GPU Passthrough** entry (`vfio-pci.ids=VENDOR:DEVICE` in kernel cmdline so the passthrough GPU is claimed by vfio-pci at boot). Select the desired entry at the systemd-boot menu — no runtime nvidia unbind needed, which avoids the kernel deadlock caused by the shared nvidia module.

**Install:** `gpu-passthrough.sh setup` checks the required official-repo packages (QEMU, OVMF, Docker, dmidecode, …) and prints the exact `pacman` command when any are missing. Looking Glass (`looking-glass` + `looking-glass-module-dkms`) is an optional manual AUR install.

**Setup:** `gpu-passthrough.sh setup` — interactive wizard that detects CPU vendor, auto-applies IOMMU kernel params (systemd-boot, GRUB, or Limine), configures driver isolation (NVIDIA blacklist for single-GPU, or dual boot entries + mkinitcpio module ordering for multi-NVIDIA), and prompts you to choose which GPU to reserve for passthrough.

`[gpu]` accepts: PCI address (`01:00.0`), model name (`3070`, `5090`), or ordinal (`nvidia0`, `nvidia1`). When omitted, uses the GPU saved during `setup`.

| Command | Action |
|---|---|
| `gpu-passthrough.sh` | Status overview — IOMMU, GPU modes, configured GPU |
| `gpu-passthrough.sh detect` | List all GPUs with PCI addresses, IOMMU groups, audio devices, current drivers |
| `gpu-passthrough.sh audit` | Full system readiness check (IOMMU, modules, packages, driver isolation, boot entries) |
| `gpu-passthrough.sh mode` | Show current GPU mode (`vm`, `host`, or `none`) |
| `gpu-passthrough.sh mode vm [--force] [gpu]` | Bind GPU + IOMMU group to vfio-pci (multi-NVIDIA: requires "GPU Passthrough" boot entry) |
| `gpu-passthrough.sh mode host [gpu]` | Unbind from vfio-pci → reload native driver |
| `gpu-passthrough.sh mode none [gpu]` | Unbind GPU from all drivers (idle state) |
| `gpu-passthrough.sh vm install` | Interactive wizard — set RAM, CPU, disk, Windows version, credentials |
| `gpu-passthrough.sh vm launch [--force]` | Start Docker container with GPU passthrough (VM persists until stopped) |
| `gpu-passthrough.sh vm connect [--rdp] [-s]` | Connect to running VM via Looking Glass (falls back to RDP); `-s`/`--stop-on-disconnect` stops VM on RDP exit |
| `gpu-passthrough.sh vm stop` | Stop the Windows VM container |
| `gpu-passthrough.sh vm status` | Show VM config, GPU binding state, container status |
| `gpu-passthrough.sh vm remove` | Remove container, image, and config (preserves `~/Windows/` shared folder) |
| `gpu-passthrough.sh vm usb [list\|add\|remove]` | Hot-plug USB devices into/out of the running VM via QEMU monitor |
| `gpu-passthrough.sh report` | Comprehensive hardware report (system, motherboard, GPUs, IOMMU groups, drivers) |
| `gpu-passthrough.sh diagnose` | Detailed diagnostic dump (dmesg, IOMMU groups, modules, config) |

**Dual-NVIDIA boot entries:** `setup` creates `hyprconf-vm.conf` in `/boot/loader/entries/` (systemd-boot) or a GRUB custom menuentry. The VM entry duplicates the default entry and appends `vfio-pci.ids=<gpu>,<audio>`. mkinitcpio is configured with `vfio-pci` before `nvidia` in MODULES so vfio-pci loads early enough to claim the device. `setup.sh --sync` keeps boot entries and initramfs config in sync. The normal entry is not modified — vfio-pci loads but claims nothing without `vfio-pci.ids` in the cmdline.

**Windows VM:** Uses `dockurr/windows` Docker image (QEMU internally) with GPU forwarded via vfio-pci and [Looking Glass](https://looking-glass.io/) for near-native display latency. First run: `gpu-passthrough.sh vm install` to configure resources and IVSHMEM size. Then `gpu-passthrough.sh vm launch` to start the VM — it persists until explicitly stopped. `gpu-passthrough.sh vm connect` launches Looking Glass (falls back to RDP if `looking-glass-client` not installed). The GPU must have a physical display connected (second monitor, second cable, or HDMI/DP dummy plug). First boot: Windows installs on the GPU-connected display — install GPU drivers and the Looking Glass host app. Audio plays through HDMI from the passthrough GPU. Shared folder at `~/Windows/` is mounted as a network drive. **OEM auto-install:** Steam, Epic Games Launcher, Battle.net, Firefox, and the Looking Glass Host app are automatically installed during first boot via an OEM `install.bat` — no manual downloads needed. All Windows privacy settings are maximised: telemetry disabled, advertising ID off, Cortana off, DiagTrack service stopped, Copilot/Recall/widgets disabled, activity history off, location denied, app launch tracking off. The user account is created automatically (no OOBE prompt). All package dependencies are surfaced by `gpu-passthrough.sh setup`.

**Anti-cheat evasion:** The VM uses a multi-layer anti-detection strategy mirroring [omarchy](https://github.com/basecamp/omarchy):

| Layer | Mechanism | Effect |
|---|---|---|
| **SMBIOS** | Types 0 (BIOS + `uefi=on`), 1 (system + UUID), 2 (baseboard), 3 (chassis), 4 (processor), 17 (memory via dmidecode) | Guest sees real host manufacturer/product/RAM instead of "QEMU Standard PC" |
| **CPU flags** | `CPU_FLAGS` env: `-hypervisor,hv_vendor_id=<vendor>,family=X,model=Y,stepping=Z` | Hides hypervisor CPUID bit; passes real CPU identity |
| **Machine type** | `MACHINE: "q35"` | Modern chipset (vmport=off, hpet=off via Dockurr defaults) |
| **Display** | `DISPLAY: "none"` | Eliminates VirtIO GPU — no Red Hat display adapter in Device Manager |
| **Network** | `ADAPTER: "e1000e"` | Intel 82574L NIC instead of VirtIO — no Red Hat network driver |
| **Disk controller** | `DISK_TYPE: "sata"` | SATA (ich9-ahci) instead of VirtIO SCSI — no Red Hat SCSI controller |
| **Disk identity** | `-global ide-hd.model/serial` + `-global ide-cd.model` from host disk | Guest disk appears as real hardware, not "QEMU HARDDISK" |
| **USB** | `USB: "no"` + conditional `qemu-xhci` only when USB passthrough configured | No unnecessary virtual USB controller |
| **Power** | `-global ICH9-LPC.disable_s3=1 -global ICH9-LPC.disable_s4=1` | Prevents suspend/hibernate which breaks GPU passthrough |
| **Looking Glass** | ivshmem shared memory | Near-native display via physical GPU, no virtual VGA needed |
| **OEM auto-install** | `/oem` volume → `install.bat` runs post-setup | Steam, Epic, Battle.net, Firefox, Looking Glass Host installed; max privacy settings applied (telemetry off, ad ID off, Copilot/Recall/widgets disabled, DiagTrack stopped) |
| **Hyper-V passthrough** | Dockurr default `hv_passthrough` + our `-hypervisor` override | Hyper-V enlightenments active but hypervisor bit hidden |

This is sufficient for EAC (Fortnite, The Finals), VAC (CS2), and most anti-cheat systems. Riot Vanguard (VALORANT) and kernel-level anti-cheat (Javelin/BF6) use deeper detection and are not bypassed.

**Workflow (dual-NVIDIA):** Reboot → select "GPU Passthrough" at boot menu → `gpu-passthrough.sh vm launch` → VM starts with GPU. `gpu-passthrough.sh vm connect` to launch Looking Glass. To return to full desktop: `gpu-passthrough.sh vm stop`, then `gpu-passthrough.sh mode host`, then reboot with the normal entry.

**Workflow (single-GPU + iGPU):** `gpu-passthrough.sh mode vm` unbinds nvidia and binds to vfio-pci. `gpu-passthrough.sh vm launch` starts the Docker container. `gpu-passthrough.sh vm connect` launches Looking Glass (or RDP). VM persists until `gpu-passthrough.sh vm stop`. Return GPU to host: `gpu-passthrough.sh mode host`.

**Prerequisites:** `sudo modprobe kvmfr static_size_mb=N` (32 for 1080p, 64 for 1440p, 128 for 4K). Add to `/etc/modules-load.d/` for persistence. GPU must have a display connected (second monitor or dummy plug).

Config stored at `~/.config/hyprconf/gpu-passthrough.conf` (GPU) and `~/.config/hyprconf/gpu-vm.conf` (VM). Boot-time binding is synced automatically via `setup.sh --sync` for multi-NVIDIA setups. `gpu-passthrough.sh audit` checks IOMMU, VFIO modules, packages, driver isolation, and boot entries.

### Arch Linux VM (GPU Passthrough)

A second GPU-passthrough VM alongside the Windows VM above, under the same `gpu-passthrough.sh vm` command family — a real Arch+Hyprland desktop with the same physical-GPU display quality, reached over plain SSH + VNC instead of Looking Glass/RDP. Launched via a plain `qemu-system-x86_64` process (no Docker).

**GPU passthrough is exclusive:** on a single-GPU system, only one VM — this one or the Windows VM — can hold the vfio-pci-bound GPU at a time. `gpu-passthrough.sh vm arch launch` refuses if the Windows VM container is running, and `gpu-passthrough.sh vm launch` refuses if this VM is running; stop the other one first. A system with a second discrete GPU can run both simultaneously.

**Image:** built ahead of time via Packer (`vm/arch-vm.pkr.hcl`) — a real, unattended hyprconf install using `install/install.sh`'s existing `HYPRCONF_CI=1` path (the same mechanism this repo's own CI uses to build its test VM image, here pointed at a real `git clone --branch stable` instead of a worktree tar). The image is also provisioned as a VM guest: `wayvnc` + `sshd` installed, and a `hyprconf-vm-wayvnc` user service that starts `wayvnc` once Hyprland's Wayland socket exists — giving VNC access to the real, GPU-accelerated compositor session, not an emulated display.

**Install:** `gpu-passthrough.sh vm arch install` checks for `packer` (plus `qemu-desktop`/`edk2-ovmf`, shared with the Windows VM's requirements) and prints the `pacman` command when missing, then runs an interactive wizard (RAM, CPU, disk, username/password, hostname, timezone, SSH/VNC ports) before building the image — a real Arch install inside Packer/QEMU, taking several minutes.

| Command | Action |
|---|---|
| `gpu-passthrough.sh vm arch status` | VM config, GPU binding state, running state, and which VM currently holds the GPU |
| `gpu-passthrough.sh vm arch install` | Interactive wizard — set resources and credentials, then build the image |
| `gpu-passthrough.sh vm arch build` | (Re)build the image from existing config without re-running the wizard |
| `gpu-passthrough.sh vm arch launch [--force]` | Bind GPU, start the VM (persists until stopped) |
| `gpu-passthrough.sh vm arch connect` | Print the SSH command; launch a local VNC viewer if one is found (`vncviewer`, `remmina`, `gvncviewer`) |
| `gpu-passthrough.sh vm arch stop` | Gracefully power off the VM and release the GPU |
| `gpu-passthrough.sh vm arch remove` | Stop, then delete the image and configuration (SSH key preserved) |

**Workflow:** `gpu-passthrough.sh vm arch install` (one-time, several minutes) → `gpu-passthrough.sh vm arch launch` → GPU display comes up on the monitor connected to the passthrough GPU (second monitor, second cable, or HDMI/DP dummy plug — same requirement as the Windows VM) → `gpu-passthrough.sh vm arch connect` for SSH + VNC. Return the GPU to the host: `gpu-passthrough.sh vm arch stop`, then `gpu-passthrough.sh mode host`.

Config stored at `~/.config/hyprconf/arch-vm.conf`; image and firmware state under `~/.local/share/hyprconf/arch-vm/`; dedicated SSH key at `~/.ssh/hyprconf_arch_vm_key`.

**Access is host-local.** Both forwarded ports are bound to `127.0.0.1` on the host — the guest is built through the unattended `HYPRCONF_CI=1` path (stock `sshd` config plus a passwordless-sudo drop-in), so it is never published to the network. Reach it from this machine, or tunnel in (`ssh -L`).

---

## Screen Lock & Idle

| Timeout | Action |
|---|---|
| 4 min | Dim display to 10% |
| 45 min | Wipe clipboard + lock (hyprlock) |
| 60 min | **Power off — on battery only** (`hyprconf-idle-action poweroff-if-battery`): flushes the LUKS key from RAM so the disk is encrypted at rest while in transit; no-op on AC |
| 90 min | Displays off (DPMS) |
| 3 hr | AC-aware (`hyprconf-idle-action auto`): suspend on AC, power off on battery |

Lock manually: `Super + L` or `Super + Shift + Escape`.

hyprlock shows a blurred desktop screenshot, live clock, and password input.

---

## YubiKey FIDO2 Login *(optional)*

Hardware-backed FIDO2+PIN authentication for an Arch + Hyprland system, driven
by the stowed `yubikey-fido2-setup` helper:

```bash
sudo yubikey-fido2-setup status    # keys, PAM coverage, LUKS FIDO2 slots (read-only)
sudo yubikey-fido2-setup setup     # full first-time setup (sudo/TTY/DM/SSH/LUKS)
sudo yubikey-fido2-setup enroll    # add an additional / backup key (login + LUKS slot)
```

`setup` is fully interactive and idempotent — each step is opt-in, every modified
file is backed up to a unique root-owned `mktemp -d` directory (path printed at the
start of the run and in the summary), and any failure offers to roll back all
changes. It covers:

| Surface | What it configures |
|---|---|
| Packages | Installs `libfido2`, `pam-u2f`, `yubikey-manager` if missing |
| FIDO2 PIN | Sets a key PIN via `ykman` if none exists |
| Registration | Writes a PIN-verified credential to `/etc/security/u2f_keys` (root:root 640); optional spare/backup key |
| `sudo` · TTY login · display manager · SSH | Inserts `pam_u2f.so … pinverification=1 cue` into the relevant `/etc/pam.d/*` files (display managers auto-detected) |
| SSH daemon | Sets `UsePAM`/`KbdInteractiveAuthentication`/`AuthenticationMethods` in the first sshd config file that defines each, validates with `sshd -t`, restarts `sshd` |
| LUKS unlock at boot | Enrols the key with `systemd-cryptenroll --fido2-device=auto`, adds `fido2-device=auto` to `/etc/crypttab`, converts `mkinitcpio` HOOKS to `systemd`/`sd-encrypt`/`sd-vconsole`, adds `rd.luks.options=UUID=…=fido2-device=auto` to the bootloader (GRUB or systemd-boot), and rebuilds the initramfs |

**`enroll`** adds a second/backup key to an existing setup without touching PAM
files or rebuilding the initramfs: it appends a new credential to the
`/etc/security/u2f_keys` line (any registered key then works for login) and adds
another `systemd-cryptenroll --fido2-device=auto` keyslot to the LUKS device.
**`status`** is read-only and reports installed packages, detected keys,
per-user credential counts, which `/etc/pam.d/*` files carry `pam_u2f`, and the
number of FIDO2 token slots per LUKS device.

**Screen lockers are intentionally *not* protected by the YubiKey** — each
locker gets its own PAM file pointing at `system-auth` (currently `hyprlock` and
`cosmic-greeter`, COSMIC's lock screen) so unlock stays password-only and
reliable, while the LUKS passphrase always remains as a fallback key slot.

This is a lockout guard, not a convenience: lockers authenticate as *your user*,
not root, and `/etc/security/u2f_keys` is `0640 root:root`. A locker whose stack
reaches `/etc/pam.d/login` therefore hits a `pam_u2f` that cannot open the
authfile, which returns `PAM_AUTHINFO_UNAVAIL` and rejects **every** unlock —
with the key inserted or not. A missing locker PAM file is equally fatal: PAM
falls back to `/etc/pam.d/other` (`pam_deny`). `yubikey-fido2-setup status`
reports the state of each shield.

> Requires a LUKS2 root for boot-unlock (`systemd-cryptenroll` needs LUKS2). The
> YubiKey packages stay commented in `packages` since they only apply to YubiKey
> owners; the script installs them on demand.

---

## Secure Boot *(optional)*

A YubiKey LUKS unlock alone does **not** stop an evil-maid attacker: a tampered,
unsigned initramfs can capture your unwrapped LUKS master key the next time *you*
unlock (PIN/touch don't help), and the installer's login-reused passphrase slot can
be brute-forced offline without ever touching the key. `hyprconf-secureboot`
(stowed to `~/.local/bin`) closes both with a **layered** design:

```bash
sudo hyprconf-secureboot status    # SB state, Setup Mode, UKI, sbctl verify (read-only)
sudo hyprconf-secureboot setup     # signed UKI + sbctl keys/sign/verify + pacman hook
sudo hyprconf-secureboot harden    # key-only LUKS (delegates to yubikey-fido2-setup harden-luks)
```

`setup` installs **sbctl**, converts the boot chain to a **signed Unified Kernel
Image** (kernel + initramfs + cmdline in one signed EFI binary), signs systemd-boot
and the UKIs, and enrolls keys when the firmware is in **Setup Mode** — refusing to
enroll over an unsigned chain so it can't brick the next boot. It detects whether to
keep Microsoft keys (`--microsoft`, for discrete GPUs / option-ROM firmware) or
enroll **own keys only** (`--own-keys-only`, strongest). It stays signed across
`linux`/`systemd`/`sbctl` upgrades via `sbctl sign -s` + a verify-only pacman hook,
and `hyprconf-secureboot status` reports if Secure Boot is later turned off.

You still finish two **manual** UEFI steps software can't do — set a **firmware admin
password** (then `hyprconf-secureboot ack-firmware-password`) and toggle **Secure
Boot → Enabled**. Optional `hyprconf-secureboot tpm-bind` adds TPM2 measured-boot
PCR binding (FIDO2 stays the default decrypt factor). Full details and residual risks
(DMA, cold-boot, rollback) are in [`docs/security-hardening.md`](docs/security-hardening.md).

> UEFI + LUKS2 only. `sbctl` stays commented in `packages` (installed on demand).
> If a boot fails, disable Secure Boot in firmware to recover — the UKI still boots
> with SB off — then fix and re-sign.

---

## Packages

| Category | Packages |
|---|---|
| Core | `base-devel`, `git`, `curl`, `wget`, `unzip`, `vim`, `stow`, `pciutils`, `xdg-user-dirs`, `openssh` |
| Hyprland | `hyprland`, `hyprpaper`, `hyprshot`, `hyprlock`, `hypridle`, `xdg-desktop-portal-hyprland` |
| Audio | `pipewire`, `pipewire-pulse`, `pipewire-alsa`, `wireplumber`, `pavucontrol` |
| KDE / Qt | `kwallet`, `kwallet-pam`, `plasma-integration`, `breeze`, `breeze-gtk`, `kde-cli-tools`, `qt6-wayland` |
| Polkit | `hyprpolkitagent` |
| Terminal & shell | `kitty`, `zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting`, `fastfetch` |
| Bar / Launcher | `quickshell`, `hyprlauncher` |
| Notifications | `dunst` |
| Applications | `firefox`, `code`, `dolphin`, `htop`, `btop` |
| Clipboard | `cliphist`, `wl-clipboard` |
| Media & input | `playerctl`, `brightnessctl` |
| Bluetooth | `bluez`, `bluez-utils`, `blueman` |
| Networking | `networkmanager`, `network-manager-applet`, `libappindicator` (SNI tray icons for nm-applet/blueman) |
| System monitoring | `iio-sensor-proxy` (bar stats read `/proc` + `/sys` directly) |
| Python | `python`, `python-textual` |
| File manager support | `gvfs` |
| Icons & themes | `papirus-icon-theme` (+ optional `adw-gtk3` from AUR) |
| GTK sync | `xsettingsd` |
| Touch panel | `gtk-layer-shell` |
| Fonts | `ttf-jetbrains-mono-nerd`, `noto-fonts-emoji` |
| Power management | `power-profiles-daemon` |
| Firewall | `ufw` |
| VPN / Network privacy | `networkmanager-openvpn`, `wireguard-tools` — core (drive any NM OpenVPN/WireGuard profile via `hyprconf-vpn`); optional manual AUR: `proton-vpn-cli`, `librewolf-bin` |
| Security (optional) | `libfido2`, `pam-u2f`, `yubikey-manager` — for `yubikey-fido2-setup`; commented in `packages`, auto-installed by the script |
| Testing | `python-pytest`, `python-pytest-asyncio`, `python-coverage` |
| AUR (manual) | `bibata-cursor-theme`, `wvkbd` (touch OSK) — install manually, e.g. `yay -S bibata-cursor-theme wvkbd`. hyprconf never installs AUR packages automatically (not even `yay`); you must provide `yay` yourself if you want it. |
| Optional (Nvidia) | `nvidia-utils` *(uncomment in `packages` if needed)* |

---

## Keybindings

> **Note:** these bindings are the maintainer's defaults and ship with the dotfiles. Change them in the `hyprconf` TUI or edit `keybinds.lua` directly.

`mainMod` is **Super (Win)**. Change it persistently in the `hyprconf` TUI (keybinds section) or in `keybinds.lua`.

### Applications

| Keybind | Action |
|---|---|
| `Super + T` | Terminal (Kitty) |
| `Super + F` | Browser (Firefox) |
| `Super + C` | Editor (VS Code) |
| `Super + E` | Files (Dolphin) |
| `Super + D` | Launcher (hyprlauncher) |

### Window Management

| Keybind | Action |
|---|---|
| `Super + Q` | Close window |
| `Super + Shift + Q` | Exit Hyprland |
| `Super + V` / `Super + Shift + Space` | Toggle floating |
| `Super + Shift + F` | Toggle fullscreen |
| `Super + P` | Toggle pseudo-tile |
| `Super + ← ↑ ↓ →` | Move focus |
| `Super + Shift + ← ↑ ↓ →` | Resize window |
| `Super + Shift + =` / `Super + Shift + -` | Increase / decrease window gaps |
| `Super + Shift + A / D` | Swap window left / right |
| `Super + Shift + W / S` | Swap window up / down |
| `Super + LMB drag` | Move window |
| `Super + RMB drag` | Resize window |

### Workspaces

| Keybind | Action |
|---|---|
| `Super + 1, 2, 5–0` | Switch to workspace 1, 2, 5–10 |
| `Super + F1 / F2` | Switch to workspace 3 / 4 |
| `Super + Shift + 1, 2, 5–0` | Move window to workspace 1, 2, 5–10 |
| `Super + Shift + F1 / F2` | Move window to workspace 3 / 4 |
| `Super + M` | Toggle scratchpad |
| `Super + Shift + M` | Move to scratchpad |
| `Super + Scroll` | Cycle workspaces |

### Media & System

| Keybind | Action |
|---|---|
| `XF86AudioRaiseVolume / LowerVolume` | Volume ±5% |
| `XF86AudioMute / MicMute` | Toggle mute / mic mute |
| `XF86MonBrightnessUp / Down` | Brightness ±5% (perceptual curve, floored at 2% so the panel never goes black) |
| `XF86AudioPlay / Pause / Next / Prev` | Media playback |
| `Super + L` | Lock screen |
| `Super + Shift + Escape` | Lock screen (alt) |
| `Super + Shift + 4` | Screenshot region (screen frozen during selection) |
| `Super + Shift + V` | Clipboard history (cliphist + hyprlauncher) |
| `Super + Shift + C` | Bar: toggle calendar popout |
| `Super + Shift + N` | Bar: toggle Control Center (Wi-Fi / Bluetooth / audio) |
| `Super + Shift + Backspace` | Toggle native display (eDP-1) |
| `Super + Shift + B` | Bedroom monitor preset |
| `Super + Shift + K` | Kitchen monitor preset |

---

## ZSH

`setup.sh` idempotently configures `~/.zshrc`:

- `~/.local/bin` prepended to `$PATH`
- Oh My Zsh + `git` plugin, Powerlevel10k theme
- `zsh-autosuggestions`, `zsh-syntax-highlighting`
- `hyprsync` alias → `setup.sh --sync`
- `fastfetch` greeting on every shell

`~/.zprofile` auto-starts Hyprland on TTY1 login (replaces `sddm`) via
`hyprland-session`, a shim that cleans up after unclean shutdowns before
exec'ing the official `start-hyprland` watchdog: it reaps orphaned
compositors and per-session daemons (an orphan holds the seat's input
devices — the cause of "keyboard/mouse dead until re-plugged" — and an
orphaned hypridle holds a stale sleep inhibitor), waits for logind to finish
tearing down the previous session, and backs off when relaunches come fast
(a post-resume GPU wedge otherwise becomes a crash-relaunch storm under
tty1 autologin).

To stop the session from another TTY or over SSH, run `hyprland-stop`.
Do **not** `pkill start-hyprland`: the watchdog relaunches Hyprland after
unclean exits, and killing the watchdog itself orphans the compositor.
`hyprland-stop` first writes a hold file that makes the next autologin land
in a plain shell (so the session *stays* stopped — this also breaks an
active crash storm in one run), then asks the compositor to exit over IPC
and only escalates to signals (watchdog first) if it is unresponsive. Start
again from the held tty1 shell with `start-hyprland`, or just exit it.

On Nvidia, `setup.sh` also configures suspend/resume VRAM preservation
(`NVreg_PreserveVideoMemoryAllocations=1` + the `nvidia-suspend/resume/
hibernate` services) — without it the GPU loses all video memory across
sleep and Hyprland/hyprlock crash on every wake. See
`docs/hyprland-reference.md` for details.

---

## Testing & Development

hyprconf uses a **5-tier test architecture** (unit → integration → TUI → VM → full install). Quick start:

```bash
make test            # Tiers 1–3 (no Hyprland session needed)
make test-vm         # Tier 4 (live Hyprland in QEMU)
make test-install    # Tier 5 (full Arch install smoke test)
```

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the full test tree, fixtures, CI config, branching model, and publish workflow.
