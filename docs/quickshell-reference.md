# Omarchy Bar-Widget Plugin Reference

> What an Omarchy bar-widget plugin in this repo needs: the three the overlay ships —
> `plugins/hyprconf-resources/` (`hyprconf.resources`), `plugins/hyprconf-workspaces/`
> (`hyprconf.workspaces`, `clonedFrom` `omarchy.workspaces`) and `plugins/hyprconf-active-window/`
> (`hyprconf.active-window`, `clonedFrom` `omarchy.active-window`) — and the one copy of a
> stock plugin `install.sh` makes, `hyprconf.clock`.
> Verified against Omarchy 4.0.0-1 (`/usr/share/omarchy/shell/`) and the installed
> Quickshell qmltypes (`/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`, quickshell-git
> 0.3.0). **Re-verify against both after every Omarchy or Quickshell upgrade** —
> the shell contract and Quickshell's API both change between minor versions.
> Quickshell docs: <https://quickshell.org/docs/v0.3.0/types/> (match the path
> segment to `pacman -Q quickshell-git`).

---

## The shell

`omarchy-shell` is one long-running Quickshell instance; the bar, panels and
overlays are plugins inside it (`/usr/share/omarchy/shell/README.md`). Layout:

```
/usr/share/omarchy/shell/
  shell.qml                       ShellRoot; IPC target "shell" (rescanPlugins, reloadConfig, summon …)
  Commons/   Color.qml Style.qml  `import qs.Commons` — theme colours and typography/spacing tokens
  Ui/        BarWidget.qml …      `import qs.Ui` — the base every bar widget extends
  services/  PluginRegistry.qml   discovery, validation, enabled state, clonedFrom resolution
  plugins/   bar/ panels/ …       first-party plugins (plugins/README.md lists ids and entry points)
```

User plugins live in `~/.config/omarchy/plugins/<plugin-id>/`; the bar layout and
per-widget settings live in the `bar:` subtree of `~/.config/omarchy/shell.json`.

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
`omarchy bar set` accepts). Validate with `omarchy plugin validate <plugin-folder>`.

### Copies of built-in widgets (`clonedFrom`)

`omarchy plugin clone <source-id>` copies a first-party plugin into
`~/.config/omarchy/plugins/<username>.<id>/` and rewrites the manifest:
`id`, `name`, `barWidget.displayName`, and `omarchy.clonedFrom = <source-id>`
(dropping `omarchy.clonePaths`). `clonedFrom` is what makes the shell route the
built-in's IPC to the copy and swap the stock widget out when the copy is
enabled (`services/PluginRegistry.qml`). Two source layouts exist:

- plugin directory (`panels/clock/manifest.json`) — the whole dir is copied;
- sibling manifest (`bar/widgets/Workspaces.manifest.json` next to
  `Workspaces.qml`) — the manifest plus each `entryPoints` file.

`install.sh`'s `copy_builtin_plugin` does this under the `hyprconf.*`
namespace (a username in shipped config is PII) for the **plugin-directory
layout only**, resolving the source from `omarchy-plugin-catalog` (`sourceDir`,
`manifestPath`) at runtime and refusing a sibling manifest — the clock is the
one stock plugin it copies (and patches to tick seconds). The two sibling-manifest
widgets the overlay replaces are not copied at all: `plugins/hyprconf-workspaces/`
and `plugins/hyprconf-active-window/` are the overlay's own QML, shipped with
`omarchy.clonedFrom` already in their manifests and synced into
`~/.config/omarchy/plugins/` on every run. Two contract facts drive the install
order: the registry swaps a `clonedFrom` copy into the stock entry **at enable
time** (`PluginRegistry.qml`, `setEnabled`), and the bar's `centerAnchor` in
`shell.json` is a plain id with no clone resolution — after swapping
`omarchy.clock` for `hyprconf.clock` the anchor must follow
(`follow_center_anchor`).

## `BarWidget` (`qs.Ui`)

`/usr/share/omarchy/shell/Ui/BarWidget.qml` — the `Item` every bar widget extends:

| Member | Notes |
|---|---|
| `bar` | The host Bar instance. `bar.run(command)` launches a command the shell's way (`root.bar.run("omarchy-launch-or-focus-tui btop")`); `bar.moduleWidgets(id)` lists live instances |
| `moduleName` | The widget's canonical id — set it to the manifest id |
| `settings` | This widget's inline `shell.json` entry; read with `setting(name, fallback)` |
| `vertical` | `true` when the bar is a side rail — switch layouts on it |
| `barSize` | Bar thickness in px |
| `broadcast(method)` | Call `method` on every live instance (one bar surface per monitor) |

Sizing rule: bind `implicitWidth`/`implicitHeight` to the widget's own content.
The bar's ModuleSlot takes its height from the widget's implicit size, so
`parent.height` closes a binding loop, QML drops it, and the widget renders
zero-height with no error logged.

## Theme tokens (`qs.Commons`)

- `Color.foreground`, `Color.accent`, `Color.urgent`, `Color.muted`,
  `Color.background` — semantic roles from the active theme's `colors.toml`.
  Only these exist; per-metric hues are not a thing an Omarchy theme defines,
  so readings all use `Color.foreground` (`muted` is dimmed secondary chrome).
- `Style.font.caption`, `Style.fontFamily`, `Style.spacing.sm` — typography and
  spacing tokens, scaled by the theme's `shell.toml`.

## Quickshell.Io — streaming a helper process

Verified in `Io/quickshell-io.qmltypes`:

```qml
import Quickshell.Io

Process {
    id: statsProc
    running: true                          // bool — true starts, false stops
    command: ["hyprconf-stats"]            // argv list — never a shell string
    stdout: SplitParser {                  // DataStreamParser; splitMarker defaults to "\n"
        onRead: data => { /* one line */ }
    }
    onExited: function(exitCode, exitStatus) { /* re-arm with running = true to restart */ }
}
Timer { id: restartTimer; interval: 1000; onTriggered: gpuProc.running = true }
```

- Other `Process` members: `stderr`, `workingDirectory`, `environment`,
  `clearEnvironment`, `stdinEnabled`, `write(data)`, `signal(n)`, `exec(argv)`,
  `startDetached()`; signals `started`, `exited(exitCode, exitStatus)`.
  `StdioCollector` collects whole output instead of lines.
- Pattern used by `Widget.qml`: one long-lived JSON stream per feeder
  (`bin/hyprconf-stats`, `bin/hyprconf-gpu-info`, installed on `PATH` — the same
  convention Omarchy's first-party plugins follow), one pair per bar surface
  (the bar is built per monitor). A stream that produced output and then died
  is restarted; one that exits without output means "no such hardware": its
  cells stay blank but sized, and it is not restarted.
- `SystemClock { precision: SystemClock.Seconds }` (`quickshell-core.qmltypes`:
  `Hours | Minutes | Seconds`) is the one-line patch `install.sh` applies to the
  `hyprconf.clock` copy — the stock clock samples at `Minutes`.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/Process/>

## CLI

`omarchy plugin --help` and `omarchy bar --help` are the CLI — read them live,
never a copy. `omarchy-plugin-catalog` prints the JSON (`id`, `firstParty`,
`sourceDir`, `manifestPath`) sources are resolved from — never a hard-coded
path. Discovery after `omarchy-shell shell rescanPlugins` is asynchronous: wait
for the id in `omarchy plugin list --json` before enabling (`activate_plugin_copy`);
`omarchy-shell shell reloadConfig` re-reads `shell.json`; `install.sh` runs
`omarchy-shell shell rescanPlugins` after each widget sync (`reload_plugins` —
the hot reload `omarchy-plugin-update` uses), falling back to
`omarchy-restart-shell` only when no shell answers.

**When adding a plugin API not covered here, add a concise example to this file**
after verifying it against the installed qmltypes and shell sources.
