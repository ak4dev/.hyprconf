# Quickshell bar

QtQuick status bar (the waybar replacement — waybar is fully retired): the
same module set plus frosted-glass popouts, a macOS-style Control Center, a
volume OSD, and rounded screen corners. Colors are driven live by hyprconf's
theme switcher. API reference for agents/contributors:
`docs/quickshell-reference.md` (repo) + <https://quickshell.org/docs/> for the
installed version.

## Runtime

`launch.sh` resolves the quickshell binary — preferring `qs` from the official
`quickshell` package (repo: `extra`, listed in `packages`) — and forwards any
arguments, so it serves both the autostart line (no args = run the shell) and
keybind IPC calls (`launch.sh ipc call popouts toggle calendar`). Until the
package is installed it falls back to a user-local tree at
`~/.local/opt/quickshell` (extracted `quickshell` + `cpptrace` + `libdwarf`
Arch packages, GPG-verified against the pacman keyring; the Qt6 stack comes
from the system). To switch to the real package:

```sh
sudo pacman -S quickshell     # or just run `setup.sh --sync` and accept
rm -rf ~/.local/opt/quickshell
hyprctl reload
```

## Theming

`Theme.qml` reads the *same source of truth* as kitty/dunst: the active theme
name in `~/.config/hypr/.current-theme` selects
`theme-switcher/themes/<name>.json`, whose keys (`background`, `foreground`,
`comment`, `accent`, `cyan`, `green`, `red`, `orange`, `purple`) drive the
bar. `yellow`/`pink` fall back to fixed values when a theme omits them. Both
files are watched, so switching themes recolors the bar live with no restart
(the theme switcher has no bar-specific step at all). Translucent tokens
(bar/popout/OSD surfaces) are derived from the theme background at reduced
alpha.

## Bar modules

Left: workspaces island (native Hyprland IPC, scroll to cycle) · window
title. Center: clock. Right: screencast indicator · tray (Bluetooth and
network-manager icons filtered out — both are managed by the Control
Center) · cpu · cpu-temp · memory · gpu · vpn · network · volume · battery.
The network module prefers the ethernet icon when a wired link is up, and
clicking it opens the Control Center.

Every data source runs exactly once in the `Services` singleton and is
bound into each screen's bar (`Bar{}` is per-monitor, so per-Bar processes
would run once per screen): cpu/mem/net/cpu-temp come from the long-lived
`stats.sh` sampler (temperature read straight from a hwmon path resolved at
startup), the GPU module from a long-lived `gpu_info.sh` stream (one
`nvidia-smi --loop` through one awk, or an AMD sysfs loop), the battery
module from a 1s poll that stops entirely on battery-less desktops
(`"once": true`), and the VPN module from a 5s `hyprconf-vpn status --json`
poll. All scripts are hermetically tested
(`tests/unit/test_quickshell_scripts.py`) with `HYPRCONF_*`-overridable
system paths; `ScriptModule` is the shared module chrome (padding,
class→color, hide-when-empty, critical blink, click).

## Popouts & extras

Borderless frosted panels blurred by Hyprland (`layerrule` in
`hyprland.conf`), each dismissed by clicking outside (`HyprlandFocusGrab`):

- **Control Center** (click the network module, or `Super+Shift+N`) —
  macOS-style unified panel:
  - Wi-Fi + Bluetooth toggle tiles.
  - **Wi-Fi network list** — native `Quickshell.Networking` (NetworkManager
    over D-Bus): scans only while the panel is open, click to connect;
    saved/open networks connect directly, secured ones reveal an inline
    password box (`WifiNetwork.connectWithPsk`), and a wrong password
    re-opens it (`connectionFailed(NoSecrets)`).
  - Volume slider + **output and input (mic) device pickers**, mic mute.
  - Bluetooth device list (connect/disconnect, battery).
  - Only *pairing a new Bluetooth device* still opens an app
    (`blueman-manager`); everything else is inline.

  Wi-Fi via `Quickshell.Networking`, Bluetooth via `Quickshell.Bluetooth`,
  audio via Pipewire — all over D-Bus/native sockets. **No subprocesses, no
  polling, and the Wi-Fi password never appears in argv or any process
  list.** The popout sets `WlrLayershell.keyboardFocus: OnDemand` so the
  password box can type.
- **Calendar** (click clock, or `Super+Shift+C`) — live time/date header +
  month grid with weekend shading, today highlighted; prev/next, click title
  for today.
- **Volume** (click volume) — slider, mute, output-device switcher.
- **Volume OSD** — macOS-style pill at the bottom of the focused monitor on
  volume/mute change; input-transparent, auto-hides.
- **Screen corners** — cosmetic rounded bezel, one overlay per monitor,
  fully click-through (empty input region).

Tray icons: left-click activates, middle-click is the secondary action, and
right-click (or left-click for menu-only items) opens the item's menu as a
frosted `TrayMenuPopout`. Quickshell's native menu APIs
(`SystemTrayItem.display()`, `QsMenuAnchor`) render nothing in this
layer-shell bar, so the menu is custom-drawn. **Known limitation:** nested
dbusmenu submenus render empty inside the layer-shell popup in Quickshell
0.3.0 — the top-level menu works. (The old nm-applet menu use-case is gone:
Wi-Fi lives in the Control Center.)

Module gestures: volume scroll = ±5%, middle-click = mute, right-click =
pavucontrol; workspaces scroll = switch; clock middle-click = toggle date
format.

### Popout IPC / keybinds

`IpcHandler` target `popouts` exposes `toggle <calendar|volume|controlcenter>`
(the name is validated against a fixed list and never executed). Bound in
`keybinds.conf` through `launch.sh` (works with either runtime):

```
bind = $mainMod SHIFT, C, exec, ~/.config/quickshell/launch.sh ipc call popouts toggle calendar
bind = $mainMod SHIFT, N, exec, ~/.config/quickshell/launch.sh ipc call popouts toggle controlcenter
```

## Security notes

- No network I/O — only local sockets (Hyprland IPC, Pipewire, D-Bus:
  NetworkManager/BlueZ/SNI).
- All externally-controlled strings (window titles, SSIDs, device names,
  tray menu labels) render as `Text.PlainText` — never rich text, never
  interpolated into a shell. String properties are `??`-guarded so model
  churn can't assign `undefined`.
- Subprocess calls use `Quickshell.execDetached([...])` argv arrays (no
  `sh -c`); the Wi-Fi PSK goes to NetworkManager over D-Bus, never argv.
- `Theme.qml` only *reads* theme files; it never writes or executes them.

## Gotchas

- Quickshell only watches files it has already **loaded** — lazily-loaded
  components (popout contents) may not hot-reload until something watched
  (e.g. `shell.qml`) is touched or `qs` is restarted.
- The `hyprland.conf` exec line is guarded by `pgrep -x 'qs|quickshell'`
  (both names: the process comm is `qs` when the system package is
  installed) so `hyprctl reload` never restarts a running bar (a restart
  tears down the StatusNotifierWatcher and breaks the tray). If quickshell
  is killed, run `hyprctl reload` (or `launch.sh`) to bring it back.

## Not yet done

- Tooltips for the plain modules (memory %, GPU details).
