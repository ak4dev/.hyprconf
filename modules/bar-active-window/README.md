# bar-active-window

## What

Puts `plugin/` — `hyprconf.active-window`, the focused window's title on **two**
caption-size lines instead of Omarchy's one — on the bar, and nothing else; its
behaviour, setting and deltas: [`plugin/README.md`](plugin/README.md). The folder
is **symlinked** into `~/.config/omarchy/plugins/` (a `git pull` then updates the
widget, and every run asks for a rescan: the shell's `inotifywait -r` never
descends a symlink, `PluginRegistry.qml:663-674`) and **enabled once**, with no
placement of its own — Omarchy's default bar carries no `omarchy.active-window`,
so `defaultSection: left` puts it after `omarchy.workspaces` (`:270-275`); a bar
that has the stock widget gets this copy swapped into that slot (`:529-534`).
Disabling it then sticks.

## Requires

Omarchy 4.0.3-1 with its shell running, `jq`, coreutils; no packages, no `sudo`.
With no shell answering the link is made and the enable retried next run, and
the checkout stays put: what lands in the plugins directory is a symlink to it.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-active-window && bash ~/.hyprconf/modules/bar-active-window/install
```

## Settings

`omarchy bar set hyprconf.active-window maxWidth 400` — the budget (px of body
text on one line, 280 default), here over two. Marker: `${HYPRCONF_STATE:-~/.local/state/hyprconf}/active-window-applied`.

## Undo

`bash modules/bar-active-window/install undo` — disables it (stock back, `:555`),
removes the module's own symlink and the marker, rescans. A real directory or a
git checkout there is left alone; a folder an install moved aside stays as
`.hyprconf.active-window.bak.<ts>` to delete.

## Verified against Omarchy 4.0.3-1

Every `PluginRegistry.qml` line above was re-read in `/usr/share/omarchy` there.
