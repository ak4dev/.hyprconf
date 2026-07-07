# Hyprland Configuration Reference

> Curated cheatsheet for this dotfiles repo. Covers every syntax feature in use.
> Full wiki: <https://wiki.hypr.land>

---

## Table of Contents

1. [Config Basics](#config-basics)
2. [Monitor Syntax](#monitor-syntax)
3. [Environment Variables](#environment-variables)
4. [Autostart (exec / exec-once)](#autostart)
5. [Keybind Types](#keybind-types)
6. [Look & Feel](#look--feel)
7. [Input & Gestures](#input--gestures)
8. [Window Rules](#window-rules)
9. [Workspace Rules](#workspace-rules)
10. [hyprlock](#hyprlock)
11. [hypridle](#hypridle)
12. [hyprpaper](#hyprpaper)
13. [Color Format](#color-format)
14. [Useful hyprctl Commands](#useful-hyprctl-commands)

---

## Config Basics

```ini
# Variable definition
$name = value

# Source another file
source = ~/.config/hypr/keybinds.conf

# Machine-local overrides (used by this repo for things like $mainMod)
# Note: Hyprland errors if a glob matches nothing, so this repo uses a conf.d dir.
source = ~/.config/hypr/conf.d/*.conf

# Set an option
general {
    option = value
}

# Environment variable
env = VAR_NAME,value
```

- Comments: `#`
- Variables: `$varName = value` — use with `$varName`
- All options are case-insensitive
- Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/>

> **Hyprland 0.55+ note:** 0.55 introduced an optional Lua configuration format and
> deprecated `hyprlang`, but the traditional `key = value` syntax shown here remains
> fully supported (back-compat is maintained). This repo and `hyprconf` deliberately
> use the stable `key = value` form.

---

## Monitor Syntax

### Classic (inline)

```ini
monitor = NAME, RESOLUTION@HZ, POSITION, SCALE[, EXTRAS...]
```

| Field | Examples |
|---|---|
| NAME | `HDMI-A-1`, `DP-1`, `eDP-1`, `` (match any) |
| RESOLUTION | `3840x2160`, `1920x1200`, `preferred`, `highres`, `highrr` |
| HZ | `@120`, `@60` (appended to resolution) |
| POSITION | `0x0`, `auto`, `auto-right`, `auto-left`, `auto-up`, `auto-down` |
| SCALE | `1`, `1.5`, `2`, `auto` |
| EXTRAS | comma-separated `key, value` pairs (see below) |

**Extra args:**

| Key | Values | Notes |
|---|---|---|
| `vrr` | `0` off · `1` always · `2` fullscreen | Adaptive sync (VRR / FreeSync / G-Sync) |
| `bitdepth` | `8` · `10` | 10-bit requires HDR-capable output |
| `cm` | `auto` · `srgb` · `dcip3` · `dp3` · `adobe` · `wide` · `edid` · `hdr` · `hdredid` | Colour management preset; `hdr`/`hdredid` are experimental |
| `sdrbrightness` | float, default `1.0` | SDR brightness multiplier in HDR mode (typical 1.0–2.0) |
| `sdrsaturation` | float, default `1.0` | SDR saturation multiplier in HDR mode |
| `sdr_eotf` | `default` · `gamma22` · `srgb` | SDR transfer function (follows `render:cm_sdr_eotf`) |
| `supports_hdr` | `-1` off · `0` auto · `1` on | Force HDR support (overrides EDID auto-detection) |
| `sdr_min_luminance` | float, default `0.2` | SDR minimum luminance for SDR→HDR mapping |
| `transform` | `0`–`7` | 0=normal, 1=90°, 2=180°, 3=270°, 4=flipped, 5–7=flipped+rotation |
| `mirror` | monitor name | Mirror another output (no re-render; aspect ratio warning applies) |

```ini
# Examples from this repo
monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5, vrr, 2, bitdepth, 10, cm, hdr, sdrbrightness, 1.3
monitor = DP-3, 3840x2160, auto-right, 3, transform, 3
monitor = DP-1, disable
```

### monitorv2 (block syntax — Hyprland ≥ 0.47)

```ini
monitorv2 {
    output             = DP-1
    mode               = 3840x2160@240
    position           = auto-left
    scale              = 2
    transform          = 0
    supports_wide_color = 1   # -1=force off, 0=auto, 1=force on
    supports_hdr       = 1   # -1=force off, 0=auto, 1=force on
    sdr_max_luminance  = 250  # SDR→HDR brightness (80–400 reasonable)
}
```

### Workspace pinning

```ini
workspace = 1, monitor:HDMI-A-1
workspace = 4, monitor:DP-1
```

### render block (per-config)

```ini
render {
    direct_scanout    = 1   # Reduces latency for fullscreen apps
    cm_auto_hdr        = 1   # Automatically enable HDR for fullscreen apps in HDR-capable color spaces
}
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Monitors/>

---

## Environment Variables

```ini
env = XCURSOR_SIZE,24
env = HYPRCURSOR_SIZE,24
env = QT_QPA_PLATFORM,wayland
env = QT_QPA_PLATFORMTHEME,qt6ct
env = QT_STYLE_OVERRIDE,kvantum
env = GTK_THEME,Adwaita-dark
env = GTK_ICON_THEME,Papirus-Dark
env = GTK_CURSOR_THEME,Bibata-Modern-Ice   # AUR: bibata-cursor-theme
env = GTK_CURSOR_SIZE,24
env = MOZ_ENABLE_WAYLAND,1
```

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Environment-variables/>

---

## Nvidia GPU

`setup.sh` / `hyprconf sync` auto-detects an Nvidia GPU and writes these env vars
into `~/.config/hypr/conf.d/60-hardware.conf`:

```ini
env = LIBVA_DRIVER_NAME,nvidia
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
```

Required packages (auto-installed on detection): `nvidia-dkms`, `nvidia-utils`, `egl-wayland`.

Early-KMS modules are also added to `/etc/mkinitcpio.conf` automatically:

```
MODULES=(... nvidia nvidia_modeset nvidia_uvm nvidia_drm ...)
```

For VA-API hardware video acceleration, optionally install `libva-nvidia-driver` and add:

```ini
env = NVD_BACKEND,direct
```

Wiki: <https://wiki.hypr.land/Nvidia/>

---

## Autostart

```ini
exec-once = program   # Runs once at Hyprland startup only
exec       = program  # Runs at startup AND on every `hyprctl reload`
```

> **Use `exec` for anything that must survive `hyprsync`/`hyprctl reload`** (e.g. daemons, wallpaper, bar).
> Use `exec-once` for one-shot init (polkit, kwallet).

```ini
exec      = pkill hyprpaper; hyprpaper --config ~/.config/hypr/hyprpaper.conf
# Guarded launch: `hyprctl reload` re-runs exec lines, so daemons that must
# NOT restart on reload (the quickshell bar) get a pgrep guard.
exec      = pgrep -x quickshell >/dev/null || ~/.config/quickshell/launch.sh
exec-once = systemctl --user start hyprpolkitagent
exec-once = hypridle
exec      = wl-paste --type text --watch cliphist store
exec      = wl-paste --type image --watch cliphist store
```

---

## Keybind Types

```
bind   KEY, action        # Normal keypress
binde  KEY, action        # Repeats while held (good for resize)
bindl  KEY, action        # Fires even when screen is locked
bindm  KEY, action        # Mouse button bind
bindel KEY, action        # Repeating + works locked (media/brightness keys)
```

### Syntax

```ini
bind  = $mainMod,       T,     exec, kitty
bind  = $mainMod SHIFT, Q,     exit
binde = $mainMod SHIFT, right, resizeactive, 40 0
bindm = $mainMod,       mouse:272, movewindow
bindm = $mainMod,       mouse:273, resizewindow
bindel = , XF86AudioRaiseVolume, exec, wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+
bindl  = , XF86AudioNext, exec, playerctl next
```

### Common dispatchers

| Dispatcher | Args | Effect |
|---|---|---|
| `exec` | command | Run a command |
| `killactive` | — | Close focused window |
| `exit` | — | Exit Hyprland |
| `togglefloating` | — | Float/un-float window |
| `fullscreen` | 0/1/2 | Fullscreen modes |
| `movefocus` | l/r/u/d | Move keyboard focus |
| `resizeactive` | dx dy | Resize active window |
| `workspace` | N / e+1 / e-1 | Switch workspace |
| `movetoworkspace` | N / special:name | Move window to workspace |
| `togglespecialworkspace` | name | Show/hide scratchpad |
| `dpms` | on/off/toggle | Display power management |
| `pseudo` | — | Pseudotile toggle (dwindle) |
| `togglesplit` | — | Toggle split direction |
| `swapwindow` | l/r/u/d | Swap active window with neighbour |

Wiki: <https://wiki.hypr.land/Configuring/Basics/Binds/>

---

## Look & Feel

### general

```ini
general {
    gaps_in  = 3           # Gap between windows
    gaps_out = 3           # Gap between windows and screen edge
    border_size = 2
    col.active_border   = rgba(33ccffee) rgba(00ff99ee) 45deg
    col.inactive_border = rgba(595959aa)
    resize_on_border = false
    allow_tearing    = false
    layout = dwindle       # dwindle | master | scrolling | monocle
}
```

### decoration

```ini
decoration {
    rounding       = 1
    rounding_power = 3
    active_opacity   = 1
    inactive_opacity = 0.8

    shadow {
        enabled      = true
        range        = 4
        render_power = 3
        color        = rgba(1a1a1aee)
    }

    blur {
        enabled   = true
        size      = 3
        passes    = 4
        vibrancy  = 0.1696
    }
}
```

### animations

```ini
animations {
    enabled = yes, please :)

    bezier = NAME, X0, Y0, X1, Y1   # CSS cubic-bezier

    # animation = TYPE, ENABLED, SPEED, CURVE[, STYLE]
    animation = windows,    1, 4.79, easeOutQuint
    animation = windowsIn,  1, 4.1,  easeOutQuint, popin 87%
    animation = workspaces, 1, 1.94, almostLinear, fade
}
```

**Animation types:** `global`, `windows`, `windowsIn`, `windowsOut`, `border`, `fade`, `fadeIn`, `fadeOut`, `layers`, `layersIn`, `layersOut`, `workspaces`, `workspacesIn`, `workspacesOut`

**Styles:** `slide`, `popin [percent%]`, `fade`

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/>

### dwindle layout

```ini
dwindle {
    preserve_split = true
    smart_split    = false  # Cursor-position split direction (implies preserve_split)
    force_split    = 0      # 0=follow mouse, 1=left/top, 2=right/bottom
}
# Note: pseudotiling is the `pseudo` dispatcher / `pseudo` window rule, not a dwindle option.
```

### misc

```ini
misc {
    force_default_wallpaper = 0
    disable_hyprland_logo   = true
}
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/>

---

## Input & Gestures

```ini
input {
    kb_layout  = us
    follow_mouse    = 1   # 0=disabled, 1=full, 2=loose, 3=fullOnRelease
    sensitivity     = 0   # -1.0 to 1.0 (libinput accel)
    natural_scroll  = true

    touchpad {
        natural_scroll = true
    }
}

# 0.55 removed the `workspace_swipe` master toggle and `*_fingers` options; the
# 3-finger swipe is now bound via the gesture system (see the Gestures wiki).
# The tuning options below still apply to it.
gestures {
    workspace_swipe_invert             = true    # Natural (macOS-style)
    workspace_swipe_distance           = 300
    workspace_swipe_min_speed_to_force = 15
    workspace_swipe_cancel_ratio       = 0.5
    workspace_swipe_create_new         = true
    workspace_swipe_direction_lock     = true
    workspace_swipe_forever            = true
}

# Per-device overrides
device {
    name        = epic-mouse-v1   # hyprctl devices to find name
    sensitivity = -0.5
}
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/#input>

---

## Window Rules

```ini
# 0.55 grammar:  windowrule = EFFECT val[, EFFECT val…], match:PROP regex[, match:…]
# Every clause carries a value — write `float on`, never a bare `float`.
# (windowrulev2 and the old `RULE, class:^(…)$` form are rejected since 0.55.)
windowrule = float on, match:class pavucontrol
windowrule = float on, center on, size 820 440, match:class theme-switcher
```

**Common effects:** `float on`, `tile on`, `fullscreen on`, `center on`, `size W H`, `move X Y`, `pin on`, `opacity A [I [F]]`, `no_blur on`, `rounding N`, `border_size N`, `workspace N`

**Match props (`match:` prefix):** `match:class REGEX`, `match:title REGEX`, `match:float 0/1`, `match:fullscreen 0/1`, `match:workspace N`, `match:xwayland 0/1`

Wiki: <https://wiki.hypr.land/Configuring/Basics/Window-Rules/>

---

## Workspace Rules

```ini
workspace = N, monitor:NAME
workspace = N, default:true
workspace = N, gapsout:0, gapsin:0     # "Smart gaps"
workspace = special:name               # Named scratchpad
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Workspace-Rules/>

---

## hyprlock

Config: `~/.config/hypr/hyprlock.conf`
Wiki: <https://wiki.hypr.land/Hypr-Ecosystem/hyprlock/>

```ini
general {
    disable_loading_bar = true
    hide_cursor         = true
    grace               = 0         # Seconds before lock is enforced
    no_fade_in          = false
}

background {
    monitor     =               # Blank = all monitors
    path        = screenshot    # Or absolute path to image
    blur_passes = 3
    blur_size   = 7
    brightness  = 0.7
    contrast    = 0.9
    vibrancy    = 0.1696
}

label {
    monitor     =
    text        = cmd[update:1000] echo "<b>$(date +"%H:%M")</b>"
    color       = rgba(255, 255, 255, 0.9)
    font_size   = 96
    font_family = JetBrainsMono Nerd Font
    position    = 0, 120        # X, Y offset from halign/valign anchor
    halign      = center        # left | center | right
    valign      = center        # top | center | bottom
}

input-field {
    monitor           =
    size              = 280, 52
    outline_thickness = 2
    dots_size         = 0.3
    dots_spacing      = 0.2
    dots_center       = true
    outer_color       = rgba(255, 255, 255, 0.2)
    inner_color       = rgba(0, 0, 0, 0.5)
    font_color        = rgba(255, 255, 255, 0.9)
    fade_on_empty     = true
    placeholder_text  = <i>Password</i>
    check_color       = rgba(100, 220, 100, 1.0)
    fail_color        = rgba(220, 80, 80, 1.0)
    fail_text         = <i>Incorrect ($ATTEMPTS)</i>
    rounding          = 8
    position          = 0, -60
    halign            = center
    valign            = center
}
```

> `cmd[update:MS]` re-runs the shell command every MS milliseconds — used for live clock.

---

## hypridle

Config: `~/.config/hypr/hypridle.conf`
Wiki: <https://wiki.hypr.land/Hypr-Ecosystem/hypridle/>

```ini
general {
    lock_cmd           = pidof hyprlock || (cliphist wipe && hyprlock)
    before_sleep_cmd   = cliphist wipe && hyprlock
    after_sleep_cmd    = hyprctl dispatch dpms on
    ignore_dbus_inhibit = false
}

listener {
    timeout    = 240                              # Seconds of inactivity
    on-timeout = brightnessctl -s set 10%         # Save & dim
    on-resume  = brightnessctl -r                 # Restore
}

listener {
    timeout    = 2700                                            # 45 min — lock
    on-timeout = pidof hyprlock || (cliphist wipe && hyprlock)
    on-resume  = hyprctl dispatch dpms on
}

listener {
    timeout    = 5400                                            # 90 min — displays off
    on-timeout = hyprctl dispatch dpms off
    on-resume  = hyprctl dispatch dpms on
}

listener {
    timeout    = 10800                                           # 3 hr  — suspend
    on-timeout = systemctl suspend
}
```

- `pidof hyprlock ||` prevents double-locking if already locked
- `before_sleep_cmd` fires on lid close / `systemctl suspend`
- Listeners fire in order; earlier timeouts should always be < later ones

---

## hyprpaper

Config: `~/.config/hypr/hyprpaper.conf`
Wiki: <https://wiki.hypr.land/Hypr-Ecosystem/hyprpaper/>

```ini
preload  = /path/to/wallpaper.jpg       # Must preload before setting
wallpaper = ,/path/to/wallpaper.jpg     # Blank monitor = all monitors
wallpaper = HDMI-A-1,/path/to/wall.jpg # Specific monitor

ipc = on    # Enable IPC for runtime wallpaper changes
splash = false
```

Runtime change:
```bash
hyprctl hyprpaper wallpaper "HDMI-A-1,/new/path.jpg"
```

---

## Color Format

Hyprland uses `rgba(RRGGBBAA)` hex strings:

```ini
rgba(33ccffee)   # R=33 G=cc B=ff A=ee (87% opacity)
rgba(00000000)   # Fully transparent
rgba(ffffffff)   # White, fully opaque
```

Gradient borders:
```ini
col.active_border = rgba(33ccffee) rgba(00ff99ee) 45deg
```

---

## Useful hyprctl Commands

```bash
# Apply config changes (re-runs exec, not exec-once)
hyprctl reload

# List all connected monitors
hyprctl monitors

# List all open windows with class/title
hyprctl clients

# List input devices (to find device name for device{} block)
hyprctl devices

# Set an option at runtime (no reload needed)
hyprctl keyword general:gaps_out 10

# Send dispatcher action
hyprctl dispatch workspace 3
hyprctl dispatch dpms off

# Reload hyprpaper wallpaper
hyprctl hyprpaper wallpaper ",/path/to/new.jpg"

# Query active workspace
hyprctl activeworkspace

# Query cursor position
hyprctl cursorpos
```

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Using-hyprctl/>


---

## hyprconf keyword tool

`hyprconf` wraps `hyprctl keyword` with a type-checked schema, readline tab completion, and persistent writes to `~/.config/hypr/conf.d/99-hyprconf-local.conf`.

The shared Python core (`~/.local/lib/hyprconf/`) is the single source of truth for all configuration state. Both the CLI and TUI import from it — no business logic is duplicated.

```bash
# Read options
hyprconf get                         # list sections
hyprconf get general                 # all options in section (with live values)
hyprconf get general gaps_in         # single option with type + description

# Write options (validates type, applies live, persists)
hyprconf set general gaps_in 8
hyprconf set decoration rounding 12
hyprconf set misc vrr 1

# Interactive REPL (Tab completes section/key names, history navigation)
hyprconf configure
# hyprconf(config)# general         → enter section
# hyprconf(config-general)# gaps_in 8
# hyprconf(config-general)# no gaps_in   → reset to default
# hyprconf(config-general)# gaps_in ?    → show details
# hyprconf(config-general)# show         → list all options
# hyprconf(config-general)# exit         → back to root

# Schema / AI changelog interface
hyprconf schema dump                 # JSON of all sections/keys/types/defaults/descriptions
hyprconf schema list-sections        # list section names
hyprconf schema keys general         # keys in a section

# First-run detection: locate and non-destructively migrate existing config
hyprconf autodetect

# Hardware auto-detection (touchscreen / accelerometer)
# Touchscreen: checks ID_INPUT_TOUCHSCREEN=1 (standard HID) OR
#              NAME="Wacom * Finger" + PHYS="i2c-*" (Wacom I2C, e.g. ThinkPad X13 Yoga)
hyprconf hardware status             # show detected hardware + daemon state
hyprconf hardware osk [on|off|toggle]   # start/stop/toggle wvkbd on-screen keyboard
hyprconf hardware rotate <on|off>    # start/stop autorotate daemon
```

Persistence key format: `section:subsection:key = value` (matching `hyprctl keyword` syntax).

Wiki options reference: <https://wiki.hypr.land/Configuring/Basics/Variables/>
