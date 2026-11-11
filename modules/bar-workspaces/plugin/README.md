# hyprconf.workspaces

An [Omarchy](https://omarchy.org) bar widget replacing the stock
`omarchy.workspaces`: only the workspaces that exist (no fixed 1–5 pills),
stacked on two lines so the widget takes half the width, with a Pac-Man (`󰮯`,
nf-md-pac_man) on the one its monitor shows. Each bar lists its own monitor's
workspaces, numbered 1–10 as Omarchy numbers them, then any visiting from an
unplugged monitor; click focuses. A `clonedFrom` replacement for the stock
widget, keeping its per-monitor logic (NOTICE carries Omarchy's MIT notice):
enabling it swaps it into the stock widget's slot on the bar. It draws no
layout glyph, so the layout is not cycled from here.

## Install

Drop the folder in where Omarchy reads user plugins
(`/usr/share/omarchy/shell/plugins/README.md:11-12`) and enable it by id:

```bash
git clone https://github.com/ak4dev/.hyprconf
cp -r .hyprconf/modules/bar-workspaces/plugin ~/.config/omarchy/plugins/hyprconf.workspaces
omarchy-shell shell rescanPlugins
omarchy plugin enable hyprconf.workspaces
```

Once this folder is published as a repository of its own, `omarchy plugin add
<url> --enable --yes` is the one-step form. `--yes` is not optional for this
widget: without it `omarchy-plugin-add` asks which bar section to put it in
(`select_bar_widget_placement`, `/usr/bin/omarchy-plugin-add:163`, Omarchy
4.5.0-3) and the answer becomes a placement, which moves the widget out of the
stock slot its `clonedFrom` manifest just claimed. `--yes` also skips Omarchy's
review-the-code prompt, so read the repository first.

`omarchy plugin disable hyprconf.workspaces` hands the slot back to the stock
widget; `omarchy plugin remove hyprconf.workspaces` takes the folder out.

Part of the [hyprconf](https://github.com/ak4dev/.hyprconf) overlay, whose
`modules/bar-workspaces/install` links and enables this folder — details in
that module's README.

## Settings

None: the stock widget reads no `omarchy bar set` key, and neither does
this one. The bar's own font and foreground apply.

## Host contract (Omarchy 4.5.0-3)

An installed third-party widget never gets the host Bar: its `bar` is a
`Ui/PluginBarApi.qml` facade and `bar.shell` a `services/PluginShellApi.qml`,
both scoped to this plugin's own id (`shell/plugins/bar/Bar.qml:2836-2837`,
`Bar.qml:349-363` → `shell/shell.qml:709-711`). Those two files are the whole
contract — a member that exists only on the Bar reads back `undefined`, with
nothing logged anywhere. This widget uses `bar.barForeground`,
`bar.fontFamily` and `bar.run(command)`, plus the `bar`, `moduleName` and
`settings` the bar's `ModuleSlot.injectProps` sets on it. Which workspaces are
its monitor's it reads the way the stock widget does, from the file Omarchy's
Hyprland config keeps (`~/.local/state/omarchy/monitor-workspaces`,
`default/hypr/monitor-workspaces.lua`), and a click runs that config's own
`o.workspaces.focus`. Re-verify both files, that one, and the Quickshell API
against `/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`, after every Omarchy or
Quickshell upgrade.

## Dependencies

Omarchy's shell only (`Quickshell.Hyprland` for the workspace list, `Quickshell.Io` for that file).
