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
cp -r .hyprconf/plugins/hyprconf-active-window ~/.config/omarchy/plugins/hyprconf.active-window
omarchy-shell shell rescanPlugins
omarchy plugin enable hyprconf.active-window
```

Once this folder is published as a repository of its own, `omarchy plugin add
<url> --enable --yes` is the one-step form. `--yes` is not optional for this
widget: without it `omarchy-plugin-add` asks which bar section to put it in
(`select_bar_widget_placement`, `/usr/bin/omarchy-plugin-add:161-162`, Omarchy
4.0.3-1) and the answer becomes a placement, which moves the widget out of the
stock slot its `clonedFrom` manifest just claimed. `--yes` also skips Omarchy's
review-the-code prompt, so read the repository first.

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
