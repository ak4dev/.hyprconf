# Quickshell Configuration Reference

> Curated cheatsheet for this dotfiles repo's bar (`stow/quickshell`). Covers every
> Quickshell type in active use, verified against the installed build's qmltypes.
> Full docs: <https://quickshell.org/docs/v0.3.0/types/> — **always consult the docs
> version matching the installed package** (`pacman -Q quickshell`); swap the
> `v0.3.0` path segment to match (e.g. `/docs/v0.4.0/types/` after an upgrade).

---

## Table of Contents

1. [Runtime & CLI](#runtime--cli)
2. [Core Concepts](#core-concepts)
3. [Windows (PanelWindow / layer shell)](#windows-panelwindow--layer-shell)
4. [Quickshell.Io (Process, FileView, IPC)](#quickshellio-process-fileview-ipc)
5. [Quickshell.Hyprland](#quickshellhyprland)
6. [Quickshell.Services.SystemTray](#quickshellservicessystemtray)
7. [Quickshell.Services.Pipewire](#quickshellservicespipewire)
8. [Quickshell.Bluetooth](#quickshellbluetooth)
9. [Quickshell.Networking](#quickshellnetworking)
10. [Widgets & Misc](#widgets--misc)
11. [Repo Integration Map](#repo-integration-map)

---

## Runtime & CLI

- Entry point: `~/.config/quickshell/shell.qml`; sibling `.qml` files are components,
  registered (with singletons) in `qmldir`.
- Config files are **watched**: edits hot-reload the shell (`Quickshell.watchFiles`,
  default true). A broken edit keeps the previous state running.
- This repo launches via `~/.config/quickshell/launch.sh` (prefers `qs` from the
  `quickshell` package, falls back to a user-local tree — see `stow/quickshell/README.md`).

```bash
qs                              # run the shell at ~/.config/quickshell
qs ipc show                     # list IpcHandler targets/functions
qs ipc call popouts toggle calendar   # call an IpcHandler function
qs kill                         # stop the running instance
qs log                          # tail the running instance's log
```

Docs: <https://quickshell.org/docs/v0.3.0/configuration/>

---

## Core Concepts

```qml
import Quickshell

ShellRoot {                       // root of shell.qml
    Variants {                    // one instance per model entry
        model: Quickshell.screens // list<ShellScreen>, updates on hotplug
        delegate: Bar {}          // delegate gets `required property var modelData`
    }
}
```

### Singletons

```qml
pragma Singleton                  // first line of the file
import Quickshell
Singleton { id: root /* ... */ }  // register in qmldir: `singleton Theme Theme.qml`
```

### The `Quickshell` singleton

| Member | Notes |
|---|---|
| `screens` | `list<ShellScreen>` — all outputs; pair with `Variants` for per-screen windows |
| `env(name)` | Read an environment variable (or null) |
| `execDetached(["cmd", "arg"])` | Spawn an **untracked** argv process — no shell; survives qs exit. Use for launching apps |
| `shellDir` | Directory containing `shell.qml` (`configDir` is deprecated) |
| `reload(hard)` | Reload the config programmatically |

`execDetached` never invokes a shell — pass argv arrays only (this repo's security
posture depends on it; never build `["sh", "-c", ...]` from external strings).

### SystemClock

```qml
SystemClock { id: clock; precision: SystemClock.Seconds }  // Hours | Minutes | Seconds
// clock.date is a JS Date; format with Qt.formatDateTime(clock.date, "HH:mm")
```

Use the coarsest precision that works — `Seconds` wakes the process every second.

---

## Windows (PanelWindow / layer shell)

```qml
import Quickshell
import Quickshell.Wayland

PanelWindow {
    anchors { top: true; left: true; right: true }  // 1 or 3 anchors → exclusive zone works
    implicitHeight: 24
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore   // Auto (default) | Ignore | Normal
    mask: Region {}                       // EMPTY region = fully click-through
    screen: modelData                     // ShellScreen to display on
    WlrLayershell.namespace: "quickshell:bar"       // hyprland layerrule matches this
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand  // None (default) | OnDemand | Exclusive
    WlrLayershell.layer: WlrLayer.Top     // Background | Bottom | Top | Overlay
}
```

- `exclusionMode: Auto` reserves space (a bar); `Ignore` overlays without reserving
  (popouts, OSD, screen corners).
- `mask: Region {}` makes a window purely visual — input passes through (OSD, corners).
  Omit `mask` for normal input.
- `WlrLayershell.namespace` cannot change after the window connects; Hyprland
  `layerrule = blur, quickshell:popouts` keys off it (see `hyprland.conf`).
- `keyboardFocus: OnDemand` is required for text fields in layer-shell windows
  (Control Center password box). Never use `Exclusive` outside a lock screen.
- `margins { top: N; left: N }` offsets from the anchored edges.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell/PanelWindow/>

---

## Quickshell.Io (Process, FileView, IPC)

### Process

```qml
import Quickshell.Io

Process {
    id: proc
    command: ["hyprctl", "-j", "activewindow"]   // argv — NEVER a shell string
    running: true                                 // true starts, false SIGTERMs
    stdout: StdioCollector {                      // whole output at once
        onStreamFinished: doSomething(text)
    }
    // or line-by-line for long-lived streams:
    stdout: SplitParser { onRead: data => handleLine(data) }
    onExited: (code, status) => { /* re-arm with `running = true` to poll */ }
}
```

- Re-set `running = true` (e.g. from a `Timer`) to re-run; `command` changes apply
  to the **next** start.
- `environment: { VAR: "x" }`, `workingDirectory`, `signal(n)`, `write(s)` available.
- One long-lived streaming process (see `stats.sh`) beats re-forking per poll.

### FileView

```qml
FileView {
    id: f
    path: "/some/file"        // "" unloads
    watchChanges: true        // emit fileChanged on disk changes
    blockLoading: true        // first text() blocks until loaded
    onFileChanged: reload()   // re-read on change
}
// f.text() is a FUNCTION, not a reactive property — bindings using it re-evaluate
// via its accompanying change signal after reload() (pattern used by Theme.qml).
```

Also supports writes (`setText`, atomic by default) and a `JsonAdapter`.

### IpcHandler

```qml
IpcHandler {
    target: "popouts"                       // unique per instance
    function toggle(name: string): string { // args/returns MUST be typed:
        /* validate `name` against a fixed list — never execute it */
    }                                       // string|int|bool|real|color|void
}
```

Invoke: `qs ipc call popouts toggle calendar`. Anything with access to the user
session can call these — validate inputs, keep them side-effect-minimal.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/Process/>

---

## Quickshell.Hyprland

### `Hyprland` singleton

| Member | Notes |
|---|---|
| `workspaces` | ObjectModel<HyprlandWorkspace>, sorted by id (special/named ids are negative → filter `id > 0`) |
| `activeToplevel` | Focused window (`.title`); **only populates from focus events** — seed initial state via `hyprctl -j activewindow` (see `Bar.qml`) |
| `focusedMonitor` | HyprlandMonitor; map a screen with `monitorFor(screen)` |
| `dispatch("workspace m+1")` | Any dispatcher string |
| `rawEvent(HyprlandEvent)` | Every socket2 event; `event.name` (e.g. `activewindow`, `screencast`), `event.data` (comma-separated) |
| `refreshWorkspaces()` / `refreshMonitors()` / `refreshToplevels()` | Manual re-sync |

`HyprlandWorkspace`: `id`, `focused`, `activate()`.

### HyprlandFocusGrab — popout dismissal

```qml
HyprlandFocusGrab {
    active: win.visible
    windows: [win, win.bar]   // whitelist; click outside → cleared
    onCleared: win.close()
}
```

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Hyprland/Hyprland/>

---

## Quickshell.Services.SystemTray

```qml
import Quickshell.Services.SystemTray

Repeater {
    model: SystemTray.items.values   // array of SystemTrayItem
    // item: id, title, icon (Image source), status, tooltipTitle,
    //       hasMenu, onlyMenu (activate() does nothing), menu (QsMenuHandle)
    // actions: activate(), secondaryActivate(), scroll(delta, horizontal)
}
```

Menu rendering — the portable path is `QsMenuOpener` on `item.menu`:

```qml
QsMenuOpener { id: opener; menu: item.menu }
// opener.children → entries: text, icon, enabled, isSeparator, hasChildren,
// buttonType (QsMenuButtonType.CheckBox/RadioButton/None), checkState, triggered()
```

**Repo caveats (verified on 0.3.0):** the native `SystemTrayItem.display()` /
`QsMenuAnchor` render nothing inside this layer-shell bar, so `TrayMenuPopout.qml`
draws menus manually via `QsMenuOpener`; nested dbusmenu submenus (nm-applet's
network list) arrive empty in the layer-shell popup. Menu labels are external
input — render `Text.PlainText` only.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Services.SystemTray/SystemTrayItem/>

---

## Quickshell.Services.Pipewire

```qml
import Quickshell.Services.Pipewire

// REQUIRED: nodes must be bound by a PwObjectTracker before their properties
// (volume, description, ...) are populated/usable.
PwObjectTracker { objects: [Pipewire.defaultAudioSink] }

readonly property var sink: Pipewire.defaultAudioSink   // may be null in transitions
// sink.audio.volume (0..1, writable) · sink.audio.muted (writable)
// sink.description · sink.name · sink.isSink · sink.isStream
```

| `Pipewire` member | Notes |
|---|---|
| `defaultAudioSink` / `defaultAudioSource` | Current defaults; can briefly be null while switching |
| `preferredDefaultAudioSink = node` | Set the default output (device pickers) |
| `nodes.values.filter(n => n.isSink && !n.isStream && n.audio)` | Enumerate outputs |
| `ready` | Initial server sync complete |

Guard every access with `?.` — `sink?.audio?.volume ?? 0`.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Services.Pipewire/Pipewire/>

---

## Quickshell.Bluetooth

New in 0.3.0 (BlueZ over D-Bus).

```qml
import Quickshell.Bluetooth

Bluetooth.defaultAdapter          // BluetoothAdapter | null
Bluetooth.devices                 // ObjectModel<BluetoothDevice>
adapter.enabled = true            // writable power toggle
adapter.discovering               // scan state (writable)
```

`BluetoothDevice`: `name`, `connected` (**writable** — assignment
connects/disconnects, as used in `ControlCenter.qml`), `paired`, `bonded`,
`trusted`, `battery` (0..1), `batteryAvailable`, `connect()`, `disconnect()`.
Pairing new devices is not handled in-shell — this repo delegates to
`blueman-manager`.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Bluetooth/>

---

## Quickshell.Networking

New in 0.3.0. NetworkManager over D-Bus is the only backend (requires both
running; this repo satisfies that). Verified against the installed qmltypes.

```qml
import Quickshell.Networking

Networking.wifiEnabled = !Networking.wifiEnabled  // writable radio toggle (rfkill)
Networking.devices                                 // ObjectModel<NetworkDevice>
```

| Type | Members in use |
|---|---|
| `NetworkDevice` | `type` (`DeviceType.Wifi/Wired/None`), `name`, `networks` (ObjectModel<Network>), `connected`, `state`, `autoconnect`, `disconnect()` |
| `WifiDevice` (: NetworkDevice) | `scannerEnabled` (**writable** — set true while a picker is open, false after), `mode` |
| `WiredDevice` (: NetworkDevice) | `hasLink`, `linkSpeed`, `network` |
| `Network` | `name` (SSID), `connected`, `known` (saved profile exists), `state` (`ConnectionState.*`), `stateChanging`, `connect()`, `disconnect()`, `forget()`, signal `connectionFailed(reason)` |
| `WifiNetwork` (: Network) | `signalStrength` (0..1), `security` (`WifiSecurityType.*`), `connectWithPsk(psk)` |

- Connect flow: `known` or open networks → `network.connect()`; secured unknown
  networks → `connectWithPsk(psk)`. A wrong PSK emits
  `connectionFailed(ConnectionFailReason.NoSecrets)`.
- `connectWithPsk` passes the secret over D-Bus to NetworkManager — **never via
  argv/process list**; prefer it over shelling out to `nmcli`.
- Open/passwordless security types: `WifiSecurityType.Open` and `.Owe`.
- `ConnectionState`: `Unknown, Connecting, Connected, Disconnecting, Disconnected`.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Networking/>

---

## Widgets & Misc

```qml
import Quickshell.Widgets
IconImage { source: trayItem.icon; implicitSize: 16 }   // icon-theme aware Image
```

- `QtQuick.Effects.RectangularShadow` (Qt, not Quickshell) draws the popout drop
  shadow without offscreen layers.
- Other 0.3.0 service modules exist but are unused here: `Mpris`, `Notifications`
  (dunst owns notifications), `UPower` (battery comes from the existing script),
  `Greetd`, `Pam`, `Polkit`, `DBusMenu` (wrapped by SystemTray).

---

## Repo Integration Map

| File | Quickshell APIs |
|---|---|
| `shell.qml` | ShellRoot, Variants, IpcHandler |
| `Bar.qml` | PanelWindow, SystemClock, Process, SplitParser, StdioCollector, Hyprland, SystemTray, Pipewire, IconImage |
| `Theme.qml` | Singleton, FileView (watch + reload pattern) |
| `PopoutWindow.qml` | PanelWindow, WlrLayershell.keyboardFocus, HyprlandFocusGrab, RectangularShadow |
| `ControlCenter.qml` | Pipewire, Bluetooth, Networking (Wi-Fi list/connect), TextInput (PSK) |
| `VolumePopout.qml` / `Osd.qml` | Pipewire, PwObjectTracker; OSD is `mask: Region {}` click-through |
| `TrayMenuPopout.qml` | QsMenuOpener, QsMenuButtonType, IconImage |
| `ScreenCorners.qml` | PanelWindow + empty Region mask, Canvas |
| `stats.sh` / `ScriptModule.qml` | One long-lived `Process` + SplitParser stream; waybar-style JSON modules |

Theming flow: `~/.config/hypr/.current-theme` → `theme-switcher/themes/<name>.json`
→ `Theme.qml` FileViews (watched) → live repaint. Hyprland blurs the popout/OSD
surfaces via `layerrule` entries in `hyprland.conf` matching the
`quickshell:*` namespaces.

**When adding features not covered here, add a concise example of the new API to
the appropriate section in this file** (same rule as `hyprland-reference.md`).
