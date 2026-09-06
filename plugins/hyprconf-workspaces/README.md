# hyprconf.workspaces

An [Omarchy](https://omarchy.org) bar widget replacing the stock
`omarchy.workspaces`: only the workspaces that exist (no fixed 1–5 pills, no
id cap), stacked on two lines so the widget takes half the width, with a
Pac-Man (`󰮯`, nf-md-pac_man) on the focused workspace. Click focuses. A
`clonedFrom` copy of the stock widget (NOTICE carries Omarchy's MIT notice):
enabling it swaps it into the stock widget's slot on the bar, and the stock
IPC target keeps working.

## Install

```bash
omarchy plugin add https://github.com/ak4dev/omarchy-hyprconf-workspaces --enable
```

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
