# hyprconf.clock

[Omarchy](https://omarchy.org)'s own bar clock, ticking seconds. The stock
`omarchy.clock` samples the clock once a minute, so a format with seconds
sits frozen 59 seconds of every one; this is that widget with its precision
raised to seconds — the calendar on click, right-click cycling the formats,
middle-click the timezone picker, the same settings, and what the calendar
saves (week start, birth year) written under this plugin's own id.
`BarWidget.qml` is Omarchy's with three deltas (its header names them, and
the refresh recipe), `Model.js` is the subset of Omarchy's the bar label
calls, and NOTICE carries Omarchy's MIT notice; the calendar panel is loaded
from the running Omarchy's own `Panel.qml`, so it is never behind the
installed release. A `clonedFrom` copy: enabling it swaps it into the stock
clock's slot on the bar, and the stock IPC target keeps working.

## Install

Drop the folder in and enable it by id — Omarchy's own by-hand path
(`/usr/share/omarchy/shell/README.md` › Installing by hand):

```bash
git clone https://github.com/ak4dev/.hyprconf
cp -r .hyprconf/modules/bar-clock/plugin ~/.config/omarchy/plugins/hyprconf.clock
omarchy-shell shell rescanPlugins
omarchy plugin enable hyprconf.clock
omarchy bar set hyprconf.clock format 'hh:mm:ss AP'
```

Once this folder is published as a repository of its own, `omarchy plugin add
<url> --enable --yes` is the one-step form. `--yes` is not optional for this
widget: without it `omarchy-plugin-add` asks which bar section to put it in
(`select_bar_widget_placement`, `/usr/bin/omarchy-plugin-add:161-162`, Omarchy
4.0.3-1) and the answer becomes a placement, which moves the widget out of the
stock slot its `clonedFrom` manifest just claimed. `--yes` also skips Omarchy's
review-the-code prompt, so read the repository first.

It takes `omarchy.clock`'s place on the bar. The bar centres on an anchor
id in `~/.config/omarchy/shell.json` (`bar.centerAnchor`, `omarchy.clock` by
default), and that value is a plain id with no clone resolution — set it to
`"hyprconf.clock"` there to keep the clock dead centre (Omarchy ships no
command for the key).

`omarchy plugin disable hyprconf.clock` puts the stock widget back in the
slot; `omarchy plugin remove hyprconf.clock` does that and drops the folder.
Neither is the whole way back — both leave the same two things behind:

```bash
omarchy bar set omarchy.clock format 'dddd HH:mm'   # the disable copies this plugin's WHOLE bar entry onto omarchy.clock and rewrites only its id, so a seconds format rides along onto a widget that samples once a minute
sleep 1; f=~/.config/omarchy/shell.json; jq 'if .bar.centerAnchor == "hyprconf.clock" then .bar.centerAnchor = "omarchy.clock" else . end' "$f" > "$f.tmp" && mv "$f.tmp" "$f"   # the anchor is a plain id: it keeps naming a widget the bar no longer carries, and the centre section falls back to centring the whole group
```

Run the anchor line last and a beat behind the commands above — that is the
`sleep`: they go through the shell, which persists `shell.json` on its next
event-loop turn (a Quickshell `FileView`), while this edit does not, so an
early read is stale and the shell's own write takes it back.

## Settings

The stock clock's, under the new id:

```bash
omarchy bar set hyprconf.clock format 'HH:mm'            # the label; formatAlt is the right-click twin
omarchy bar set hyprconf.clock verticalFormat 'HH\n—\nmm' # side-rail bars; verticalFormatAlt likewise
omarchy bar set hyprconf.clock weekStartDay monday        # the calendar's first column
```

`format` takes `Qt.formatDateTime` tokens (`ww` is the ISO week). The
calendar's `birthYear` / `lifeExpectancy` are set from the panel itself.

## Host contract (Omarchy 4.0.3-1)

An installed third-party widget never gets the host Bar: its `bar` is a
`Ui/PluginBarApi.qml` facade and `bar.shell` a `services/PluginShellApi.qml`,
both scoped to this plugin's own id (`shell/plugins/bar/Bar.qml:2002-2003`,
`shell/shell.qml:221`). Those two files are the whole contract — a member that
exists only on the Bar reads back `undefined`, with nothing logged anywhere.
This widget uses `bar.run(command)` and
`bar.shell.updateEntryInline(id, settings)`, plus the `bar`, `moduleName` and
`settings` the bar's `ModuleSlot.injectProps` sets on it — and hands all three
down to the stock `Panel.qml` it loads (`injectPanel()`), which is what keeps
the calendar's own settings writes landing under this plugin's id.
Re-verify both files, and the Quickshell API against
`/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`, after every Omarchy or Quickshell
upgrade.

## Dependencies

Omarchy's shell only — the panel is Omarchy's own file at
`$OMARCHY_PATH/shell/plugins/panels/clock/Panel.qml`.
