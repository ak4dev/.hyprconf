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

```bash
omarchy plugin add https://github.com/ak4dev/omarchy-hyprconf-active-window --enable
```

It takes `omarchy.active-window`'s place on the bar (or, with no stock entry
to replace, lands in the left section after the workspaces). `omarchy plugin
disable hyprconf.active-window` puts the stock widget back and sticks.
`omarchy plugin remove hyprconf.active-window` restores the stock widget
too, and deletes a git checkout; a folder copied in by hand is moved to
`~/.config/omarchy/plugins/.hyprconf.active-window.bak.<timestamp>` instead.

With the [hyprconf](https://github.com/ak4dev/.hyprconf) overlay installed,
its `install.sh` syncs this folder from the checkout on every run and
enables it once — unless the folder is a git checkout from `omarchy plugin
add`, which it leaves to `omarchy plugin update`.

## Settings

The stock widget's one setting, the character budget as px of body-size
text on one line (280 by default), laid out here on two lines:

```bash
omarchy bar set hyprconf.active-window maxWidth 400
```

## Dependencies

Omarchy's shell only (`Quickshell.Wayland` for the focused toplevel).
