# bar-clock

## What

Keeps Omarchy's own bar clock, `omarchy.clock`, on a format that prints
seconds: `hh:mm:ss AP`. The stock clock ticks every second for such a format
and once a minute otherwise (`shell/plugins/panels/clock/BarWidget.qml:34,126`),
so there is no widget here — only the format, set with Omarchy's own
`omarchy bar set` (`bin/omarchy-bar:426-456`) on any run that finds the clock
printing none.

Before 10.0 this module shipped a copy of the clock as the `hyprconf.clock`
plugin, for the seconds Omarchy 4.5 now ticks itself. A box that still carries
that link has it retired on the first run: the bar slot goes back to
`omarchy.clock` with every setting of the entry kept (format, week start, birth
year), and the link and its `clock-applied` marker go. Name `omarchy.clock`
where you named `hyprconf.clock`.

## Requires

Omarchy 4.5 with its shell running — `omarchy bar set` is the shell's write —
and `jq`. With no shell answering the run says so and the next one retries. No
packages, no `sudo`, no prompt. [`../bar-plugin.sh`](../bar-plugin.sh) is read
only to retire the old plugin; a sparse checkout of this directory brings it
along.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/bar-clock && bash ~/.hyprconf/modules/bar-clock/install
```

## Settings

Not a set-once choice. The format is yours (`omarchy bar set omarchy.clock
format …`) as long as it prints seconds — Omarchy's own test, an `s` outside a
quoted literal (`shell/plugins/panels/clock/Model.js:48-51`): one that prints
none goes back to `hh:mm:ss AP` on any run — `hyprsync`, a plain `hyprconf`,
and the hook after every `omarchy-update`. Right-clicking the clock walks
Omarchy's ring of presets, most of which print none, so one walk would
otherwise lose the seconds for good. A bar with no `omarchy.clock` on it is
left as it is.

## Undo

`bash modules/bar-clock/install undo` — a clock still on `hh:mm:ss AP` goes
back to the stock `dddd HH:mm`; a format you chose stays. Like the bar's
position, it sticks only after a full `hyprconf --undo`, which also removes the
hook. A folder an earlier install moved aside is left where it is: delete
`~/.config/omarchy/plugins/.hyprconf.clock.bak.<ts>` yourself.

## Verified against Omarchy 4.5.0-3
