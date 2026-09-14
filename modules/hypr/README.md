# hypr — Hyprland deltas for Omarchy

## What
Copies `bindings.lua`, `input.lua` and `looknfeel.lua` into `~/.config/hypr/`, `require`d after Omarchy's own defaults
(`config/hypr/hyprland.lua:20-22`) and stating only deltas over `$OMARCHY_PATH/default/hypr/`. Edit in the checkout,
then `hyprconf hypr` (`bash ~/.hyprconf/install.sh hypr`): an `omarchy refresh` or a migration lands on the copy, and
the next run — the post-update hook's included — puts it back. Seeds the `*Monitors*.lua` presets and links
`hyprconf-gaps` and `hyprconf-monitor-preset` into `~/.local/bin`, bound by name in `bindings.lua`.

`hyprconf-monitor-preset <name>` copies a preset — one machine's desk — into `~/.local/state/omarchy/toggles/hypr/`,
loaded after `monitors.lua` (`default/hypr/toggles.lua:4,11`), so its `hl.monitor` lines win and `monitors.lua` is
never touched; `stock` hands the removal to `omarchy-hyprland-toggle`. Without the tool: copy one there and reload.

- `o.bind(keys, description, …)`, never `hl.bind`: only `o.bind` records the description the `SUPER+K` menu lists
  (`default/hypr/helpers.lua:92`); `{ omarchy = "terminal" }` becomes `omarchy-launch-terminal` (`:56,61-62`).
- A repeat of the same combo does not replace a bind — both fire — so `rebind()` unbinds first, the **keycode** form
  included: Omarchy declares digits and `-`/`=` as `SUPER + SHIFT + code:20` (`bindings/tiling.lua:20-25,52-55`).
- `output = "desc:<make> <model>"` prefix-matches `"<make> <model> <serial>"` — make plus model is enough, so no
  serial reaches a tracked file — and the same selector works in `hl.workspace_rule` and `hl.dsp.workspace.move`.
  Never a connector: `DP-N`/`HDMI-A-N` numbering follows the GPU the session drives the displays through, so a cable
  moved between two GPUs renumbers every connector and a connector-keyed preset lights nothing. A named rule beats the
  `output = ""` catch-all whatever the order, disables included; `laptop` stays connector-keyed — it describes no
  particular hardware.
- A dotted filename cannot be `require`d (Lua maps dots to path separators): hence the copy in under
  `hyprconf-monitor-preset.lua`. `hyprctl keyword` is a no-op under the Lua parser (prints "use eval", exits 0):
  the live forms are `hyprctl eval 'hl.config({ … })'` (exit 7 on error) and `hyprctl dispatch 'hl.dsp.…({ … })'`.
- Syntax beyond these notes: `/usr/share/hypr/stubs/hl.meta.lua`, `/usr/share/hypr/hyprland.lua`, Omarchy's skill at
  `$OMARCHY_PATH/default/agents/skills/omarchy/hyprland.md` and <https://wiki.hypr.land> — link, never copy.

## Requires
Omarchy, plus `jq` and `hyprctl` (both always present). No packages, no sudo, no prompt.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/hypr && bash ~/.hyprconf/modules/hypr/install
```

## Keybindings
`mainMod` is `SUPER`. Every key below is bound with `rebind()` over Omarchy's `o.bind`, so it shows in `SUPER+K`; a key
taken over from Omarchy is unbound first, its keycode form (`code:10…21`) included, so only one binding fires. Launchers
are named the way Omarchy names them (`{ omarchy = "terminal" }`), hyprconf's own tools by command name from
`~/.local/bin`. The keymap is `bindings.lua` in this folder — edit it here, then `hyprconf hypr`.

| Key | Action |
|---|---|
| `SUPER+T` | Terminal (`omarchy-launch-terminal` — follows `omarchy default terminal`) |
| `SUPER+F` | Browser (`omarchy-launch-browser`) |
| `SUPER+C` | Editor (`omarchy-launch-editor`) |
| `SUPER+E` | File manager (`omarchy-launch-nautilus`) |
| `SUPER+D` | Omarchy menu (`omarchy-menu toggle`) — Omarchy's own menu key is `SUPER+SPACE`, which stays |
| `SUPER+Q` | Close window |
| `SUPER+SHIFT+Q` | Log out (`omarchy-system-logout`) |
| `SUPER+V` / `SUPER+SHIFT+SPACE` | Toggle window floating |
| `SUPER+SHIFT+F` | Full screen |
| `SUPER+SHIFT+← → ↑ ↓` | Shrink/expand window (repeating) |
| `SUPER+SHIFT+A / D / W / S` | Move window left / right / up / down — and onto the neighbouring monitor when there is no window that way |
| `SUPER+SHIFT+=` / `SUPER+SHIFT+-` | Increase / decrease window gaps (`hyprconf-gaps`, runtime only — a reload restores the configured values) |
| `SUPER+1, 2, 5–0` / `SUPER+SHIFT+1, 2, 5–0` | Switch to / move window to workspace 1, 2, 5–10 |
| `SUPER+F1` / `SUPER+F2` (+ `SHIFT`) | Switch to / move window to workspace 3 / 4 |
| `SUPER+3` / `SUPER+4` / `SUPER+SHIFT+3` | Left to Omarchy (workspace 3 / 4; move window to 3) |
| `SUPER+M` / `SUPER+SHIFT+M` | Toggle magic scratchpad / move window to it |
| `SUPER+L` / `SUPER+SHIFT+Escape` | Lock system (`omarchy-system-lock`) |
| `SUPER+SHIFT+4` | Screenshot region (`omarchy-capture-screenshot region`) |
| `SUPER+SHIFT+V` | Clipboard history (`omarchy-menu-clipboard`) |
| `SUPER+SHIFT+BACKSPACE` | Toggle laptop display (`omarchy-hyprland-monitor-internal toggle`) |
| `SUPER+SHIFT+B` / `SUPER+SHIFT+K` | Monitor preset bedroom / kitchen |

**Left to Omarchy on purpose:** volume, brightness and media keys (Omarchy's drive its OSD and media service), `SUPER+K`,
`SUPER+SPACE`, `SUPER+3`/`4`, `SUPER+SHIFT+3` — and its own `SUPER+P` (pseudo), `SUPER+← → ↑ ↓` (focus), `SUPER+scroll`
(workspace scroll) and `SUPER+LMB`/`RMB` drag (move/resize), which hyprconf does not restate (`default/hypr/bindings/tiling.lua`).
**Displaced Omarchy defaults** (`default/hypr/bindings/*.lua`; each still reachable by command or by another Omarchy key):

| Key | Omarchy's binding | Still available as |
|---|---|---|
| `SUPER+T` | Toggle window floating | hyprconf's `SUPER+V` |
| `SUPER+F` | Full screen | hyprconf's `SUPER+SHIFT+F` |
| `SUPER+C` / `SUPER+V` | Universal copy / paste | `CTRL+C` / `CTRL+V` in the app |
| `SUPER+SHIFT+F` | File manager (`omarchy-launch-nautilus`) | hyprconf's `SUPER+E`; Omarchy's `SUPER+ALT+SHIFT+F` (cwd) |
| `SUPER+SHIFT+B` | Browser (`omarchy-launch-browser`) | hyprconf's `SUPER+F`; Omarchy's `SUPER+SHIFT+RETURN` |
| `SUPER+SHIFT+← → ↑ ↓` | Swap window | Nothing binds swap any more — hyprconf's `SUPER+SHIFT+A / D / W / S` *moves* the window in the layout instead, which in a two-window split reads the same and, unlike swap, also crosses to the next monitor |
| `SUPER+SHIFT+-` / `SUPER+SHIFT+=` | Shrink window up / expand window down (keycode binds `code:20`/`code:21`) | Omarchy's `SUPER+SHIFT+ALT+-`/`=` (a little) and `SUPER+CTRL+SHIFT+-`/`=` (a lot) |
| `SUPER+SHIFT+4` | Move window to workspace 4 (`SUPER+SHIFT+code:13`) | hyprconf's `SUPER+SHIFT+F2` |
| `SUPER+SHIFT+SPACE` | Toggle top bar | `omarchy toggle bar` |
| `SUPER+L` | Toggle workspace layout | `omarchy-hyprland-workspace-layout-toggle`; lock stays on Omarchy's `SUPER+CTRL+L` too |
| `SUPER+SHIFT+BACKSPACE` | Toggle window gaps | `omarchy-hyprland-window-gaps-toggle` |
| `SUPER+SHIFT+A` / `D` / `W` / `S` / `M` | ChatGPT / Docker / Omawrite / Google Maps / Music — only while Omarchy's preinstalled-app bindings are on (`o.preinstalled_bindings_enabled()`: until `~/.local/state/omarchy/preinstalls-removed` exists) | `omarchy-launch-webapp`, `omarchy-launch-docker-tui` (lazydocker behind Omarchy's polkit gate — the socket is root-owned), `omawrite`, `omarchy-launch-spotify` |

## Look'n'feel and input deltas
Only what differs from `$OMARCHY_PATH/default/hypr/`:

| File | Setting | hyprconf | Omarchy |
|---|---|---|---|
| `looknfeel.lua` | `general.gaps_in` / `gaps_out` | 3 / 3 | 5 / 10 |
| | `decoration.rounding` / `rounding_power` | 1 / 3 | 0 / – |
| | `decoration.inactive_opacity` | 0.8 — Omarchy tags every window `+default-opacity` (`default/hypr/windows.lua:6`) and applies `opacity = "0.985 0.96"` to the tag (`:25`), so the effective inactive alpha is ~0.77, while the apps Omarchy takes out of the tag with `tag = "-default-opacity", opacity = "1 1"` (`apps/steam.lua:3`, `apps/qemu.lua:1`) come out at exactly 0.8 | 1 |
| | `decoration.shadow` | on | off |
| | `decoration.blur` | on (size 3, passes 4) | off |
| | animations | `windows` easeOutQuint 4.79; `workspaces`/`In`/`Out` fade | workspaces animation off |
| | `dwindle.force_split` / `precise_mouse_move` / `smart_split` | 0 / true / true | 2 / – / – |
| | window rules: class `steam` | **tiled** (`o.window("steam", { tile = true })`; the Friends List stays floating) | every Steam window floats (`default/hypr/apps/steam.lua`) |
| `input.lua` | `input.natural_scroll` + `touchpad.natural_scroll` | true | false |
| | `hl.gesture` 3-finger horizontal → workspace | on | – |
| | `gestures.workspace_swipe_min_speed_to_force` / `workspace_swipe_forever` | 15 / true | – (Hyprland: 30 / false) |

Border and shadow colours stay with the active Omarchy theme; keyboard layout stays with Omarchy's `input.lua` logic.

## Monitor presets
| Preset | File | Hotkey |
|---|---|---|
| `bedroom` | `~/.config/hypr/pcMonitors.bedroom.lua` | `SUPER+SHIFT+B` |
| `kitchen` | `~/.config/hypr/pcMonitors.kitchen.lua` | `SUPER+SHIFT+K` |
| `laptop` | `~/.config/hypr/laptopMonitors.lua` | — |
| `stock` | — (`omarchy-hyprland-toggle hyprconf-monitor-preset off` removes the toggle file; Omarchy's `monitors.lua` alone speaks) | — |

`hyprconf-monitor-preset <preset>` copies the preset (never links it) to `~/.local/state/omarchy/toggles/hypr/hyprconf-monitor-preset.lua`,
then `hyprctl reload`, then moves each existing workspace to the monitor Hyprland's own parsed rules name — a reload
only places *future* workspaces — and issues one `dpms` wake, the way `omarchy-hyprland-monitor-internal` does after its
own enable. Feedback goes through `omarchy-osd` and `omarchy-notification-send`; `-h` lists the presets it finds. The
`on` half of Omarchy's toggle cannot be reused (it reads only `$OMARCHY_PATH/default/hypr/toggles/`), so the copy is the
tool's own. Each preset carries its workspace-to-monitor rules, and an edit to one survives re-selecting it.

## Settings
No set-once marker — nothing here is a one-time choice. A seeded preset is yours to edit and is never overwritten;
delete it to re-seed. A new preset is one more `*Monitors*.lua` file in this folder: the seed and the tool's `-h` line
both derive from the glob.

## Undo
`bash modules/hypr/install undo` — `hyprconf-monitor-preset stock`, then `omarchy-refresh-config` puts each override
back to Omarchy's own template (the copy is removed first, so no `.bak` is left), the seeded presets and the two
`~/.local/bin` links go, `hyprctl reload`. Safe on a machine that never installed: exit 0, and what lands is Omarchy's
own template at each of the three paths.

## Verified against
Omarchy 4.0.3-1 (Hyprland 0.56.2). Every `file:line` above was read from `/usr/share/omarchy` at that version.
