# hypr — Hyprland deltas for Omarchy

`bindings.lua`, `input.lua` and `looknfeel.lua` are `require`d by Omarchy's
`~/.config/hypr/hyprland.lua` **after** its own defaults and before its toggles
dir (`/usr/share/omarchy/config/hypr/hyprland.lua:14-26`), so each states only
where hyprconf differs — diff `/usr/share/omarchy/default/hypr/*.lua` before
adding a value. `monitors.lua` stays Omarchy's, and the `*Monitors*.lua` presets
are not `require`d from here: `hyprconf-monitor-preset` copies one into
`~/.local/state/omarchy/toggles/hypr/`, loaded last (`default/hypr/toggles.lua:11`),
so its `hl.monitor` calls are the last word. What the keys and the presets do,
for a user, is `README.md` › Keybindings / Monitor presets.

## Binds

- `o.bind(keys, description, dispatcher, options)` (`default/hypr/helpers.lua:92-105`),
  never `hl.bind`: only `o.bind` records the description the `SUPER+K` menu lists.
  A string dispatcher becomes `hl.dsp.exec_cmd`; `{ omarchy = "terminal" }` becomes
  `omarchy-launch-terminal` (`helpers.lua:56-61`, `command_from`).
- Hyprland does not replace a bind on a repeat of the same combo — both fire — so
  every key taken over is `hl.unbind`ed first (`rebind()`). Omarchy declares the
  digits and `-`/`=` by **keycode** (`SUPER + SHIFT + code:20`,
  `default/hypr/bindings/tiling.lua:52-55`), which `hl.unbind` of the keysym does
  not match: `unbind_keycode()` is load-bearing.
- A dispatcher's whole argument set is in its own error text:
  `hyprctl dispatch 'hl.dsp.window.move({ dir = "x" })'`.

## Monitor presets

- `output = "desc:<make> <model>"` prefix-matches Hyprland's `"<make> <model>
  <serial>"`, so make + model is enough and the serial stays out of a tracked file;
  the same selector works in `hl.workspace_rule({ monitor = … })` and
  `hl.dsp.workspace.move`. A named rule beats the `output = ""` catch-all whatever
  the order, disables included. Why not connectors: `README.md` › Monitor presets.
- A file name containing a dot cannot be `require`d (Lua maps dots to path
  separators) — hence the copy in under the dot-free `hyprconf-monitor-preset.lua`.
- Workspace rules place only *future* workspaces, so the tool also dispatches
  `hl.dsp.workspace.move` per `hl.workspace_rule` line — keep them one per line.

## Runtime (Hyprland 0.56.2)

`hyprctl keyword` is a no-op under the Lua parser ("keyword can't work with
non-legacy parsers. Use eval." — and it exits 0); `hyprctl dispatch dpms on` is a
0.55-ism that errors. The live forms, used by `bin/hyprconf-{gaps,monitor-preset}`:

```bash
hyprctl eval 'hl.config({ general = { gaps_in = 5, gaps_out = 5 } })'  # "ok"; exit 7 on error
hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'
```

Syntax beyond these notes: `/usr/share/hypr/stubs/hl.meta.lua`,
`/usr/share/hypr/hyprland.lua`, Omarchy's skill at
`$OMARCHY_PATH/default/agents/skills/omarchy/hyprland.md` and
<https://wiki.hypr.land> — link, never copy.
Verified against Omarchy 4.0.3-1 (Hyprland 0.56.2).
