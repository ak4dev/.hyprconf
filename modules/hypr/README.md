# hypr — Hyprland deltas for Omarchy

## What
Copies `bindings.lua`, `input.lua` and `looknfeel.lua` into `~/.config/hypr/`, `require`d after Omarchy's own defaults
(`config/hypr/hyprland.lua:20-22`) and stating only deltas over `$OMARCHY_PATH/default/hypr/`. Edit in the checkout,
then `hyprconf hypr` (`bash ~/.hyprconf/install.sh hypr`): an `omarchy refresh` or a migration lands on the copy, and
the next run — the post-update hook's included — puts it back. A file of your own at one of those paths, or a
dotfiles link, is kept once as `<file>.lua.stock` (said in one line; Omarchy's own template is not — undo restores it
anyway). Seeds the `*Monitors*.lua` presets and links `hyprconf-gaps` and `hyprconf-monitor-preset` into
`~/.local/bin`, bound by name in `bindings.lua`.

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
`mainMod` is `SUPER`. Every key below goes through `rebind()` over Omarchy's `o.bind`, so it shows in `SUPER+K`; a key
taken over from Omarchy is unbound first, its keycode form included, so only one binding fires. `SUPER+K` lists what
is live and `/usr/share/omarchy/default/hypr/bindings/` what was displaced; the displaced-by notes that matter are
comments beside their binds in `bindings.lua`, which is the keymap — edit it here, then `hyprconf hypr`.

| Key | Action |
|---|---|
| `SUPER+T` / `F` / `C` / `E` | Terminal / browser / editor / file manager — Omarchy's launchers, following `omarchy default …` |
| `SUPER+D` | Omarchy menu (Omarchy's own menu key, `SUPER+SPACE`, stays) |
| `SUPER+Q` / `SUPER+SHIFT+Q` | Close window / log out |
| `SUPER+V` / `SUPER+SHIFT+SPACE` | Toggle window floating |
| `SUPER+SHIFT+F` | Full screen |
| `SUPER+SHIFT+← → ↑ ↓` | Shrink / expand window (repeating) |
| `SUPER+SHIFT+A / D / W / S` | Move window left / right / up / down — onto the neighbouring monitor when no window is that way |
| `SUPER+SHIFT+=` / `SUPER+SHIFT+-` | Increase / decrease window gaps (`hyprconf-gaps`, runtime only — a reload restores the configured values) |
| `SUPER+1, 2, 5–0` / `SUPER+SHIFT+1, 2, 5–0` | Switch to / move window to workspace 1, 2, 5–10 |
| `SUPER+F1` / `SUPER+F2` (+ `SHIFT`) | Switch to / move window to workspace 3 / 4 |
| `SUPER+M` / `SUPER+SHIFT+M` | Toggle magic scratchpad / move window to it |
| `SUPER+L` / `SUPER+SHIFT+Escape` | Lock system |
| `SUPER+SHIFT+4` | Screenshot region |
| `SUPER+SHIFT+V` | Clipboard history |
| `SUPER+SHIFT+BACKSPACE` | Toggle laptop display |
| `SUPER+SHIFT+B` / `SUPER+SHIFT+K` | Monitor preset bedroom / kitchen |

**Left to Omarchy on purpose:** volume, brightness and media keys (Omarchy's drive its OSD and media service), `SUPER+K`,
`SUPER+SPACE`, `SUPER+3`/`4`, `SUPER+SHIFT+3` — and its own `SUPER+P` (pseudo), `SUPER+← → ↑ ↓` (focus), `SUPER+scroll`
(workspace scroll) and `SUPER+LMB`/`RMB` drag (move/resize), which hyprconf does not restate (`default/hypr/bindings/tiling.lua`).

## Look'n'feel and input deltas
Tighter gaps (3/3), hairline rounding, translucent unfocused windows — `inactive_opacity` 0.8; Omarchy tags every window
`+default-opacity` and applies `opacity = "0.985 0.96"` to the tag (`default/hypr/windows.lua:6,25`), so the effective
inactive alpha is ~0.77, while the apps it takes out of the tag (`apps/steam.lua:3`, `apps/qemu.lua:1`) come out at
exactly 0.8 — blur and shadow on, an easeOutQuint window animation with fading workspaces, cursor-driven dwindle splits,
natural scroll, a 3-finger workspace swipe, and Steam tiled like every other window (the Friends List stays floating).
Only deltas from `$OMARCHY_PATH/default/hypr/`: each value and its reason are commented where it is set, in
`looknfeel.lua` and `input.lua`. Border and shadow colours stay with the active Omarchy theme; keyboard layout stays with
Omarchy's `input.lua` logic.

## Monitor presets
| Preset | File | Hotkey |
|---|---|---|
| `bedroom` | `~/.config/hypr/pcMonitors.bedroom.lua` | `SUPER+SHIFT+B` |
| `kitchen` | `~/.config/hypr/pcMonitors.kitchen.lua` | `SUPER+SHIFT+K` |
| `laptop` | `~/.config/hypr/laptopMonitors.lua` | — |
| `stock` | — (`omarchy-hyprland-toggle hyprconf-monitor-preset off` removes the toggle file; Omarchy's `monitors.lua` alone speaks) | — |

`hyprconf-monitor-preset <preset>` copies the preset into the toggles directory (never links it), reloads, moves each
existing workspace to the monitor Hyprland's own parsed rules name — a reload only places *future* workspaces — and
issues one `dpms` wake; `-h` lists the presets it finds, and the tool's header carries the seam with its citations.
A preset belongs to the machine: an edit survives re-selecting it.

## Settings
Nothing here is a one-time choice. A seeded preset is yours to edit and is never overwritten; delete it to re-seed —
so a preset improved in this folder would otherwise stop at the checkout in silence. The one marker,
`${HYPRCONF_STATE:-~/.local/state/hyprconf}/<preset>.shipped`, is the preset as this checkout last shipped it: when a
run finds yours differs *and* the shipped one has moved since, it says so in one line and leaves your file alone —
once per shipped version, so an edit of your own never nags. A new preset is one more `*Monitors*.lua` file in this
folder: the seed and the tool's `-h` line both derive from the glob. The two `pcMonitors.*` presets are the author's
desks: on another machine delete both, here and the seeded copies in `~/.config/hypr/` — pressed against unknown
displays, `SUPER+SHIFT+B`/`K` would bring every output up at its preferred mode for the session and point
workspaces 1–6 at panels that are not there.

## Undo
`bash modules/hypr/install undo` — `hyprconf-monitor-preset stock`, then each override goes back: a
`<file>.lua.stock` is moved into place — the file of your own the first run set aside, or the one a hyprconf 7.x
install left, which was Omarchy's template of that day (delete it first for the current one) — and where there is
none, `omarchy-refresh-config` puts Omarchy's own template back (the copy is removed first, so no `.bak` is left).
The seeded presets, their `.shipped` markers and the two `~/.local/bin` links go, `hyprctl reload`. Safe on a machine
that never installed: exit 0, and what lands is Omarchy's own template at each of the three paths.

## Verified against
Omarchy 4.0.3-1 (Hyprland 0.56.2). Every `file:line` above was read from `/usr/share/omarchy` at that version.
