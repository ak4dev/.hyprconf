# hyprconf.workspaces

An [Omarchy](https://omarchy.org) bar widget replacing the stock
`omarchy.workspaces`: only the workspaces that exist (no fixed 1–5 pills, no
id cap), stacked on two lines so the widget takes half the width, with a
Pac-Man (`󰮯`, nf-md-pac_man) on the focused workspace. Click focuses. A
`clonedFrom` copy of the stock widget (NOTICE carries Omarchy's MIT notice):
enabling it swaps it into the stock widget's slot on the bar, and the stock
IPC target keeps working.

## Install

Drop the folder in and enable it by id — Omarchy's own by-hand path
(`/usr/share/omarchy/shell/README.md` › Installing by hand):

```bash
git clone https://github.com/ak4dev/.hyprconf
cp -r .hyprconf/plugins/hyprconf-workspaces ~/.config/omarchy/plugins/hyprconf.workspaces
omarchy-shell shell rescanPlugins
omarchy plugin enable hyprconf.workspaces
```

Once this folder is published as a repository of its own, `omarchy plugin add
<url> --enable --yes` is the one-step form. `--yes` is not optional for this
widget: without it `omarchy-plugin-add` asks which bar section to put it in
(`select_bar_widget_placement`, `/usr/bin/omarchy-plugin-add:161-162`, Omarchy
4.0.3-1) and the answer becomes a placement, which moves the widget out of the
stock slot its `clonedFrom` manifest just claimed. `--yes` also skips Omarchy's
review-the-code prompt, so read the repository first.

It takes `omarchy.workspaces`' place on the bar. `omarchy plugin disable
hyprconf.workspaces` puts the stock widget back and sticks. `omarchy plugin
remove hyprconf.workspaces` restores the stock widget too, and deletes a git
checkout; a folder copied in by hand is moved to
`~/.config/omarchy/plugins/.hyprconf.workspaces.bak.<timestamp>` instead.

With the [hyprconf](https://github.com/ak4dev/.hyprconf) overlay installed,
its `install.sh` syncs this folder from the checkout on every run and
enables it once — unless the folder is a git checkout from `omarchy plugin
add`, which it leaves to `omarchy plugin update`.

## Settings

None: the stock widget reads no `omarchy bar set` key, and neither does
this one. The bar's own font and foreground apply.

## Dependencies

Omarchy's shell only (`Quickshell.Hyprland` for the workspace list).
