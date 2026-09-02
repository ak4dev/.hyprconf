# Hyprland Configuration Reference

> Curated cheatsheet of the Lua config syntax this overlay uses in `hypr/*.lua`
> and the monitor presets, for hand-editing them. Full wiki: <https://wiki.hypr.land>.
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
9. [Runtime: hyprctl on 0.56](#runtime-hyprctl-on-056)

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
-- ~/.config/hypr/bindings.lua). A module whose FILE name contains a dot
-- (pcMonitors.bedroom.lua) cannot be require()d, which is why
-- hyprconf-monitor-preset copies a preset into Omarchy's toggles directory
-- under a dot-free name (hyprconf-monitor-preset.lua) instead.
require("hypr.bindings")
```

- One `hl.*(...)` statement per line is this repo's convention (not a Lua
  requirement) — `hyprconf-monitor-preset` parses presets line by line, and a
  one-line entry is what `grep`/`diff` show cleanly.
- **Ground truth:** the installed package's Lua API stub
  (`/usr/share/hypr/stubs/hl.meta.lua`) and example config
  (`/usr/share/hypr/hyprland.lua`). Re-check them before trusting an unfamiliar
  `hl.*` field.

---

## Omarchy's Override Points

Omarchy's `~/.config/hypr/hyprland.lua` (template: `/usr/share/omarchy/config/hypr/hyprland.lua`)
loads its defaults, then `require`s the user files, then its toggles (every
`.lua` under `~/.local/state/omarchy/toggles/hypr/`, `require_all` with reload —
later `hl.monitor` calls win, which is where a monitor preset lands), then
invites personal additions at the tail:

```lua
require("default.hypr.omarchy")   -- Omarchy defaults
require("hypr.monitors")          -- ~/.config/hypr/monitors.lua   ← Omarchy's own; never touched
require("hypr.input")             -- ~/.config/hypr/input.lua      ← symlink to hypr/input.lua
require("hypr.bindings")          -- ~/.config/hypr/bindings.lua   ← symlink to hypr/bindings.lua
require("hypr.looknfeel")         -- ~/.config/hypr/looknfeel.lua  ← symlink to hypr/looknfeel.lua
require("hypr.autostart")         -- left to Omarchy
require("default.hypr.toggles")   -- ~/.local/state/omarchy/toggles/hypr/*.lua ← hyprconf-monitor-preset.lua
-- Add any other personal Hyprland configuration below.
-- o.window("qemu", { workspace = "5" })
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
| `output` | string | `"HDMI-A-1"`, `"DP-1"`, `"eDP-1"`, `"desc:<make> <model>"` (see below), `""` (catch-all — any unlisted output) |
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
hl.monitor({ output = "desc:LG Electronics LG TV SSCR2", mode = "3840x2160@119.88", position = "0x0", scale = 1.6, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.3 })
hl.monitor({ output = "desc:Acer Technologies CB282K", mode = "3840x2160@60.00", position = "0x0", scale = 2, transform = 1 })
hl.monitor({ output = "desc:Samsung Electric Company Odyssey G8", disabled = true })
```

Later `hl.monitor()` calls for the same `output` override earlier ones.

### `desc:` — naming a display instead of a connector

`output` also takes `"desc:<text>"`, which **prefix-matches** the description
`hyprctl monitors all` reports as `"<make> <model> <serial>"` — so make + model
is enough and the serial can be left off (it must be: a serial is PII, and
these files are tracked). `HL.MonitorSpec` in `/usr/share/hypr/stubs/hl.meta.lua`
declares only `output`; the `desc:` prefix lives inside that string. The same
selector works in `hl.workspace_rule({ monitor = ... })` and in
`hyprctl dispatch 'hl.dsp.workspace.move({ … })'`.

Why it matters: `DP-N`/`HDMI-A-N` numbering follows the GPU the session drives
the displays through (probe order, `AQ_DRM_DEVICES`, cabling), so moving a
cable from one GPU to another renumbers every connector — the same three panels
went `HDMI-A-1`/`DP-1`/`DP-2` → `HDMI-A-2`/`DP-4`/`DP-5` on a 3070 → 5090 move,
and every connector-keyed preset then lit nothing. A description follows the
panel. Verified on Hyprland 0.56.2: a `desc:` rule re-scaled a live output, and
the move dispatch answered `ok` for a `desc:` monitor.

A named rule (`desc:` or connector) beats the `output = ""` catch-all whatever
the order, disables included — so a preset can end with a catch-all as a
safety net without it re-enabling what the preset turned off.

### Workspace pinning and render (per preset)

```lua
hl.workspace_rule({ workspace = "1", monitor = "desc:LG Electronics LG TV SSCR2" })
hl.config({ render = { direct_scanout = 1, cm_auto_hdr = 1 } })
```

`hyprconf-monitor-preset` parses a preset's `hl.workspace_rule` lines to move
existing workspaces after the reload — keep them one per line, in that exact form.

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

`hypr/bindings.lua`'s own helpers (see the file):

```lua
rebind(keys, description, dispatcher, options)   -- hl.unbind(keys), then o.bind(...)
unbind_keycode(mods, key)                        -- hl.unbind(mods .. " + code:N") for the digits and -/=
                                                 -- Omarchy binds by keycode (KEYCODE table)
```

Key forms in use there: `mainMod .. " + T"`, `" + SHIFT + F1"`, `" + SHIFT + equal"`,
and `{ repeating = true }` for the resize keys. The mouse forms (`" + mouse:272"`
with `{ mouse = true }`, `" + mouse_down"` / `" + mouse_up"`) are Omarchy's own
binds in `tiling.lua` and are not restated.

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
| `hl.dsp.window.move({direction=...})` | `"left"`/`"right"`/`"up"`/`"down"` | Move window in the layout (to the next monitor when nothing is that way) |
| `hl.dsp.window.resize({x=,y=,relative=true})` | dx, dy | Resize active window |
| `hl.dsp.window.swap({direction=...})` | direction | Swap with neighbour (refuses when there is none) |
| `hl.dsp.window.drag()` | — | Mouse move (with `{ mouse = true }`) |
| `hl.dsp.workspace.toggle_special(name)` | name | Show/hide scratchpad |
| `hl.dsp.workspace.move({workspace=N, monitor="…"})` | — | Rehome a workspace (used by `hyprconf-monitor-preset`) |
| `hl.dsp.dpms({action="enable"})` | `enable`/`disable`/`toggle` | Display power |

`move` and `resize` read `x`/`y` as an EXACT target size unless `relative = true`
is set, and Hyprland rejects a negative one (`error: Invalid size`) — the whole
argument set each accepts is in its own error text: `hyprctl dispatch
'hl.dsp.window.move({ dir = "x" })'`.

Wiki: <https://wiki.hypr.land/Configuring/Basics/Binds/>

---

## Look & Feel

`hypr/looknfeel.lua` states deltas only (the values and the reasoning are in
the file; the delta table is in `README.md`). The forms it uses:

```lua
hl.config({ general = { gaps_in = N, gaps_out = N },
            decoration = { rounding = N, rounding_power = N, inactive_opacity = X,
                           shadow = { enabled, range, render_power, color = "rgba(RRGGBBAA)" },
                           blur = { enabled, size, passes, vibrancy } },
            dwindle = { force_split = N, precise_mouse_move = B, smart_split = B },
            misc = { force_default_wallpaper = N } })
hl.animation({ leaf = TYPE, enabled = B, speed = X, bezier = CURVE[, style = STYLE] })
o.window("class", { tile = true })                                -- Omarchy's window-rule helper
o.window({ class = "steam", title = "Friends List" }, { float = true })
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

`hypr/input.lua` states deltas only (see the file). Keyboard layout
(`kb_layout` …) is deliberately left to Omarchy, which derives it from
`/etc/vconsole.conf`. The forms:

```lua
hl.config({ input = { natural_scroll = B, touchpad = { natural_scroll = B } },
            gestures = { workspace_swipe_* = … } })
-- Since 0.51 there is no workspace_swipe master toggle: the gesture must be
-- declared or the gestures.* tuning applies to nothing.
hl.gesture({ fingers = N, direction = DIR, action = ACTION })
--   DIR:    swipe/horizontal/vertical/left/right/up/down/pinch/pinchin/pinchout
--   ACTION: workspace, move, resize, special, close, fullscreen, float,
--           cursorZoom, scroll_move, unset
hl.device({ name = "some-mouse", sensitivity = -0.5 })   -- per device, name from `hyprctl devices`
```

Wiki: <https://wiki.hypr.land/Configuring/Basics/Variables/#input>

---

## Window Rules

Hand-written, one per line, in the "personal configuration" tail of
`~/.config/hypr/hyprland.lua` (Omarchy's template invites them there):

```lua
-- hl.window_rule({ name = "...", match = { PROP = value, ... }, EFFECT = value, ... })
hl.window_rule({ match = { class = "pavucontrol" }, float = true })
hl.window_rule({ match = { class = "btop" }, float = true, center = true, size = "820 440" })
```

**Common effects:** `float`, `tile`, `fullscreen`, `center`, `size = "W H"`,
`move = "X Y"`, `pin`, `opacity`, `no_blur`, `rounding`, `border_size`,
`workspace`, `no_auto_hdr`.

**Match fields:** `class`, `title`, `float`, `fullscreen`, `workspace`, `xwayland`.

Omarchy's own helper for the same thing is `o.window("class", { … })`
(`/usr/share/omarchy/default/hypr/helpers.lua`; the tail of its `hyprland.lua`
template shows `o.window("qemu", { workspace = "5" })`).

Wiki: <https://wiki.hypr.land/Configuring/Basics/Window-Rules/>

---

## Workspace Rules

Monitor presets (`hypr/*Monitors*.lua`) carry their own, one per line; any
others go in the same `hyprland.lua` tail as window rules.

```lua
hl.workspace_rule({ workspace = "1", monitor = "NAME" })
hl.workspace_rule({ workspace = "1", default = true })
hl.workspace_rule({ workspace = "1", gaps_out = 0, gaps_in = 0 })  -- "smart gaps"
hl.workspace_rule({ workspace = "special:name" })                  -- named scratchpad
```

Workspace rules only place *future* workspaces — after a reload, existing ones
stay where they were, which is why `hyprconf-monitor-preset` dispatches
`hl.dsp.workspace.move` for each rule.

Wiki: <https://wiki.hypr.land/Configuring/Basics/Workspace-Rules/>

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

`hyprconf-gaps` and `hyprconf-monitor-preset` use the `eval` / Lua-dispatch forms above.

Wiki: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Using-hyprctl/>

