# bar-workspaces

## What

Puts `hyprconf.workspaces` on the Omarchy bar in place of the stock
`omarchy.workspaces`: only the workspaces that exist, on two lines, Pac-Man on
the focused one — the widget itself is `plugin/README.md`.

`plugin/` is LINKED into `~/.config/omarchy/plugins/hyprconf.workspaces`, and
every run asks for a rescan — what picks a `git pull` up; the scan, the watch
and the `PluginRegistry.qml` lines behind them are
[`../bar-plugin.sh`](../bar-plugin.sh)'s header. Enabled ONCE, behind
`~/.local/state/hyprconf/workspaces-applied`; a folder `omarchy plugin add`
cloned (it has a `.git`) is left alone, to `omarchy plugin update`.

## Requires

Omarchy 4.0.4-1, `jq`, and [`../bar-plugin.sh`](../bar-plugin.sh) — the link,
rescan, enable and undo the four bar modules share, which a sparse checkout of
this directory brings along. No packages, no `sudo`. The enable needs the
running shell (without one the link is made and the next run enables it), and
the checkout has to stay put — the installed plugin is a link into it.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-workspaces && bash ~/.hyprconf/modules/bar-workspaces/install
```

## Settings

None — [`plugin/README.md`](plugin/README.md#settings).

## Undo

`bash modules/bar-workspaces/install undo` — disables the plugin (the stock
widget comes back), removes the link and the marker. With no shell answering,
the disable is done in `~/.config/omarchy/shell.json` itself — the bar entry goes
back to `omarchy.workspaces` — so no slot is left naming a plugin that is gone.

## Verified against Omarchy 4.0.4-1
