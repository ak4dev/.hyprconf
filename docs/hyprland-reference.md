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

**Deprecation timeline:** Hyprland 0.55 introduced Lua (`hyprland.lua`) as a
replacement for the original hyprlang `.conf` grammar shown in older versions
of this doc. 0.56 (the version this repo currently targets) prints a
deprecation notice on `.conf` configs; full removal is expected around 0.57.
If `hyprland.lua` exists, Hyprland loads it *instead of* `hyprland.conf` — the
two formats are not mixed. This repo, and `hyprconf`'s config engine, moved to
Lua as part of that transition. `hypridle`, `hyprlock`, `hyprpaper`, and
`hyprlauncher` are **separate programs** with their own config lifecycles and
are *not* affected — they keep using hyprlang `.conf` (see their sections
below).

```lua
-- Variable (a plain Lua local, since Lua files don't share `$var`-style globals)
local name = "value"

-- Include another file — dots in the module name become path separators, so
-- a directory literally named with a dot (this repo's conf.d/) needs a
-- package.path workaround; see hyprland.lua's own comment on this.
require("keybinds")

-- Machine-local overrides: each require is individually pcall-wrapped so a
-- missing file is a no-op (no hyprlang-style "glob must match >=1 file"
-- restriction to work around anymore).
local function try_require(name) pcall(require, name) end
try_require("local")

-- Set an option
hl.config({
    general = {
        option = value,
    },
})

-- Environment variable
hl.env("VAR_NAME", "value")
```

- Comments: `-- …` (Lua), not `#`
- One `hl.*(...)` statement per line is this repo's own convention (not a Lua
  requirement) — it keeps every keybind/rule/monitor entry addressable by
  line number, which is how `hyprconf`'s TUI adds/deletes entries
- Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/>

> **Ground truth used to write this doc:** the installed Hyprland package's
> own Lua API type-stub (`/usr/share/hypr/stubs/hl.meta.lua`) and example
> config (`/usr/share/hypr/hyprland.lua`) — more reliable than the wiki, whose
> Lua pages are JS-rendered and were seen to omit content when fetched
> programmatically. Re-check those two files against your installed version
> before trusting an unfamiliar `hl.*` field name in the wild.

---

## Monitor Syntax

### `hl.monitor({...})`

```lua
hl.monitor({ output = NAME, mode = "RESOLUTION@HZ", position = "POSITION", scale = SCALE })
```

| Field | Type | Examples |
|---|---|---|
| `output` | string | `"HDMI-A-1"`, `"DP-1"`, `"eDP-1"`, `""` (catch-all — matches any unlisted connector) |
| `mode` | string | `"3840x2160@120"`, `"1920x1200"`, `"preferred"`, `"highres"`, `"highrr"` |
| `position` | string | `"0x0"`, `"auto"`, `"auto-right"`, `"auto-left"`, `"auto-up"`, `"auto-down"` |
| `scale` | string \| number | `1`, `1.5`, `2`, `"auto"` |
| `disabled` | boolean | `true` disables the output (replaces the old `mode = "disable"` positional form) |

**Extra fields** (same table, alongside the ones above):

| Key | Type | Values | Notes |
|---|---|---|---|
| `vrr` | integer | `0` off · `1` always · `2` fullscreen | Adaptive sync (VRR / FreeSync / G-Sync) |
| `bitdepth` | integer | `8` · `10` | 10-bit requires HDR-capable output |
| `cm` | string | `"auto"` · `"srgb"` · `"dcip3"` · `"dp3"` · `"adobe"` · `"wide"` · `"edid"` · `"hdr"` · `"hdredid"` | Colour management preset; `hdr`/`hdredid` are experimental |
| `sdrbrightness` | number | default `1.0` | SDR brightness multiplier in HDR mode (typical 1.0–2.0) |
| `sdrsaturation` | number | default `1.0` | SDR saturation multiplier in HDR mode |
| `sdr_eotf` | string | `"default"` · `"gamma22"` · `"srgb"` | SDR transfer function (follows `render.cm_sdr_eotf`) |
| `supports_hdr` | integer | `-1` off · `0` auto · `1` on | Force HDR support (overrides EDID auto-detection) |
| `sdr_min_luminance` | number | default `0.2` | SDR minimum luminance for SDR→HDR mapping |
| `transform` | integer | `0`–`7` | 0=normal, 1=90°, 2=180°, 3=270°, 4=flipped, 5–7=flipped+rotation |
| `mirror` | string | monitor name | Mirror another output (no re-render; aspect ratio warning applies) |

```lua
-- Examples from this repo (pcMonitors.lua / pcMonitors.bedroom.lua)
hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@120", position = "0x0", scale = 1.5, vrr = 2, bitdepth = 10, cm = "hdr", sdrbrightness = 1.3 })
hl.monitor({ output = "DP-3", mode = "3840x2160", position = "auto-right", scale = 3, transform = 3 })
hl.monitor({ output = "DP-1", disabled = true })
```

### Workspace pinning

```lua
hl.workspace_rule({ workspace = "1", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "4", monitor = "DP-1" })
```

### render (per-config)

```lua
hl.config({
    render = {
        direct_scanout = 1,  -- Reduces latency for fullscreen apps
        cm_auto_hdr = 1,     -- Automatically enable HDR for fullscreen apps in HDR-capable color spaces
    },
})
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Monitors/>

---

## Environment Variables

```lua
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")
hl.env("QT_QPA_PLATFORM", "wayland")
hl.env("QT_QPA_PLATFORMTHEME", "qt6ct")
hl.env("QT_STYLE_OVERRIDE", "kvantum")
hl.env("GTK_THEME", "Adwaita-dark")
hl.env("GTK_ICON_THEME", "Papirus-Dark")
hl.env("GTK_CURSOR_THEME", "Bibata-Modern-Ice")   -- AUR: bibata-cursor-theme
hl.env("GTK_CURSOR_SIZE", "24")
hl.env("MOZ_ENABLE_WAYLAND", "1")
```

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Environment-variables/>

---

## Nvidia GPU

`setup.sh` (and `setup.sh --sync`) auto-detects an Nvidia GPU and writes these env vars
into `~/.config/hypr/conf.d/hardware.lua`:

```lua
hl.env("LIBVA_DRIVER_NAME", "nvidia")
hl.env("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
```

Required packages (auto-installed on detection): `nvidia-dkms`, `nvidia-utils`, `egl-wayland`.

Early-KMS modules are also added to `/etc/mkinitcpio.conf` automatically:

```
MODULES=(... nvidia nvidia_modeset nvidia_uvm nvidia_drm ...)
```

For VA-API hardware video acceleration, optionally install `libva-nvidia-driver` and add:

```lua
hl.env("NVD_BACKEND", "direct")
```

Wiki: <https://wiki.hypr.land/Nvidia/>

---

## Autostart

```lua
-- Fires once at Hyprland startup only — the Lua equivalent of `exec-once`.
hl.on("hyprland.start", function()
    hl.exec_cmd("program")
end)

-- A plain top-level hl.exec_cmd() call (not wrapped in hl.on) runs at startup
-- AND on every `hyprctl reload`, since a Lua config file re-executes
-- top-to-bottom on every reload — this is the equivalent of classic `exec =`.
hl.exec_cmd("program")
```

> **Use a top-level `hl.exec_cmd()` call for anything that must survive
> `hyprctl reload`** (e.g. daemons, wallpaper, bar). Use `hl.on("hyprland.start", …)`
> for one-shot init (polkit, kwallet).

```lua
hl.exec_cmd("pkill hyprpaper; hyprpaper --config ~/.config/hypr/hyprpaper.conf")
-- Guarded launch: a plain hl.exec_cmd() call re-runs on every reload, so
-- daemons that must NOT restart on reload (the quickshell bar) get a pgrep
-- guard. Match every name the daemon can run under — quickshell's comm is
-- `qs` when launched via the system package, so guarding only `quickshell`
-- always misses.
hl.exec_cmd("pgrep -x 'qs|quickshell' >/dev/null || ~/.config/quickshell/launch.sh")

hl.on("hyprland.start", function()
    hl.exec_cmd("systemctl --user start hyprpolkitagent")
    hl.exec_cmd("hypridle")
    hl.exec_cmd("wl-paste --type text --watch cliphist store")
    hl.exec_cmd("wl-paste --type image --watch cliphist store")
end)
```

---

## Keybind Types

```
hl.bind(keys, dispatcher)                              -- Normal keypress
hl.bind(keys, dispatcher, { repeating = true })         -- Repeats while held (good for resize)
hl.bind(keys, dispatcher, { locked = true })            -- Fires even when screen is locked
hl.bind(keys, dispatcher, { mouse = true })             -- Mouse button bind
hl.bind(keys, dispatcher, { locked = true, repeating = true })  -- Repeating + works locked (media/brightness keys)
```

### Syntax

```lua
local mainMod = "SUPER"

hl.bind(mainMod .. " + T", hl.dsp.exec_cmd("kitty"))
hl.bind(mainMod .. " + SHIFT + Q", hl.dsp.exit())
hl.bind(mainMod .. " + SHIFT + right", hl.dsp.window.resize({ x = 40, y = 0 }), { repeating = true })
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"), { locked = true })
```

### Common dispatchers (`hl.dsp.*`)

| Dispatcher | Args | Effect |
|---|---|---|
| `hl.dsp.exec_cmd(cmd)` | command string | Run a command |
| `hl.dsp.window.close()` | — | Close focused window |
| `hl.dsp.exit()` | — | Exit Hyprland |
| `hl.dsp.window.float({action="toggle"})` | — | Float/un-float window |
| `hl.dsp.window.fullscreen()` | — | Toggle fullscreen |
| `hl.dsp.focus({direction=...})` | `"left"`/`"right"`/`"up"`/`"down"` | Move keyboard focus |
| `hl.dsp.window.resize({x=,y=})` | dx, dy | Resize active window |
| `hl.dsp.focus({workspace=...})` | N / `"e+1"` / `"e-1"` | Switch workspace |
| `hl.dsp.window.move({workspace=...})` | N / `"special:name"` | Move window to workspace |
| `hl.dsp.workspace.toggle_special(name)` | name | Show/hide scratchpad |
| `hl.dsp.dpms(...)` | on/off/toggle | Display power management |
| `hl.dsp.window.pseudo()` | — | Pseudotile toggle (dwindle) |
| `hl.dsp.layout("togglesplit")` | — | Toggle split direction |
| `hl.dsp.window.swap({direction=...})` | `"left"`/`"right"`/`"up"`/`"down"` | Swap active window with neighbour |

Wiki: <https://wiki.hypr.land/Configuring/Basics/Binds/>

---

## Look & Feel

### general

```lua
hl.config({
    general = {
        gaps_in = 3,           -- Gap between windows
        gaps_out = 3,          -- Gap between windows and screen edge
        border_size = 2,
        col = {
            active_border = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 },
            inactive_border = "rgba(595959aa)",
        },
        resize_on_border = false,
        allow_tearing = false,
        layout = "dwindle",    -- dwindle | master | scrolling | monocle
    },
})
```

### decoration

```lua
hl.config({
    decoration = {
        rounding = 1,
        rounding_power = 3,
        active_opacity = 1,
        inactive_opacity = 0.8,

        shadow = {
            enabled = true,
            range = 4,
            render_power = 3,
            color = "rgba(1a1a1aee)",
        },

        blur = {
            enabled = true,
            size = 3,
            passes = 4,
            vibrancy = 0.1696,
        },
    },
})
```

### animations

```lua
hl.config({ animations = { enabled = true } })

hl.curve("easeOutQuint", { type = "bezier", points = { {0.23, 1}, {0.32, 1} } })  -- CSS cubic-bezier

-- hl.animation({ leaf = TYPE, enabled = ENABLED, speed = SPEED, bezier = CURVE[, style = STYLE] })
hl.animation({ leaf = "windows",    enabled = true, speed = 4.79, bezier = "easeOutQuint" })
hl.animation({ leaf = "windowsIn",  enabled = true, speed = 4.1,  bezier = "easeOutQuint", style = "popin 87%" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
```

**Animation leaves:** `global`, `windows`, `windowsIn`, `windowsOut`, `border`, `fade`, `fadeIn`, `fadeOut`, `layers`, `layersIn`, `layersOut`, `workspaces`, `workspacesIn`, `workspacesOut`

**Styles:** `slide`, `popin [percent%]`, `fade`

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/>

### dwindle layout

```lua
hl.config({
    dwindle = {
        preserve_split = true,
        smart_split = false,  -- Cursor-position split direction (implies preserve_split)
        force_split = 0,      -- 0=follow mouse, 1=left/top, 2=right/bottom
    },
})
-- Note: pseudotiling is the hl.dsp.window.pseudo() dispatcher / a window rule, not a dwindle option.
```

### misc

```lua
hl.config({
    misc = {
        force_default_wallpaper = 0,
        disable_hyprland_logo = true,
        allow_session_lock_restore = true,  -- let a relaunched hyprlock re-lock after
                                             -- the previous locker crashed (pairs with
                                             -- hypridle's after_sleep_cmd re-lock)
        -- Related: lockdead_screen_delay (ms before the red "lockdead" screen),
        -- disable_watchdog_warning (silence the "not started via start-hyprland"
        -- warning — settable in the hyprconf TUI, misc section).
    },
})
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/>

---

## Session start / stop (start-hyprland)

Since 0.53 the `hyprland` package ships `start-hyprland`, a **watchdog
launcher**: it runs `Hyprland --watchdog-fd N` as a child, provides crash
recovery (relaunch on unclean exit) and safe mode. Hyprland warns when started
without it.

- This repo's `~/.zprofile` (written by `setup.sh`) execs
  `~/.local/bin/hyprland-session` on tty1. tty1 is **autologin**, so every
  session exit — clean or crash — triggers an immediate re-login and another
  run of the shim. Before exec'ing `start-hyprland` it:
  1. honors the **hold file** (`$XDG_RUNTIME_DIR/hyprland-session.hold`,
     written by `hyprland-stop`) by dropping to a plain shell — without it,
     "stop" is instantly answered by an autologin relaunch;
  2. reaps orphaned compositors / stale `$XDG_RUNTIME_DIR/hypr/<sig>/` dirs,
     and orphaned per-session daemons (allowlisted comms at PPID 1: hypridle,
     hyprpaper, hyprlock, quickshell, …) — an orphaned hypridle holds a stale
     sleep inhibitor and double-fires lock commands; never touch non-listed
     PPID-1 processes (nohup'd user jobs carry the dead session's
     `HYPRLAND_INSTANCE_SIGNATURE` too);
  3. waits (≤10 s) for logind to finish tearing down previous sessions on the
     same TTY — starting into a `closing` session brings the compositor up
     inactive ("Session is not active, waiting for 5s") with dead inputs;
  4. **backs off on rapid relaunches** (stamp file): a session that died
     within 90 s of starting is a failed start; attempts 3–6 wait 15/30/60 s,
     then it gives up into a shell instead of storming (post-resume GPU
     wedges caused one SIGABRT + re-login every ~7 s).
- **Autologin is per-machine, not per-install:** setup.sh never configures it
  (passwordless console = a security decision). Toggle it by adding/removing
  the `/etc/systemd/system/getty@tty1.service.d/autologin.conf` drop-in
  (`ExecStart=-/sbin/agetty -o '-p -f -- \\u' --noclear --autologin <user> %I $TERM`).
  Changes apply at the next getty respawn.
- **Stopping the session:** `hyprland-stop` (from any TTY/SSH), or
  `hyprctl dispatch exit` / the `exit` keybind from inside. Never
  `pkill start-hyprland` — killing the watchdog orphans Hyprland, which keeps
  the logind session + every input-device fd open; the next session's
  keyboard/mouse stay dead until the peripherals are re-plugged. Killing
  Hyprland itself with SIGKILL is answered by the watchdog relaunching it.
  `hyprland-stop` writes the hold file *first*, so a single run also stops a
  crash-relaunch storm whose current instance is mid-init (no IPC socket yet
  → invisible to instance enumeration); it then asks instances to exit over
  IPC, escalates watchdog-first only if unresponsive, and finally sweeps any
  mid-init compositor. Start again from the held tty1 shell with
  `start-hyprland` (or exit the shell to re-trigger autologin).
- Launch flags: `start-hyprland -- -h` (config path, checks, etc.).

---

## Nvidia: suspend/resume VRAM preservation

Without explicit configuration the Nvidia driver **discards all video memory
on S3 suspend**. On wake the compositor's GL context is gone: Hyprland
SIGABRTs within ~1 min of `PM: suspend exit` (uncaught exception), every EGL
client dies with it (hyprlock included — "no lockscreen after wake"), and
relaunches crash in `CCompositor::initServer` until the GPU resettles
(~1–2 min) — which autologin turns into a relaunch storm.

Required (NVIDIA README "Preserving video memory allocations", applied by
`setup.sh`, works for proprietary and `nvidia-open`):

```ini
# /etc/modprobe.d/nvidia-power-management.conf
options nvidia NVreg_PreserveVideoMemoryAllocations=1 NVreg_TemporaryFilePath=/var/tmp
```

```bash
systemctl enable nvidia-suspend.service nvidia-resume.service \
                 nvidia-hibernate.service nvidia-suspend-then-hibernate.service
mkinitcpio -P   # modprobe.d is baked into the initramfs (modconf + early KMS)
```

- The services drive `/proc/driver/nvidia/suspend`; the module parameter alone
  does nothing. `/usr/lib/systemd/system-sleep/nvidia` only covers the resume
  side.
- `NVreg_TemporaryFilePath` must be a real filesystem (not tmpfs) with room
  for a copy of all utilized VRAM — `/var/tmp`, never the `/tmp` default.
- Verify after a suspend cycle: `journalctl -b -u nvidia-suspend.service` and
  no new `coredumpctl list Hyprland` entries at the wake timestamp.

---

## Input & Gestures

```lua
hl.config({
    input = {
        kb_layout = "us",
        follow_mouse = 1,      -- 0=disabled, 1=full, 2=loose, 3=fullOnRelease
        sensitivity = 0,       -- -1.0 to 1.0 (libinput accel)
        natural_scroll = true,

        touchpad = {
            natural_scroll = true,
        },
    },
})

-- Since 0.51 there's no `workspace_swipe` master toggle; the swipe must be
-- bound explicitly via the gesture system, or swiping does nothing:
--
--   hl.gesture({ fingers = N, direction = "...", action = "...", mods = "...", scale = F })
--   hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })  -- this repo (gestures.lua)
--   hl.gesture({ fingers = 4, direction = "down", mods = "SUPER", action = "special", workspace_name = "scratchpad" })
--
-- Directions: swipe/horizontal/vertical/left/right/up/down/pinch/pinchin/pinchout
-- Actions: workspace, move, resize, special, close, fullscreen, float,
--          cursorZoom, scroll_move, unset
-- The tuning options below apply to the workspace swipe gesture.
hl.config({
    gestures = {
        workspace_swipe_invert = true,     -- Natural (macOS-style)
        workspace_swipe_distance = 300,
        workspace_swipe_min_speed_to_force = 15,
        workspace_swipe_cancel_ratio = 0.5,
        workspace_swipe_create_new = true,
        workspace_swipe_direction_lock = true,
        workspace_swipe_forever = true,
    },
})

-- Per-device overrides
hl.device({
    name = "epic-mouse-v1",  -- hyprctl devices to find name
    sensitivity = -0.5,
})
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/#input>

---

## Window Rules

```lua
-- hl.window_rule({ name = "...", match = { PROP = value, ... }, EFFECT = value, ... })
-- One call per line is this repo's own convention (see Config Basics above) —
-- it's what lets hyprconf's TUI add/delete individual rules by line number.
hl.window_rule({ match = { class = "pavucontrol" }, float = true })
hl.window_rule({ name = "theme-switcher-float", match = { class = "theme-switcher" }, float = true, center = true, size = "820 440" })
```

**Common effects:** `float`, `tile`, `fullscreen`, `center`, `size = "W H"`, `move = "X Y"`, `pin`, `opacity`, `no_blur`, `rounding`, `border_size`, `workspace`, `no_auto_hdr` (0.56+) — booleans (`float = true`), numbers, or strings depending on the field.

**Match table fields:** `class`, `title`, `float`, `fullscreen`, `workspace`, `xwayland` — same prop vocabulary as before, just Lua table keys instead of `match:field value` comma-clauses.

> 0.56 adds a `stableid:ID` **window selector** for dispatchers
> (`hyprctl dispatch focuswindow stableid:foo`) — it is not a `match` table field.

Wiki: <https://wiki.hypr.land/Configuring/Basics/Window-Rules/>

---

## Workspace Rules

```lua
hl.workspace_rule({ workspace = "1", monitor = "NAME" })
hl.workspace_rule({ workspace = "1", default = true })
hl.workspace_rule({ workspace = "1", gaps_out = 0, gaps_in = 0 })  -- "Smart gaps"
hl.workspace_rule({ workspace = "special:name" })                  -- Named scratchpad
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Workspace-Rules/>

---

## hyprlock

Config: `~/.config/hypr/hyprlock.conf` — a **separate program**, still hyprlang `.conf` (not part of the 0.55+ Lua migration).
Wiki: <https://wiki.hypr.land/Hypr-Ecosystem/hyprlock/>

```ini
general {
    hide_cursor      = true
    immediate_render = true   # draw instantly (background:color until the
                              # screenshot/image resource is ready)
    # Other general{} options (hyprlock ≥ 0.9): ignore_empty_input, text_trim,
    # fractional_scaling (0/1/2=auto), screencopy_mode (0=gpu/1=cpu),
    # fail_timeout (ms).
    # REMOVED from general{}: disable_loading_bar; grace → `--grace N` CLI
    # flag; no_fade_in → `animations { }` category / fadeIn animation.
}

# Auth is its own category now (pam enabled by default):
# auth { pam { enabled = true } fingerprint { enabled = false } }

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

Config: `~/.config/hypr/hypridle.conf` — a **separate program**, still hyprlang `.conf` (not part of the 0.55+ Lua migration).
Wiki: <https://wiki.hypr.land/Hypr-Ecosystem/hypridle/>

```ini
general {
    lock_cmd           = pidof hyprlock || (cliphist wipe && hyprlock)
    before_sleep_cmd   = loginctl lock-session    # NOT hyprlock directly — see below
    after_sleep_cmd    = loginctl lock-session; hyprctl dispatch dpms on
    inhibit_sleep      = 3     # hold sleep until the session is actually locked
    ignore_dbus_inhibit = false
}

listener {
    timeout    = 240                              # Seconds of inactivity
    on-timeout = brightnessctl -s set 10%         # Save & dim
    on-resume  = brightnessctl -r                 # Restore
}

listener {
    timeout    = 2700                             # 45 min — lock (via lock_cmd)
    on-timeout = loginctl lock-session
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

- **Single lock path:** every lock trigger (idle listener, sleep hook, keybind)
  goes through `loginctl lock-session`, which fires `lock_cmd` exactly once.
  The `pidof hyprlock ||` guard prevents a second hyprlock instance — two
  lockers fight over `ext-session-lock` and the loser exits (crashing on the
  way out in 0.9.x), leaving wakes with no lockscreen.
- `before_sleep_cmd` fires on lid close / `systemctl suspend`;
  `after_sleep_cmd` fires on resume. Re-issuing `loginctl lock-session` there
  relaunches hyprlock if it died across the sleep (guarded no-op otherwise) —
  pair it with `misc.allow_session_lock_restore = true` in `hyprland.lua`.
- `inhibit_sleep` modes: `0` off · `1` wait for `before_sleep_cmd` to launch ·
  `2` auto · `3` wait until a session-lock client reports locked (systemd caps
  the delay at `InhibitDelayMaxSec`, 5 s by default, so a broken locker cannot
  block suspend forever).
- Listeners fire in order; earlier timeouts should always be < later ones

---

## hyprpaper

Config: `~/.config/hypr/hyprpaper.conf` — a **separate program**, still hyprlang `.conf` (not part of the 0.55+ Lua migration).
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

Hyprland uses `rgba(RRGGBBAA)` hex strings — in the Lua compositor config
these are plain **quoted Lua strings** (`HL.ConfigValueTypes` accepts a string
everywhere a `color`/`gradient` value is expected; hyprlock/hypridle/hyprpaper
keep the bare unquoted hyprlang form shown elsewhere in this doc):

```lua
"rgba(33ccffee)"   -- R=33 G=cc B=ff A=ee (87% opacity)
"rgba(00000000)"   -- Fully transparent
"rgba(ffffffff)"   -- White, fully opaque
```

Gradient borders:
```lua
col = { active_border = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 } }
-- or, equivalently, a single string in the classic "color1 color2 ANGLEdeg" form:
col = { active_border = "rgba(33ccffee) rgba(00ff99ee) 45deg" }
```

---

## Useful hyprctl Commands

`hyprctl` is runtime IPC — it talks to a running compositor over a socket and
is completely unaffected by the `.conf`→Lua config-file migration; every
command below works the same regardless of which format produced the running
config.

```bash
# Apply config changes (re-runs top-level hl.exec_cmd() calls, not hl.on("hyprland.start", ...))
hyprctl reload

# List all connected monitors
hyprctl monitors

# List all open windows with class/title
hyprctl clients

# List input devices (to find device name for hl.device({...}))
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

## hyprconf TUI

`hyprconf` launches a full-screen Textual TUI with type-checked editing of every
Hyprland config section (schema-driven pickers for enums, sliders for numerics),
plus keybinds, window/workspace rules, monitors, hyprlock, hypridle, hyprpaper,
hardware daemons, and the theme picker. Writes persist to
`~/.config/hypr/conf.d/local.lua`.

The shared Python core (`~/.local/lib/hyprconf/`) is the single source of truth
for all configuration state; the TUI imports from it — no business logic is
duplicated. The option schema lives in `hyprconf/schema.py`; the Lua-syntax
primitives (comment stripping, value formatting, single-line call parsing)
live in `hyprconf/lua_syntax.py`.

Persistence key format: internally still `section:subsection:key` (matching
`hyprctl keyword` syntax), serialized on disk as a single nested
`hl.config({...})` call rather than flat `key = value` lines.

Wiki options reference: <https://wiki.hypr.land/Configuring/Basics/Variables/>
