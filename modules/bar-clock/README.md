# bar-clock

## What

Puts `plugin/` — Omarchy's own bar clock, sampling seconds — on the bar as
`hyprconf.clock`, formatted `hh:mm:ss AP`: the stock `omarchy.clock` samples
once a minute, so a seconds format sits frozen 59 of every 60. What it keeps
of Omarchy's, and its host contract: `plugin/README.md`.

Installed as a **symlink** into this checkout, so a `git pull` is the update
and every run asks the shell to rescan (its watch does not follow a link). A
same-id `omarchy plugin add` checkout is left to `omarchy plugin update`; a
real folder there is moved aside once as `.hyprconf.clock.bak.<ts>`.

## Requires

Omarchy's shell and `jq`; no packages, no sudo. With nothing answering it
links the folder and enables on the next run. The checkout has to stay put —
the plugin is a link into it, and the validator wants a trailing slash.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-clock && bash ~/.hyprconf/modules/bar-clock/install
```

## Settings

Enabled and formatted ONCE, behind `~/.local/state/hyprconf/clock-applied`:
the clock is yours afterwards (`omarchy bar set hyprconf.clock format …`) and
`omarchy plugin disable` sticks. `bar.centerAnchor` follows the swap once; an
anchor left naming nothing is repaired on any run, one you chose is not.

## Undo

`bash modules/bar-clock/install undo` — disable, `omarchy.clock`'s format back
to `dddd HH:mm`, the anchor back, link and marker gone.

Verified against Omarchy 4.0.3-1.
