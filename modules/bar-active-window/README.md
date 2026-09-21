# bar-active-window

## What

Puts `plugin/` — `hyprconf.active-window`, the focused window's title on **two**
caption-size lines instead of Omarchy's one — on the bar, and nothing else; its
behaviour, setting and deltas: [`plugin/README.md`](plugin/README.md). The folder
is **symlinked** into `~/.config/omarchy/plugins/` (a `git pull` then updates the
widget, and every run asks for a rescan — why:
[`../bar-plugin.sh`](../bar-plugin.sh)'s header) and **enabled once**, with no
placement of its own — where it lands, and what it displaces:
[`plugin/README.md`](plugin/README.md#install). Disabling it then sticks.

## Requires

Omarchy 4.0.4-1 with its shell running, `jq`, coreutils, and [`../bar-plugin.sh`](../bar-plugin.sh) — the link, rescan,
enable and undo the four bar modules share, which a sparse checkout of this directory brings along; no packages, no `sudo`.
With no shell answering the link is made and the enable retried next run; the checkout stays put (the installed plugin is a symlink to it).

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-active-window && bash ~/.hyprconf/modules/bar-active-window/install
```

## Settings

`omarchy bar set hyprconf.active-window maxWidth 400` — the budget (px of body
text on one line, 280 default), here over two. Marker: `${HYPRCONF_STATE:-~/.local/state/hyprconf}/active-window-applied`.

## Undo

`bash modules/bar-active-window/install undo` — disables it, which hands the slot
back to Omarchy's stock title widget (`PluginRegistry.qml:555`); where the enable
had ADDED the slot instead, that comes off too while this copy still holds it, so
a default bar returns to stock and a stock title placed since is left. Then the
module's own symlink and the marker go, and it rescans. A real directory or a git
checkout there is left alone; a folder an install moved aside stays as
`.hyprconf.active-window.bak.<ts>` to delete. With no shell answering, the same
swap is done in `~/.config/omarchy/shell.json` itself: the entry back to
`omarchy.active-window`, or off where the enable had added the slot.

## Verified against Omarchy 4.0.4-1
