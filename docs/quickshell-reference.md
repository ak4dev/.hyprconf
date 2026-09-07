# Omarchy Bar-Widget Plugin Reference

> What an Omarchy bar-widget plugin in this repo needs: the four the overlay ships —
> `plugins/hyprconf-clock/` (`hyprconf.clock`, `clonedFrom` `omarchy.clock`),
> `plugins/hyprconf-resources/` (`hyprconf.resources`), `plugins/hyprconf-workspaces/`
> (`hyprconf.workspaces`, `clonedFrom` `omarchy.workspaces`) and `plugins/hyprconf-active-window/`
> (`hyprconf.active-window`, `clonedFrom` `omarchy.active-window`) — each a folder that is
> a plugin on its own (`docs/CONTRIBUTING.md` › Publishing a plugin).
> Verified against Omarchy 4.0.2-1 (`/usr/share/omarchy/shell/`) and the installed
> Quickshell qmltypes (`/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`, quickshell
> 0.3.1 — Arch's package, renamed off `-git`). **Re-verify against both after every Omarchy or Quickshell upgrade** —
> the shell contract and Quickshell's API both change between minor versions.
> Quickshell docs: <https://quickshell.org/docs/v0.3.1/types/> (match the path
> segment to `pacman -Q quickshell`).

---

## The shell

`omarchy-shell` is one long-running Quickshell instance; the bar, panels and
overlays are plugins inside it (`/usr/share/omarchy/shell/README.md`). Layout:

```
/usr/share/omarchy/shell/
  shell.qml                       ShellRoot; IPC target "shell" (rescanPlugins, reloadConfig, summon …)
  Commons/   Color.qml Style.qml Util.qml   `import qs.Commons` — theme colours, typography/spacing tokens, helpers
  Ui/        BarWidget.qml …      `import qs.Ui` — the base every bar widget extends
  services/  PluginRegistry.qml   discovery, validation, enabled state, clonedFrom resolution
  plugins/   bar/ panels/ …       first-party plugins (plugins/README.md lists ids and entry points)
```

User plugins live in `~/.config/omarchy/plugins/<plugin-id>/`; the bar layout and
per-widget settings live in the `bar:` subtree of `~/.config/omarchy/shell.json`.
A third-party plugin is a **git repository with `manifest.json` at its root**:
`omarchy plugin add <url>` clones it, runs `omarchy-plugin-validate` over the
clone and moves it to `~/.config/omarchy/plugins/<id>/` (`bin/omarchy-plugin-add`);
`omarchy plugin update` fast-forwards a git checkout and refuses anything else;
`omarchy plugin remove` deletes a checkout and backs a plain folder up to
`.<id>.bak.<timestamp>` beside it. The registry scans only the top level of the
plugins dir and ignores dot-prefixed names (`PluginRegistry.qml`, `rescan` and
`localPluginIdForPath`).

## Manifest

Every plugin ships `manifest.json` (contract in `shell/README.md`). The keys the
resources one (`plugins/hyprconf-resources/manifest.json`) relies on:

```json
{
  "schemaVersion": 1,
  "id": "hyprconf.resources",
  "kinds": ["bar-widget"],
  "entryPoints": { "barWidget": "Widget.qml" },
  "barWidget": {
    "displayName": "Resource Usage",
    "category": "System",
    "defaultSection": "right",
    "allowMultiple": false
  }
}
```

`defaultSection` is what places `hyprconf.resources` on an enable with no
placement flag (`stage_bar_plugin` passes none). Other optional `barWidget` keys:
`defaults` (per-widget settings the widget reads via `setting()`), `schema` (what
`omarchy bar set` accepts). Validate with `omarchy plugin validate <plugin-folder>`
(`bin/omarchy-plugin-validate`: `schemaVersion` the number 1, the five required
fields, the id's regex and the reserved `omarchy.*` namespace, relative
`..`-free entry points that exist, one per kind, `defaultSection`'s domain, no
symlink anywhere in the folder — `tests/unit/test_plugins.py` re-implements the
list so CI pins it without Omarchy).

### Copies of built-in widgets (`clonedFrom`)

`omarchy plugin clone <source-id>` copies a first-party plugin into
`~/.config/omarchy/plugins/<username>.<id>/` and rewrites the manifest:
`id`, `name`, `barWidget.displayName`, and `omarchy.clonedFrom = <source-id>`
(dropping `omarchy.clonePaths`). `clonedFrom` is what makes the shell route the
built-in's IPC to the copy and swap the stock widget out when the copy is
enabled (`services/PluginRegistry.qml`, `setEnabled` / `resolveEnabledId`) —
for a third-party copy as much as a clone (no first-party gate). Two source
layouts exist:

- plugin directory (`panels/clock/manifest.json`) — the whole dir is copied;
- sibling manifest (`bar/widgets/Workspaces.manifest.json` next to
  `Workspaces.qml`) — the manifest plus each `entryPoints` file.

The overlay makes no clone at install time — a username in shipped config is
PII, and a copy made once on the box was frozen at whatever release made it.
Its three `clonedFrom` widgets ship as their own folders with the rewritten
manifest already in them: `plugins/hyprconf-workspaces/` and
`plugins/hyprconf-active-window/` are the overlay's own QML derived from the
two sibling-manifest widgets, and `plugins/hyprconf-clock/` is the
plugin-directory clock itself — the stock `BarWidget.qml` and `Model.js` with
exactly three deltas (`precision: SystemClock.Seconds`; the calendar panel
loaded from the RUNNING Omarchy's own `Panel.qml` through
`"file://" + Quickshell.env("OMARCHY_PATH") + "/shell/plugins/panels/clock/Panel.qml"`,
which imports its own `Model.js` relative to itself; and `injectPanel()`
forwarding the widget's `moduleName` to that panel), so one `Model.js` beside
`BarWidget.qml` (its static `import "Model.js"`) is the whole fork, and a
`NOTICE` carries Omarchy's MIT notice. All four are synced into
`~/.config/omarchy/plugins/` on every run.

A clone keeps the built-in ids that are written into the QML: `omarchy plugin
clone` rewrites only `manifest.json` and the `entryPoints` filenames, on
purpose — "keep built-in ids inside the plugin code as stable IPC targets",
its `update_manifest` comment — and `clonedFrom` routes the IPC half. What
`clonedFrom` does **not** route is a *settings write*: a nested panel whose
own `moduleName` is still the built-in id hands that id to `shell.qml`'s
`updateEntryInline(moduleName, entry)`, which writes only an entry already
carrying it in `bar.layout` or `config.plugins` — and the live slot carries
the clone's id. So a copy with a settings-writing panel has to forward its
own `moduleName` down (the clock plugin's third delta): the bar sets the
*widget's* `moduleName` from the slot id in `ModuleSlot.injectProps`, the
widget passes it on.

Two more contract facts drive the install
order: the registry swaps a `clonedFrom` copy into the stock entry **at enable
time** (`setEnabled`), and the bar's `centerAnchor` in `shell.json` is a plain
id with no clone resolution (`Util.canonicalWidgetId` is a string cast) — after
swapping `omarchy.clock` for `hyprconf.clock` the anchor must follow
(`follow_center_anchor`).

## `BarWidget` (`qs.Ui`)

`/usr/share/omarchy/shell/Ui/BarWidget.qml` — the `Item` every bar widget extends:

| Member | Notes |
|---|---|
| `bar` | The host Bar instance (`plugins/bar/Bar.qml`). `bar.run(command)` launches a command the shell's way (`root.bar.run("omarchy-launch-or-focus-tui btop")`); `bar.moduleWidgets(id)` lists live instances |
| `bar.showTooltip(target, text)` / `bar.hideTooltip(target)` | The bar's own tooltip, anchored on `target` (the widget root) — call from a `MouseArea`'s `onEntered` / `onExited` with `hoverEnabled: true` |
| `bar.barForeground` (color) / `bar.fontFamily` (string) | The bar's current text colour (theme, transparency-aware) and font family — bind `color` and `font.family` to these, with `Color.foreground` / `Style.fontFamily` as the `bar`-less fallback, as every stock text widget does |
| `moduleName` | The widget's canonical id — set it to the manifest id; a `clonedFrom` copy keeps the **stock** id (the IPC target the shell routes to the copy) |
| `settings` | This widget's inline `shell.json` entry; read with `setting(name, fallback)` |
| `vertical` | `true` when the bar is a side rail — switch layouts on it |
| `barSize` | Bar thickness in px |
| `broadcast(method)` | Call `method` on every live instance (one bar surface per monitor) |

Sizing rule: bind `implicitWidth`/`implicitHeight` to the widget's own content.
The bar's ModuleSlot takes its height from the widget's implicit size, so
`parent.height` closes a binding loop, QML drops it, and the widget renders
zero-height with no error logged.

## Text rendering (Omarchy 4.0.2's rule)

Every `Text` whose `text` is anything but string literals declares
`textFormat: Text.PlainText` — a window title, a device name or a feeder
string is data, and Qt's default `AutoText` would parse it as HTML. Omarchy
enforces it over its own tree (`test/shell.d/qml-text-format-scan.py`; the
stock `ActiveWindow.qml` and `WidgetButton.qml` carry the line) and
`tests/unit/test_plugins.py` scans `plugins/**/*.qml` the same way: a block's
own `text:` binding, an inline `component X: Text {` root (its text comes from
every caller), a one-line `Text { text: x }`.

## Theme tokens and helpers (`qs.Commons`)

- `Color.foreground`, `Color.accent`, `Color.urgent`, `Color.muted`,
  `Color.background` — semantic roles from the active theme's `colors.toml`.
  Only these exist; per-metric hues are not a thing an Omarchy theme defines,
  so readings all use `Color.foreground` (`muted` is dimmed secondary chrome).
- `Style.font.caption` / `.body` / `.title` … (px), `Style.font.family` (the
  `monospace` alias `omarchy font set` rewrites; `Style.fontFamily` is the
  same string), `Style.spacing.sm` / `.controlPaddingX` … (px tokens), and
  `Style.space(px)` / `Style.spaceReal(px)` — a pixel value scaled by the
  theme's `[spacing] scale` (rounded / fractional) — typography and spacing
  from the theme's `shell.toml` (`Commons/Style.qml`).
- `Util.shellQuote(value)` single-quotes a string for bash — for anything
  built into a `bar.run` command line
  (`root.bar.run("hyprctl dispatch " + Util.shellQuote(...))`).

## Quickshell.Hyprland and Quickshell.Wayland

Verified in `Hyprland/_Ipc/quickshell-hyprland-ipc.qmltypes` and
`Wayland/_ToplevelManagement/quickshell-wayland-toplevel-management.qmltypes`:

```qml
import Quickshell.Hyprland   // Hyprland singleton
Hyprland.workspaces.values   // ObjectModel of HyprlandWorkspace — .id (int; < 0 is a special workspace), .name
Hyprland.focusedWorkspace    // HyprlandWorkspace or null

import Quickshell.Wayland    // ToplevelManager singleton (wlr foreign toplevel)
ToplevelManager.activeToplevel   // Toplevel or null — .title, .appId, .activate(), .close()
```

Both are the seams the two `clonedFrom` widgets read the same way stock does
(`bar/widgets/Workspaces.qml`, `bar/widgets/ActiveWindow.qml`).

## Quickshell.Io — streaming a bundled helper process

Verified in `Io/quickshell-io.qmltypes`:

```qml
import Quickshell.Io

// This plugin's own directory, with its trailing slash: the shell loads an
// entry point as a percent-encoded file:// URL (PluginRegistry.qml
// entryPointUrl → Util.fileUrl), so Qt.resolvedUrl(".") is that URL's
// directory and decodeURIComponent gives the filesystem path back — a space
// or a "%" in the path survives (verified with the qml tool).
readonly property string pluginDir: decodeURIComponent(String(Qt.resolvedUrl(".")).replace(/^file:\/\//, ""))

Process {
    id: statsProc
    running: true                                  // bool — true starts, false stops
    command: [root.pluginDir + "bin/hyprconf-stats"]   // argv list, absolute path — never a shell string, never a bare name
    stdout: SplitParser {                          // DataStreamParser; splitMarker defaults to "\n"
        onRead: data => { /* one line */ }
    }
    onExited: function(exitCode, exitStatus) { if (root.statsProduced) statsRestartTimer.died() }
}

// The restart ladder: 1 s, 2 s, 4 s, 8 s, 16 s, 32 s, then parked. `attempt`
// is refilled by the parser (`produced()`) on every line that arrives, so a
// stream that is delivering data restarts after a second and one that is only
// dying stops costing anything.
component Restarter: Timer {
    id: restarter
    property var proc: null
    property int attempt: 0
    readonly property int maxAttempts: 6
    interval: 1000
    onTriggered: if (restarter.proc) restarter.proc.running = true
    function produced() { restarter.attempt = 0 }
    function died() {
        if (restarter.attempt >= restarter.maxAttempts) return
        restarter.interval = 1000 * (1 << restarter.attempt)
        restarter.attempt++
        restarter.start()
    }
}
Restarter { id: statsRestartTimer; proc: statsProc }
```

- A plugin's scripts ship inside its folder and are run by absolute path from
  it — the way Omarchy's clipboard plugin runs its bundled `capture.sh`
  (`plugins/clipboard/Clipboard.qml`: `captureScript: root.omarchyPath +
  "/shell/plugins/clipboard/capture.sh"`, `command: [root.captureScript]`).
  Never a bare name on `PATH`: the shell's PATH is the session's, which has
  `$OMARCHY_PATH/bin` and not `~/.local/bin` (a login bash appends that one,
  `default/bash/envs`), and a plugin installed by `omarchy plugin add` has
  nothing of the overlay's. The exec bit travels: git stores it, `cp -aL`
  keeps it.
- Other `Process` members: `stderr`, `workingDirectory`, `environment`,
  `clearEnvironment`, `stdinEnabled`, `write(data)`, `signal(n)`, `exec(argv)`,
  `startDetached()`; signals `started`, `exited(exitCode, exitStatus)`.
  `StdioCollector` collects whole output instead of lines.
- Pattern used by `plugins/hyprconf-resources/Widget.qml`: one long-lived JSON
  stream per feeder (`bin/hyprconf-stats`, `bin/hyprconf-gpu-info` inside the
  plugin folder), one pair per bar surface (the bar is built per monitor). A
  stream that exits without output means "no such hardware": its cells stay
  blank but sized, and it is not restarted. One that produced output and then
  died IS restarted (Clipboard.qml restarts its watchers the same way) — but
  **on a backoff with a cap**, never a flat retry. The "it produced output"
  flag stays latched (it also decides what the cells paint), so nothing else
  ever stops the loop, and the dead-hardware case is a feeder that exits
  *instantly*: `nvidia-smi --loop` returns at once when the driver stops
  answering, so a 1 s retry is ~78,000 execs a day per bar surface, each
  paying a failing NVML init. Upstream's `Clipboard.qml` has neither a
  backoff nor a produced-output gate, so this is the stricter shape, not a
  relaxation of it.
- `SystemClock { precision: SystemClock.Seconds }` (`quickshell-core.qmltypes`:
  `Hours | Minutes | Seconds`) is one of the clock plugin's three deltas — the
  stock clock samples at `Minutes`. `Quickshell.env("NAME")` (core) reads the
  shell's environment: `OMARCHY_PATH` is how Omarchy's plugins locate their
  tree, and how the clock plugin loads the stock `Panel.qml`.

Docs: <https://quickshell.org/docs/v0.3.1/types/Quickshell.Io/Process/>

## CLI

`omarchy plugin --help` and `omarchy bar --help` are the CLI — read them live,
never a copy. Discovery after `omarchy-shell shell rescanPlugins` is
asynchronous: wait for the id in `omarchy plugin list --json` before enabling
(`activate_plugin_copy`); `omarchy-shell shell reloadConfig` re-reads
`shell.json`; `install.sh` runs `omarchy-shell shell rescanPlugins` after each
widget sync (`reload_plugins` — the hot reload `omarchy-plugin-update` uses),
falling back to `omarchy-restart-shell` only when no shell answers. No command
sets `bar.centerAnchor`; the bar's README documents the key, and
`follow_center_anchor` edits it with `jq` after the clock swap.

**When adding a plugin API not covered here, add a concise example to this file**
after verifying it against the installed qmltypes and shell sources.
