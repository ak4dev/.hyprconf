# bar-workspaces

## What

Puts `hyprconf.workspaces` on the Omarchy bar in place of the stock
`omarchy.workspaces`: only the workspaces that exist, on two lines, Pac-Man on
the focused one — the widget itself is `plugin/README.md`.

`plugin/` is LINKED into `~/.config/omarchy/plugins/hyprconf.workspaces`: the
third-party scan follows a symlinked folder (`PluginRegistry.qml:712-713`) and
`omarchy plugin remove` unlinks one (`bin/omarchy-plugin-remove:87,99-101`),
but `inotifywait -r` never descends one (`PluginRegistry.qml:663-674`), so
every run asks for a rescan — what picks a `git pull` up. Enabled ONCE, behind
`~/.local/state/hyprconf/workspaces-applied`; a folder `omarchy plugin add`
cloned (it has a `.git`) is left alone, to `omarchy plugin update`.

## Requires

Omarchy 4.0.3-1 and `jq`; no packages, no `sudo`. The enable needs the running
shell (without one the link is made and the next run enables it), and the
checkout has to stay put — the installed plugin is a link into it.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-workspaces && bash ~/.hyprconf/modules/bar-workspaces/install
```

## Settings

None: the stock widget reads no `omarchy bar set` key and neither does this
one. The bar's own font and foreground apply.

## Undo

`bash modules/bar-workspaces/install undo` — disables the plugin (the stock
widget comes back), removes the link and the marker.

## Verified against Omarchy 4.0.3-1
