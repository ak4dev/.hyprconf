# Quickshell bar (experiment)

QtQuick replacement for the waybar setup, mirroring `stow/waybar`'s layout,
colors, and module set, then extending it with frosted-glass popouts, a
volume OSD, a custom tray menu, and rounded screen corners. Lives on the
`feat/quickshell-bar` branch; waybar's config is untouched and its exec line
is kept (commented) in `hyprland.conf` for rollback.

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

## Bar modules

Left: workspaces island (native Hyprland IPC, scroll to cycle) · window
title. Center: clock. Right: screencast indicator · media · tray · cpu ·
cpu-temp · memory · gpu · vpn · network · volume · battery.

The cpu-temp, GPU, VPN, and battery modules re-run the existing scripts from
`~/.config/waybar/` unchanged via `ScriptModule`, so their hermetic tests
still cover them. cpu/mem/net come from one long-lived `stats.sh` sampler.

## Popouts & extras (quickshell-only)

Frosted panels blurred by Hyprland (`layerrule` in `hyprland.conf`), each
dismissed by clicking outside (`HyprlandFocusGrab`):

- **Calendar** (click clock) — month view, prev/next, click title for today.
- **Volume** (click volume) — slider, mute, output-device switcher.
- **Network** (click network) — interface, IPv4, live rates, session totals.
- **Media** (click media) — MPRIS art/title/progress + transport controls.
- **Tray menu** (right-click a tray icon) — custom-rendered SNI/dbusmenu
  with submenus, checkboxes, and icons in the frosted style.
- **Volume OSD** — macOS-style pill at the bottom of the focused monitor on
  volume/mute change; input-transparent, auto-hides.
- **Screen corners** — cosmetic rounded bezel, one overlay per monitor,
  fully click-through (empty input region).

Module gestures: volume scroll = ±5%, middle-click = mute, right-click =
pavucontrol; media middle-click = play/pause; workspaces scroll = switch;
clock middle-click = toggle date format.

### Popout IPC / keybinds

`IpcHandler` target `popouts` exposes `toggle <calendar|volume|network|media>`
(the name is validated against a fixed list and never executed). Once the
`quickshell` package is installed so `qs` is on `PATH`, these can be bound in
`keybinds.conf`, e.g.:

```
bind = $mainMod, C, exec, qs ipc call popouts toggle calendar
```

## Security notes

- No network I/O: album art is only loaded from `file://` URLs; everything
  else is local sockets (Hyprland IPC, Pipewire, D-Bus SNI/MPRIS).
- All externally-controlled strings (window titles, MPRIS metadata, tray
  menu labels) render as `Text.PlainText` — never rich text, never
  interpolated into a shell command.
- Subprocess calls use `Quickshell.execDetached([...])` argv arrays (no
  `sh -c`); the reused waybar scripts are unchanged.

## Differences from waybar (intentional)

- On narrow (portrait) monitors the title elides and the clock slides left;
  waybar let the sections overlap.
- Workspaces, window title, volume, tray, and media are event-driven
  (Hyprland IPC socket, Pipewire/MPRIS native) instead of polled.

## Not yet done

- Tooltips for the plain modules (memory %, GPU details).
- `hyprconf setup` integration / package-list entry for `quickshell`.
- Popout keybinds are documented above but not added to `keybinds.conf`
  (they need the `qs` binary on `PATH`, i.e. the installed package).
