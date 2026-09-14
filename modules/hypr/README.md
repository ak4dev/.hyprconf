# hypr — Hyprland deltas for Omarchy

## What
Copies `bindings.lua`, `input.lua` and `looknfeel.lua` into `~/.config/hypr/`, `require`d after Omarchy's own defaults
(`config/hypr/hyprland.lua:20-22`) and stating only deltas over `$OMARCHY_PATH/default/hypr/`. Edit in the checkout,
then `hyprconf hypr`: an `omarchy refresh` lands on the copy, the next run puts it back. Seeds the `*Monitors*.lua`
presets and links `hyprconf-gaps` and `hyprconf-monitor-preset` into `~/.local/bin`, bound by name in `bindings.lua`.

`hyprconf-monitor-preset <name>` copies a preset — one machine's desk — into `~/.local/state/omarchy/toggles/hypr/`,
loaded after `monitors.lua` (`default/hypr/toggles.lua:4,11`), so its `hl.monitor` lines win and `monitors.lua` is
never touched; `stock` hands the removal to `omarchy-hyprland-toggle`. Without the tool: copy one there and reload.

- `o.bind(keys, description, …)`, never `hl.bind`: only `o.bind` records the description the `SUPER+K` menu lists
  (`default/hypr/helpers.lua:92`); `{ omarchy = "terminal" }` becomes `omarchy-launch-terminal` (`:56,61-62`).
- A repeat of the same combo does not replace a bind — both fire — so `rebind()` unbinds first, the **keycode** form
  included: Omarchy declares digits and `-`/`=` as `SUPER + SHIFT + code:20` (`bindings/tiling.lua:20-25,52-55`).
- `output = "desc:<make> <model>"` prefix-matches `"<make> <model> <serial>"` — make plus model is enough, so no
  serial reaches a tracked file — and the same selector works in `hl.workspace_rule` and `hl.dsp.workspace.move`.
- A dotted filename cannot be `require`d (Lua maps dots to path separators): hence the copy in under
  `hyprconf-monitor-preset.lua`. `hyprctl keyword` is a no-op under the Lua parser (prints "use eval", exits 0):
  the live forms are `hyprctl eval 'hl.config({ … })'` (exit 7 on error) and `hyprctl dispatch 'hl.dsp.…({ … })'`.

## Requires
Omarchy, plus `jq` and `hyprctl` (both always present). No packages, no sudo, no prompt.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/hypr && bash ~/.hyprconf/modules/hypr/install
```

## Settings
No set-once marker — nothing here is a one-time choice. A seeded preset is yours to edit and is never overwritten; delete it to re-seed.

## Undo
`bash modules/hypr/install undo` — `hyprconf-monitor-preset stock`, then `omarchy-refresh-config` puts each override
back to Omarchy's own template, the seeded presets and the two `~/.local/bin` links go, `hyprctl reload`.

## Verified against
Omarchy 4.0.3-1 (Hyprland 0.56.2). Every `file:line` above was read from `/usr/share/omarchy` at that version.
