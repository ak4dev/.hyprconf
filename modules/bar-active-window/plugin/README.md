# hyprconf.active-window

An [Omarchy](https://omarchy.org) bar widget replacing the stock
`omarchy.active-window`: the focused window's title on **two** caption-size
lines, so the same character budget takes about half the width. Everything
else is the stock widget's behaviour — title or app id, hidden when nothing
is focused or the bar is vertical, the full title as a tooltip, left-click
focuses, middle- or right-click closes. A `clonedFrom` copy of the stock
widget (NOTICE carries Omarchy's MIT notice): enabling it swaps it into the
stock widget's slot on the bar, and the stock IPC target keeps working.

## Install

Drop the folder in and enable it by id — Omarchy's own by-hand path
(`/usr/share/omarchy/shell/README.md` › Installing by hand):

```bash
git clone https://github.com/ak4dev/.hyprconf
cp -r .hyprconf/modules/bar-active-window/plugin ~/.config/omarchy/plugins/hyprconf.active-window
omarchy-shell shell rescanPlugins
omarchy plugin enable hyprconf.active-window
```

Once this folder is published as a repository of its own, `omarchy plugin add
<url> --enable --yes` is the one-step form. `--yes` is not optional for this
widget: without it `omarchy-plugin-add` asks which bar section to put it in
(`select_bar_widget_placement`, `/usr/bin/omarchy-plugin-add:162`, Omarchy
4.0.4-1) and the answer becomes a placement, which moves the widget out of the
stock slot its `clonedFrom` manifest just claimed. `--yes` also skips Omarchy's
review-the-code prompt, so read the repository first.

Omarchy's default bar carries no `omarchy.active-window` entry
(`config/omarchy/shell.json` › `.bar.layout`), so it lands in the section its
manifest names — `left`, after `omarchy.workspaces`, the anchor `barTarget` uses
there (`PluginRegistry.qml:270-275`), clone-resolved to a `hyprconf.workspaces`
copy while that one holds the slot. On a bar that does carry the stock widget,
the copy replaces that entry in place (`PluginRegistry.qml:529-534`). `omarchy plugin
disable hyprconf.active-window` puts the stock widget back and sticks
(`restoreCloneSource`, `PluginRegistry.qml:555`). `omarchy plugin remove
hyprconf.active-window` restores the stock widget too, and unlinks a symlinked
folder rather than deleting what it points at (`omarchy-plugin-remove:99-101`).

The [hyprconf](https://github.com/ak4dev/.hyprconf) overlay ships this folder as
`modules/bar-active-window`: its `install` symlinks it into
`~/.config/omarchy/plugins/` and enables it once — see that module's README.

## Settings

The stock widget's one setting, the character budget as px of body-size
text on one line (280 by default), laid out here on two lines:

```bash
omarchy bar set hyprconf.active-window maxWidth 400
```

## Host contract (Omarchy 4.0.4-1)

An installed third-party widget never gets the host Bar: its `bar` is a
`Ui/PluginBarApi.qml` facade (`shell/plugins/bar/Bar.qml:1999-2003`) and
`bar.shell` a `services/PluginShellApi.qml` scoped to this plugin's own id
(`Bar.qml:229-248` → `shell/shell.qml:684`). Those two files are the whole
contract — a member that exists only on the Bar reads back `undefined`, with
nothing logged anywhere. This widget uses `bar.barForeground`,
`bar.fontFamily`, `bar.showTooltip(target, text)` and
`bar.hideTooltip(target)`, plus the `bar`, `moduleName` and `settings` the
bar's `ModuleSlot.injectProps` sets on it. Re-verify both files, and the
Quickshell API against `/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`, after
every Omarchy or Quickshell upgrade.

## Dependencies

Omarchy's shell only (`Quickshell.Wayland` for the focused toplevel).
