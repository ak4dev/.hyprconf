# hyprconf.clock

[Omarchy](https://omarchy.org)'s own bar clock, ticking seconds. The stock
`omarchy.clock` samples the clock once a minute, so a format with seconds
sits frozen 59 seconds of every one; this is that widget with its precision
raised to seconds and nothing else changed — the calendar on click,
right-click cycling the formats, middle-click the timezone picker, the same
settings. `BarWidget.qml` and `Model.js` are Omarchy's (the header of the
first names the two deltas; NOTICE carries Omarchy's MIT notice), and the
calendar panel is loaded from the running Omarchy's own `Panel.qml`, so it
is never behind the installed release. A `clonedFrom` copy: enabling it
swaps it into the stock clock's slot on the bar, and the stock IPC target
keeps working.

## Install

```bash
omarchy plugin add https://github.com/ak4dev/omarchy-hyprconf-clock --enable
omarchy bar set hyprconf.clock format 'hh:mm:ss AP'
```

It takes `omarchy.clock`'s place on the bar. The bar centres on an anchor
id in `~/.config/omarchy/shell.json` (`bar.centerAnchor`, `omarchy.clock` by
default), and that value is a plain id with no clone resolution — set it to
`"hyprconf.clock"` there to keep the clock dead centre (Omarchy ships no
command for the key). `omarchy plugin disable hyprconf.clock` puts the stock
clock back and sticks. `omarchy plugin remove hyprconf.clock` restores the
stock clock too, and deletes a git checkout; a folder copied in by hand is
moved to `~/.config/omarchy/plugins/.hyprconf.clock.bak.<timestamp>`
instead.

With the [hyprconf](https://github.com/ak4dev/.hyprconf) overlay installed,
its `install.sh` syncs this folder from the checkout on every run, and once
— on the first run with a live shell — enables it, sets the format to
`hh:mm:ss AP` and moves the anchor; unless the folder is a git checkout from
`omarchy plugin add`, which it leaves to `omarchy plugin update`.

## Settings

The stock clock's, under the new id:

```bash
omarchy bar set hyprconf.clock format 'HH:mm'            # the label; formatAlt is the right-click twin
omarchy bar set hyprconf.clock verticalFormat 'HH\n—\nmm' # side-rail bars; verticalFormatAlt likewise
omarchy bar set hyprconf.clock weekStartDay monday        # the calendar's first column
```

`format` takes `Qt.formatDateTime` tokens (`ww` is the ISO week). The
calendar's `birthYear` / `lifeExpectancy` are set from the panel itself.

## Dependencies

Omarchy's shell only — the panel is Omarchy's own file at
`$OMARCHY_PATH/shell/plugins/panels/clock/Panel.qml`.

## Keeping it current

An Omarchy release that changes its clock changes the stock `BarWidget.qml`
or `Model.js`; the two here are refreshed from them by hand (the recipe is
in `BarWidget.qml`'s header) and the version bumped.
