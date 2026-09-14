# bar-resources

## What

Installs `plugin/` — the `hyprconf.resources` bar widget: CPU, RAM, GPU and
network on two aligned lines, fed by the two streams in `plugin/bin/`. What it
shows, its host contract and its dependencies: [`plugin/README.md`](plugin/README.md).

`~/.config/omarchy/plugins/hyprconf.resources` is a **symlink** to `plugin/`, so
the checkout is the installed widget (so it stays put) and the feeders exec
through the link. The shell's `inotifywait -r` does not descend one
(`PluginRegistry.qml:663-667`), so every run asks for a rescan — that is what
carries a `git pull` into the running bar. The widget is enabled **once**, behind
`~/.local/state/hyprconf/resources-applied`, so `omarchy plugin disable
hyprconf.resources` sticks. A same-id `omarchy plugin add` checkout is left alone;
a real folder of that name is moved aside as `.hyprconf.resources.bak.<ts>`.

## Requires

Omarchy's shell running — the enable needs it; without one the module says so and
enables on the next run. No packages (`bash`, `btop`, `hwdata` are in the base).

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-resources && bash ~/.hyprconf/modules/bar-resources/install
```

## Settings

None of its own. It lands in `barWidget.defaultSection` (right); move it with
`omarchy bar move hyprconf.resources …`.

## Undo

`bash modules/bar-resources/install undo` — disables the widget, removes the link
and the marker, rescans. An earlier install's backup folder stays.

## Verified against Omarchy 4.0.3-1
