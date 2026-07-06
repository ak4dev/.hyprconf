# Quickshell bar (experiment)

QtQuick replacement for the waybar setup, mirroring `stow/waybar`'s layout,
colors, and module set. Lives on the `feat/quickshell-bar` branch; waybar's
config is untouched and its exec line is kept (commented) in `hyprland.conf`
for rollback.

## Runtime

`launch.sh` prefers `qs` from the official `quickshell` package (repo:
`extra`). Until that is installed, it falls back to a user-local package
tree at `~/.local/opt/quickshell` (extracted `quickshell` + `cpptrace` +
`libdwarf` Arch packages; the Qt6 stack comes from the system). To switch to
the real package:

```sh
sudo pacman -S quickshell
rm -rf ~/.local/opt/quickshell
hyprctl reload
```

## Files

- `shell.qml` — entry point; one `Bar` per monitor
- `Bar.qml` — the bar: workspaces island, window title, clock, tray, and
  the stats modules
- `ScriptModule.qml` — generic waybar-`custom`-style module: polls a script
  that prints one JSON line (`{"text": ..., "class": ...}`)
- `Theme.qml` — the waybar.css color palette
- `stats.sh` — long-lived cpu/mem/net sampler (one JSON line per second)
- `launch.sh` — launcher used by the hyprland `exec` line

The cpu-temp, GPU, VPN, and battery modules re-run the existing scripts from
`~/.config/waybar/` unchanged, so their hermetic tests still cover them.

## Differences from waybar (intentional)

- On narrow (portrait) monitors the title elides and the clock slides left;
  waybar let the sections overlap.
- Workspaces, window title, volume, and tray are event-driven (Hyprland IPC
  socket, Pipewire native) instead of polled.

## Not yet ported

- Tooltips (clock calendar, memory %, network ip/cidr, GPU details)
- `hyprconf setup` integration / package list entry for `quickshell`
