# Omarchy Bar-Widget Plugin Reference

> What an Omarchy bar-widget plugin in this repo needs: the three the overlay ships —
> `plugins/hyprconf-resources/` (`hyprconf.resources`), `plugins/hyprconf-workspaces/`
> (`hyprconf.workspaces`, `clonedFrom` `omarchy.workspaces`) and `plugins/hyprconf-active-window/`
> (`hyprconf.active-window`, `clonedFrom` `omarchy.active-window`) — and the one copy of a
> stock plugin `install.sh` makes, `hyprconf.clock`.
> Verified against Omarchy 4.0.0 (`/usr/share/omarchy/shell/`) and the installed
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

Every plugin ships `manifest.json` (contract in `shell/README.md`). The resources one:

```json
{
  "schemaVersion": 1,
  "id": "hyprconf.resources",
  "name": "Resource Usage",
  "version": "1.0.0",
  "author": "hyprconf",
  "description": "CPU/temp/memory/GPU/network readout, ported from hyprconf's quickshell bar",
  "kinds": ["bar-widget"],
  "entryPoints": { "barWidget": "Widget.qml" },
  "barWidget": {
    "displayName": "Resource Usage",
    "description": "CPU/temp/memory/GPU/network readout",
    "category": "System",
    "allowMultiple": false
  }
}
```

Optional `barWidget` keys: `defaultSection`, `defaults` (per-widget settings the
widget reads via `setting()`), `schema` (what `omarchy bar set` accepts). Validate
with `omarchy plugin validate <plugin-folder>`.

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
`~/.config/omarchy/plugins/` on every run, so the shell swaps them into the
stock slots the same way. The bar's `centerAnchor` in `shell.json` is a plain
id with no clone resolution — after swapping `omarchy.clock` for
`hyprconf.clock` the anchor must follow. A bar carrying both the stock widget
and the copy (an upgrade from the `<username>.*` era) is healed by disabling
and re-enabling the copy — the registry swaps a `clonedFrom` copy into the
stock entry only at enable time — and `omarchy bar move`-ing it into the
recorded stock slot when it lands elsewhere.

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
  convention Omarchy's first-party plugins follow). A stream that produced
  output and then died is restarted; one that exits without output means "no
  such hardware" and stays hidden.
- `SystemClock { precision: SystemClock.Seconds }` (`quickshell-core.qmltypes`:
  `Hours | Minutes | Seconds`) is the one-line patch `install.sh` applies to the
  `hyprconf.clock` copy — the stock clock samples at `Minutes`.

Docs: <https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/Process/>

## CLI

```bash
omarchy plugin list [--json]                 # ids + enabled state
omarchy plugin enable <id> [placement]       # e.g. --section right
omarchy plugin disable <id>
omarchy plugin clone <source-id> [--edit]    # ~/.config/omarchy/plugins/<username>.<id>
omarchy plugin validate <plugin-folder>
omarchy plugin add|remove|update …

omarchy bar set <id> <key> <value> [--json] [placement]   # per-widget option (omarchy bar set hyprconf.clock format 'hh:mm:ss AP')
omarchy bar put|move <id> [placement]        # placement: --section left|center|right, --after <id>, --index N
omarchy bar position|transparent|use|reset|defaults

omarchy-shell shell rescanPlugins            # discovery is async — wait for the id in `plugin list` before enabling
omarchy-shell shell reloadConfig             # re-read shell.json (idle timeouts, bar layout)
omarchy restart shell                        # install.sh does this once per run, only when a widget copy was (re)synced or re-seated
omarchy-plugin-catalog                       # JSON: id, firstParty, sourceDir, manifestPath — resolve sources here, never a hard-coded path
```

**When adding a plugin API not covered here, add a concise example to this file**
after verifying it against the installed qmltypes and shell sources.
