# bar

## What

Keeps Omarchy's bar on the **top** edge. A 200 ms press-and-hold, or a drag of a
few pixels, on the bar's centre section moves the bar to whichever screen edge
the pointer is let go nearest (`shell/plugins/bar/Bar.qml:1552,1597,1637-1690`,
`:475`), so a slow click between two widgets can send it to the side. Omarchy
has no setting that locks it. Any run that finds `bar.position` set to `bottom`,
`left` or `right` puts it back with Omarchy's own `omarchy bar position top`,
which also reloads the running shell (`bin/omarchy-bar:198-205`,
`bin/omarchy-shell-config:14-18,53-62`).

## Requires

`jq` and `omarchy-bar`, both in a stock Omarchy. No packages, no `sudo`, no
prompt.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar && bash ~/.hyprconf/modules/bar/install
```

## Settings

None. This is not a set-once choice: `hyprsync`, a plain `hyprconf` run and the
hook after every `omarchy-update` all put the bar back on top, so a move with
`omarchy bar position`, the menu or a drag lasts only until the next run. A
`position` that is already `top`, missing or not one of the four edges (which
Omarchy reads as top, `shell/plugins/bar/BarModel.js:5-8`) is left as it is.

## Undo

`bash ~/.hyprconf/modules/bar/install undo` does nothing: top is Omarchy's own
default (`config/omarchy/shell.json:8`), so there is nothing to restore. A move
sticks again only after a full `hyprconf --undo`, which also removes the hook.

## Verified against Omarchy 4.0.4-1
