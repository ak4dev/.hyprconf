# Hyprland Configuration Reference

> Curated cheatsheet of the Lua config syntax this overlay uses in `hypr/*.lua`
> and in what the `hyprconf` TUI writes. Full wiki: <https://wiki.hypr.land>.
> Omarchy owns the rest of the Hyprland setup (autostart, env vars, lock/idle,
> backgrounds, session) — see `/usr/share/omarchy/default/hypr/`.

---

## Table of Contents

1. [Config Basics](#config-basics)
2. [Omarchy's Override Points](#omarchys-override-points)
3. [Monitor Syntax](#monitor-syntax)
4. [Keybinds](#keybinds)
5. [Look & Feel](#look--feel)
6. [Input & Gestures](#input--gestures)
7. [Window Rules](#window-rules)
8. [Workspace Rules](#workspace-rules)
9. [Color Format](#color-format)
10. [Runtime: hyprctl on 0.56](#runtime-hyprctl-on-056)
11. [hyprconf TUI](#hyprconf-tui)

---

## Config Basics

Hyprland 0.55 introduced Lua (`hyprland.lua`); 0.56 — the version this overlay
targets, and what Omarchy 4.0 ships — no longer reads hyprlang `.conf` for the
compositor. Omarchy's `~/.config/hypr/hyprland.lua` is the entry point.

```lua
-- Comments are `--`, not `#`
local name = "value"                      -- a plain Lua local

-- Set options
hl.config({
    general = {
        option = value,
    },
})

-- Include another module (dots become path separators — "hypr.bindings" is
-- ~/.config/hypr/bindings.lua). A directory whose NAME contains a dot (conf.d/)
-- cannot be require()d; use loadfile() as hypr/hyprland.block.lua does.
require("hypr.bindings")
```

- One `hl.*(...)` statement per line is this repo's convention (not a Lua
  requirement) — it keeps every bind/rule/monitor entry addressable by line
  number, which is how the TUI adds and deletes entries.
- **Ground truth:** the installed package's Lua API stub
  (`/usr/share/hypr/stubs/hl.meta.lua`) and example config
  (`/usr/share/hypr/hyprland.lua`). Re-check them before trusting an unfamiliar
  `hl.*` field.

---

## Omarchy's Override Points

Omarchy's `~/.config/hypr/hyprland.lua` (template: `/usr/share/omarchy/config/hypr/hyprland.lua`)
loads its defaults, then `require`s the user files, then its toggles, then invites
personal additions at the tail:

```lua
require("default.hypr.omarchy")   -- Omarchy defaults
require("hypr.monitors")          -- ~/.config/hypr/monitors.lua   ← switch_monitor.sh symlinks presets here
require("hypr.input")             -- ~/.config/hypr/input.lua      ← symlink to hypr/input.lua
require("hypr.bindings")          -- ~/.config/hypr/bindings.lua   ← symlink to hypr/bindings.lua
require("hypr.looknfeel")         -- ~/.config/hypr/looknfeel.lua  ← symlink to hypr/looknfeel.lua
require("hypr.autostart")         -- left to Omarchy
require("default.hypr.toggles")
-- Add any other personal Hyprland configuration below.
-- >>> hyprconf >>>  (managed block from hypr/hyprland.block.lua: loadfile()s
--                    conf.d/local.lua, windowrules.lua, workspacerules.lua)
-- <<< hyprconf <<<
```

Because the overrides load *after* the defaults, each file states only where
hyprconf differs. Diff against `/usr/share/omarchy/default/hypr/*.lua` before
adding a value — restating a default creates drift when Omarchy retunes it.

---

## Monitor Syntax

```lua
hl.monitor({ output = NAME, mode = "RESOLUTION@HZ", position = "POSITION", scale = SCALE })
```

| Field | Type | Examples |
|---|---|---|
| `output` | string | `"HDMI-A-1"`, `"DP-1"`, `"eDP-1"`, `""` (catch-all — any unlisted connector) |
| `mode` | string | `"3840x2160@120"`, `"1920x1200"`, `"preferred"`, `"highres"`, `"highrr"` |
| `position` | string | `"0x0"`, `"auto"`, `"auto-right"`, `"auto-left"`, `"auto-up"`, `"auto-down"` |
| `scale` | string \| number | `1`, `1.5`, `2`, `"auto"` |
| `disabled` | boolean | `true` disables the output |

**Extra fields** (same table):

| Key | Type | Values | Notes |
|---|---|---|---|
| `vrr` | integer | `0` off · `1` always · `2` fullscreen | Adaptive sync |
| `bitdepth` | integer | `8` · `10` | 10-bit requires an HDR-capable output |
| `cm` | string | `"auto"` · `"srgb"` · `"dcip3"` · `"dp3"` · `"adobe"` · `"wide"` · `"edid"` · `"hdr"` · `"hdredid"` | Colour management preset |
| `sdrbrightness` | number | default `1.0` | SDR brightness multiplier in HDR mode |
| `sdrsaturation` | number | default `1.0` | SDR saturation multiplier in HDR mode |
| `supports_hdr` | integer / boolean | `-1` off · `0` auto · `1` on | Force HDR support |
| `transform` | integer | `0`–`7` | 0=normal, 1=90°, 2=180°, 3=270°, 4=flipped, 5–7=flipped+rotation |
| `mirror` | string | monitor name | Mirror another output |

```lua
-- From hypr/pcMonitors.bedroom.lua / pcMonitors.kitchen.lua
hl.monitor({ output = "HDMI-A-2", mode = "3840x2160@119.88", position = "0x0", scale = 1.5, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.3 })
hl.monitor({ output = "DP-5", mode = "3840x2160@60", position = "0x0", scale = 2, transform = 1 })
hl.monitor({ output = "DP-4", disabled = true })
```

Later `hl.monitor()` calls for the same `output` override earlier ones.

### Workspace pinning and render (per preset)

```lua
hl.workspace_rule({ workspace = "1", monitor = "HDMI-A-2" })
hl.config({ render = { direct_scanout = 1, cm_auto_hdr = 1 } })
```

`switch_monitor.sh` parses a preset's `hl.workspace_rule` lines to move existing
workspaces after the reload — keep them one per line, in that exact form.

Wiki: <https://wiki.hypr.land/Configuring/Basics/Monitors/>

---

## Keybinds

### `hl.bind` (Hyprland)

```lua
hl.bind(keys, dispatcher)                                        -- normal
hl.bind(keys, dispatcher, { repeating = true })                  -- repeats while held
hl.bind(keys, dispatcher, { locked = true })                     -- fires when locked
hl.bind(keys, dispatcher, { mouse = true })                      -- mouse-button bind
hl.unbind(keys)                                                  -- remove a bind (matches what was declared)
```

### `o.bind` (Omarchy) — what this overlay uses

Defined in `/usr/share/omarchy/default/hypr/helpers.lua`:

```lua
o.bind(keys, description, dispatcher, options)
-- description is recorded in options.description — that is what
-- omarchy-menu-keybindings (SUPER+K) lists. A string dispatcher becomes
-- hl.dsp.exec_cmd(dispatcher).
```

`hypr/bindings.lua`'s own helpers:

```lua
local mainMod = "SUPER"

local function rebind(keys, description, dispatcher, options)
  hl.unbind(keys)                                   -- Hyprland does not replace on re-bind: both would fire
  o.bind(keys, description, dispatcher, options)
end

-- Omarchy declares digits and -/= by KEYCODE (o.bind("SUPER + SHIFT + code:20", …)),
-- which hl.unbind of the keysym does not match — clear those explicitly.
local KEYCODE = { ["1"] = 10, ["2"] = 11, ["4"] = 13, ["5"] = 14, ["6"] = 15,
                  ["7"] = 16, ["8"] = 17, ["9"] = 18, ["0"] = 19, minus = 20, equal = 21 }
local function unbind_keycode(mods, key)
  local code = KEYCODE[key]
  if code then hl.unbind(mods .. " + code:" .. code) end
end

rebind(mainMod .. " + T", "Terminal", hl.dsp.exec_cmd("omarchy-launch-terminal"))
rebind(mainMod .. " + SHIFT + right", "Expand window right", hl.dsp.window.resize({ x = 40, y = 0 }), { repeating = true })
rebind(mainMod .. " + mouse:272", "Move window", hl.dsp.window.drag(), { mouse = true })
unbind_keycode(mainMod .. " + SHIFT", "4")
hl.unbind(mainMod .. " + SHIFT + 4")
o.bind(mainMod .. " + SHIFT + 4", "Screenshot region", "omarchy-capture-screenshot region")
```

### Common dispatchers (`hl.dsp.*`)

| Dispatcher | Args | Effect |
|---|---|---|
| `hl.dsp.exec_cmd(cmd)` | command string | Run a command |
| `hl.dsp.window.close()` | — | Close focused window |
| `hl.dsp.window.float({action="toggle"})` | — | Float/un-float |
| `hl.dsp.window.fullscreen()` | — | Toggle fullscreen |
| `hl.dsp.window.pseudo()` | — | Pseudotile toggle |
| `hl.dsp.focus({direction=...})` | `"left"`/`"right"`/`"up"`/`"down"` | Move focus |
| `hl.dsp.focus({workspace=...})` | N / `"e+1"` / `"e-1"` | Switch workspace |
| `hl.dsp.window.move({workspace=...})` | N / `"special:name"` | Move window to workspace |
| `hl.dsp.window.resize({x=,y=})` | dx, dy | Resize active window |
| `hl.dsp.window.swap({direction=...})` | direction | Swap with neighbour |
| `hl.dsp.window.drag()` | — | Mouse move (with `{ mouse = true }`) |
| `hl.dsp.workspace.toggle_special(name)` | name | Show/hide scratchpad |
| `hl.dsp.workspace.move({workspace=N, monitor="…"})` | — | Rehome a workspace (used by `switch_monitor.sh`) |
| `hl.dsp.dpms({action="enable"})` | `enable`/`disable`/`toggle` | Display power |

Wiki: <https://wiki.hypr.land/Configuring/Basics/Binds/>

---

## Look & Feel

What `hypr/looknfeel.lua` sets (deltas only — see its header for what was
deliberately left to Omarchy: border colours, `border_size`, layout, curves):

```lua
hl.config({
    general = { gaps_in = 3, gaps_out = 3 },
    decoration = {
        rounding = 1, rounding_power = 3,
        active_opacity = 1, inactive_opacity = 0.8,
        shadow = { enabled = true, range = 4, render_power = 3, color = "rgba(1a1a1aee)" },
        blur   = { enabled = true, size = 3, passes = 4, vibrancy = 0.1696 },
    },
})

-- hl.animation({ leaf = TYPE, enabled = ENABLED, speed = SPEED, bezier = CURVE[, style = STYLE] })
hl.animation({ leaf = "windows",       enabled = true, speed = 4.79, bezier = "easeOutQuint" })
hl.animation({ leaf = "workspaces",    enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesIn",  enabled = true, speed = 1.21, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })

hl.config({
    dwindle = { force_split = 0, precise_mouse_move = true, smart_split = true },
    misc    = { force_default_wallpaper = 0 },
})
```

- Animation leaves: `global`, `windows`, `windowsIn`, `windowsOut`, `border`,
  `fade`, `fadeIn`, `fadeOut`, `layers`, `layersIn`, `layersOut`, `workspaces`,
  `workspacesIn`, `workspacesOut`. Styles: `slide`, `popin [percent%]`, `fade`.
- Curves: `hl.curve("name", { type = "bezier", points = { {x1, y1}, {x2, y2} } })`
  (Omarchy already defines `easeOutQuint` and `almostLinear`).
- `dwindle.force_split`: `0` follow mouse, `1` left/top, `2` right/bottom.
  `smart_split` makes the cursor position choose the split *direction* too.

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/>,
<https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/>

---

## Input & Gestures

What `hypr/input.lua` sets. Keyboard layout (`kb_layout` …) is deliberately left
to Omarchy, which derives it from `/etc/vconsole.conf`.

```lua
hl.config({
    input = {
        natural_scroll = true,
        touchpad = { natural_scroll = true },
    },
})

-- Since 0.51 there is no workspace_swipe master toggle; the gesture must be
-- declared or swiping does nothing. Directions: swipe/horizontal/vertical/
-- left/right/up/down/pinch/pinchin/pinchout. Actions: workspace, move, resize,
-- special, close, fullscreen, float, cursorZoom, scroll_move, unset.
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

hl.config({
    gestures = {
        workspace_swipe_invert = true,
        workspace_swipe_distance = 300,
        workspace_swipe_min_speed_to_force = 15,
        workspace_swipe_cancel_ratio = 0.5,
        workspace_swipe_create_new = true,
        workspace_swipe_direction_lock = true,
        workspace_swipe_direction_lock_threshold = 10,
        workspace_swipe_forever = true,
    },
})

-- Per-device overrides (name from `hyprctl devices`)
hl.device({ name = "some-mouse", sensitivity = -0.5 })
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/#input>

---

## Window Rules

Written by the TUI to `~/.config/hypr/conf.d/windowrules.lua`, one per line:

```lua
-- hl.window_rule({ name = "...", match = { PROP = value, ... }, EFFECT = value, ... })
hl.window_rule({ match = { class = "pavucontrol" }, float = true })
hl.window_rule({ match = { class = "hyprconf" }, float = true, center = true, size = "820 440" })
```

**Common effects:** `float`, `tile`, `fullscreen`, `center`, `size = "W H"`,
`move = "X Y"`, `pin`, `opacity`, `no_blur`, `rounding`, `border_size`,
`workspace`, `no_auto_hdr`.

**Match fields:** `class`, `title`, `float`, `fullscreen`, `workspace`, `xwayland`.

Omarchy's own helper for the same thing is `o.window("class", { … })`
(see the tail of its `hyprland.lua` template).

Wiki: <https://wiki.hypr.land/Configuring/Basics/Window-Rules/>

---

## Workspace Rules

Written by the TUI to `~/.config/hypr/conf.d/workspacerules.lua`; monitor
presets carry their own.

```lua
hl.workspace_rule({ workspace = "1", monitor = "NAME" })
hl.workspace_rule({ workspace = "1", default = true })
hl.workspace_rule({ workspace = "1", gaps_out = 0, gaps_in = 0 })  -- "smart gaps"
hl.workspace_rule({ workspace = "special:name" })                  -- named scratchpad
```

Workspace rules only place *future* workspaces — after a reload, existing ones
stay where they were, which is why `switch_monitor.sh` dispatches
`hl.dsp.workspace.move` for each rule.

Wiki: <https://wiki.hypr.land/Configuring/Basics/Workspace-Rules/>

---

## Color Format

`rgba(RRGGBBAA)` hex strings, as plain quoted Lua strings:

```lua
"rgba(1a1a1aee)"   -- R=1a G=1a B=1a A=ee
"rgba(00000000)"   -- fully transparent
col = { active_border = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 } }
col = { active_border = "rgba(33ccffee) rgba(00ff99ee) 45deg" }   -- equivalent
```

(Border colours are not set by this overlay — the active Omarchy theme owns them.)

---

## Runtime: hyprctl on 0.56

`hyprctl` is IPC to the running compositor. With the Lua parser some 0.55 forms
are dead:

```bash
hyprctl reload                                                   # re-run the config

# hyprctl keyword general:gaps_out 10   ← NO-OP on 0.56: prints "keyword can't work
#                                          with non-legacy parsers. Use eval." and exits 0
hyprctl eval 'hl.config({ general = { gaps_in = 5, gaps_out = 5 } })'   # answers "ok"; exit 7 on error
hyprctl eval 'hl.monitor({ output = "DP-1", mode = "preferred", position = "auto", scale = 2 })'

# hyprctl dispatch dpms on              ← 0.55-ism, syntax error under Lua
hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'
hyprctl dispatch 'hl.dsp.workspace.move({ workspace = 7, monitor = "HDMI-A-2" })'

hyprctl getoption general:gaps_in -j    # 0.56 reports four-sided gaps under "css" (older: "custom")
hyprctl monitors [all] | clients | devices | activeworkspace
```

`adjust-gaps`, `switch_monitor.sh` and the TUI's live apply all use the `eval` /
Lua-dispatch forms above.

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Using-hyprctl/>

---

## hyprconf TUI

`hyprconf` (Textual, `tui/main.py`) edits every option section from
`lib/hyprconf/schema.py` (`SECTION_ORDER`) plus keybinds, window/workspace
rules, monitors, and Omarchy's theme / background / idle settings. Writes go to:

| Section | File |
|---|---|
| options | `~/.config/hypr/conf.d/local.lua` — one nested `hl.config({...})` call |
| keybinds | `~/.config/hypr/bindings.lua` — `o.bind` / `rebind` / `hl.bind`, one per line |
| window/workspace rules | `~/.config/hypr/conf.d/windowrules.lua`, `workspacerules.lua` |
| monitors | `~/.config/hypr/monitors.lua` |
| idle | `idle` block of `~/.config/omarchy/shell.json` |

Persistence keys are `section:subsection:key` internally; live apply is
`hyprctl eval` (`hl.config` / `hl.monitor`), never `hyprctl keyword`. The
`conf.d/*.lua` files are loaded by the managed block in `hyprland.lua`
(`hypr/hyprland.block.lua`).
