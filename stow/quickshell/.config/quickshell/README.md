# Quickshell bar (experiment)

QtQuick replacement for the waybar setup, mirroring `stow/waybar`'s layout
and module set, then extending it with frosted-glass popouts, a volume OSD,
and rounded screen corners. Colors are driven live by hyprconf's theme
switcher. Lives on the `feat/quickshell-bar` branch; waybar's config is
untouched and its exec line is kept (commented) in `hyprland.conf` for
rollback.

## Runtime

`launch.sh` prefers `qs` from the official `quickshell` package (repo:
`extra`). Until that is installed, it falls back to a user-local package
tree at `~/.local/opt/quickshell` (extracted `quickshell` + `cpptrace` +
`libdwarf` Arch packages, GPG-signature verified against the pacman keyring;
the Qt6 stack comes from the system). To switch to the real package:

```sh
sudo pacman -S quickshell
rm -rf ~/.local/opt/quickshell
hyprctl reload
```

## Theming

`Theme.qml` reads the *same source of truth* as waybar/kitty/dunst: the
active theme name in `~/.config/hypr/.current-theme` selects
`theme-switcher/themes/<name>.json`, whose keys (`background`, `foreground`,
`comment`, `accent`, `cyan`, `green`, `red`, `orange`, `purple`) drive the
bar. `yellow`/`pink` fall back to fixed values when a theme omits them, just
like waybar. Both files are watched, so switching themes recolors the bar
live with no restart. Translucent tokens (bar/popout/OSD surfaces) are
derived from the theme background at reduced alpha.

## Bar modules

Left: workspaces island (native Hyprland IPC, scroll to cycle) · window
title. Center: clock. Right: screencast indicator · tray · cpu · cpu-temp ·
memory · gpu · vpn · network · volume · battery.

The cpu-temp, GPU, VPN, and battery modules re-run the existing scripts from
`~/.config/waybar/` unchanged via `ScriptModule`, so their hermetic tests
still cover them. cpu/mem/net come from one long-lived `stats.sh` sampler.

## Popouts & extras (quickshell-only)

Borderless frosted panels blurred by Hyprland (`layerrule` in
`hyprland.conf`), each dismissed by clicking outside (`HyprlandFocusGrab`):

- **Calendar** (click clock) — live time/date header + month grid with
  weekend shading, today highlighted; prev/next, click title for today.
- **Volume** (click volume) — slider, mute, output-device switcher.
- **Network** (click network) — interface, IPv4, live rates, session totals.
- **Volume OSD** — macOS-style pill at the bottom of the focused monitor on
  volume/mute change; input-transparent, auto-hides.
- **Screen corners** — cosmetic rounded bezel, one overlay per monitor,
  fully click-through (empty input region).

Tray icons: left-click activates, middle-click is the secondary action, and
right-click (or left-click for menu-only items) opens the item's menu as a
frosted `TrayMenuPopout`. Quickshell's native menu APIs
(`SystemTrayItem.display()`, `QsMenuAnchor`) render nothing in this
layer-shell bar, so the menu is custom-drawn. **Known limitation:** nested
dbusmenu submenus (the Wi-Fi network list, audio-profile pickers) render
empty inside the layer-shell popup in Quickshell 0.3.0 — the top-level menu
(Enable Wi-Fi, Disconnect, Connection Information, Edit Connections, …)
works.

Module gestures: volume scroll = ±5%, middle-click = mute, right-click =
pavucontrol; workspaces scroll = switch; clock middle-click = toggle date
format.

### Popout IPC / keybinds

`IpcHandler` target `popouts` exposes `toggle <calendar|volume|network>`
(the name is validated against a fixed list and never executed). Once the
`quickshell` package is installed so `qs` is on `PATH`, these can be bound in
`keybinds.conf`, e.g.:

```
bind = $mainMod, C, exec, qs ipc call popouts toggle calendar
```

## Security notes

- No network I/O — only local sockets (Hyprland IPC, Pipewire, D-Bus SNI).
- All externally-controlled strings (window titles, tray menu labels) render
  as `Text.PlainText` — never rich text, never interpolated into a shell.
- Subprocess calls use `Quickshell.execDetached([...])` argv arrays (no
  `sh -c`); the reused waybar scripts are unchanged.
- `Theme.qml` only *reads* theme files; it never writes or executes them.

## Not yet done

- Tooltips for the plain modules (memory %, GPU details).
- `hyprconf setup` integration / package-list entry for `quickshell`.
- Popout keybinds are documented above but not added to `keybinds.conf`
  (they need the `qs` binary on `PATH`, i.e. the installed package).
