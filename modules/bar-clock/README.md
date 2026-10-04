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

Omarchy's shell, `jq`, and [`../bar-plugin.sh`](../bar-plugin.sh) — the link, rescan, enable and undo the four bar
modules share, which a sparse checkout of this directory brings along; no packages, no sudo. With nothing answering it links
the folder and enables on the next run. The checkout has to stay put — the plugin is a link into it, and the validator wants
a trailing slash.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-clock && bash ~/.hyprconf/modules/bar-clock/install
```

## Settings

Enabled ONCE, behind `~/.local/state/hyprconf/clock-applied`, so `omarchy
plugin disable` sticks. The format is yours (`omarchy bar set hyprconf.clock
format …`) as long as it ticks seconds: one with no `s` outside a quoted
literal goes back to `hh:mm:ss AP` on any run — `hyprsync`, and the hook
after every `omarchy-update`. Right-clicking the clock walks Omarchy's format
ring, which has no seconds preset, so one walk would otherwise lose them for
good. The bar can keep the old label until the shell restarts — Omarchy
rebuilds a plugin widget from a stale copy of its entry on every rescan — and
`omarchy-update` ends with that restart, so `hyprsync` shows it; after a plain
`hyprconf` run, `omarchy-restart-shell`. `bar.centerAnchor` follows the swap
once; an anchor left naming nothing is repaired on any run, one you chose is
not.

## Undo

`bash modules/bar-clock/install undo` — while `hyprconf.clock` is still on the
bar: disable, and `omarchy.clock`'s format back to `dddd HH:mm`; a stock clock
you had already gone back to keeps the format you set. Then the anchor back, link
and marker gone. A folder an install moved aside is left where it is: delete
`.hyprconf.clock.bak.<ts>` yourself. With no shell answering, the entry goes back
to `omarchy.clock` with its format in `~/.config/omarchy/shell.json` itself.

## Verified against Omarchy 4.0.4-1
