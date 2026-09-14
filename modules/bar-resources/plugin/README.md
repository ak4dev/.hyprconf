# hyprconf.resources

An [Omarchy](https://omarchy.org) bar widget: CPU, RAM, GPU and network on
two aligned lines, in the bar's right section.

    <cpu> <thermo>41°  3%   <mem> 12.7/94.2G   ↑ 12.3kB/s
    <gpu> <thermo>36°  7%   <mem>  2.3/32.6G   ↓ 1.2MB/s

Top line: CPU temperature and utilisation, RAM used/total, upload rate.
Bottom line: the active GPU's temperature and utilisation, VRAM used/total,
download rate. Fed by two long-lived JSON streams bundled in `bin/`
(`hyprconf-gpu-info`, one line every two seconds; `hyprconf-stats`, one a
second, whose tick reads `/proc` and `/sys` and forks nothing — it paces
itself on bash's loadable `sleep` builtin, where the GPU feeder's sysfs
loops exec `/usr/bin/sleep`). Both emit numbers only; every glyph, unit and
column width is the widget's. The network rates are the default-route
interface's, read from `/proc/net/route` — by definition the one carrying the
traffic, so with a full-tunnel VPN up the rates follow the tunnel. Columns are
fixed-width, sized from their widest value, so nothing shifts as the numbers
change. On a multi-GPU box the **active** card is shown — the one with the most
VRAM in use (ties: utilisation, then index), re-evaluated every sample; NVIDIA
(`nvidia-smi --loop`), AMD (`gpu_busy_percent`) and Intel (the `xe` driver's GT
idle residency) in that order. An Intel iGPU has no VRAM of its own, so it reads
`shared`, and its tooltip carries the GT clock where NVIDIA's carries power
draw. A feeder that exits without ever emitting a line means the hardware is not
there and is left alone (the GPU cells stay blank but sized); one that emitted a
line and then died is restarted on a capped backoff, 1 s → 32 s, then parked
(`Service.qml`'s header has the rule). An Intel card in runtime suspend is never
touched: residency, hwmon and clock each resume an `xe` device on read, so a
tick that finds `power/runtime_status` saying `suspended` or `suspending` reads
nothing off that card and ranks it idle. Every other value is measured, a
missing file included. Click the CPU cell for `btop`
(`omarchy-launch-or-focus-tui btop`).

Omarchy's own stats were the first stop and neither fits (4.0.3-1):
`omarchy-system-stats --bar-widget` is cpu/memory/load through three awk forks
per call, with no network, temperature or GPU, and the bar's `command` module
runs `bash -lc` off a Timer inside the per-screen `Variants` — a login shell per
monitor per interval, for one line of output where this draws two.

## Install

Drop the folder in and enable it by id — Omarchy's own by-hand path
(`/usr/share/omarchy/shell/README.md` › Installing by hand):

```bash
git clone https://github.com/ak4dev/.hyprconf
cp -r .hyprconf/modules/bar-resources/plugin ~/.config/omarchy/plugins/hyprconf.resources
omarchy-shell shell rescanPlugins
omarchy plugin enable hyprconf.resources
```

Once this folder is published as a repository of its own, `omarchy plugin add
<url> --enable --yes` is the one-step form. `--yes` is the scripted path —
Omarchy 4.0.3 confirms in a terminal even when given arguments
(`/usr/share/omarchy/shell/README.md`) — and it skips the review-the-code
prompt, so read the repository first.

It lands in the right section (`barWidget.defaultSection`); move it with
`omarchy bar move hyprconf.resources …`. `omarchy plugin disable
hyprconf.resources` takes it off the bar and stops the service with it — the
same id is both switches; `omarchy plugin remove hyprconf.resources` deletes a
git checkout, unlinks a symlink, and backs up a hand-copied folder.

## Settings

None: the widget reads no `omarchy bar set` key. The bar's own font and
foreground apply.

## How it runs

The manifest declares two kinds. `Widget.qml` is the `bar-widget` and is
built once per monitor, like every bar widget; `Service.qml` is the
`service`, which Omarchy's shell loads **once** for the session — any enabled
plugin declaring `kinds: ["service"]` with an `entryPoints.service`, first-party
or not (`shell/shell.qml`, `_syncServices` / `ensureService`; a third-party
instance is created unparented and held alive by the shell's `_services` map) —
and it is the one that runs the two feeders. The widget reads the numbers back
with `bar.shell.serviceFor("hyprconf.resources")` — the accessor Omarchy scopes
to a plugin's own id (`shell/services/PluginShellApi.qml`). So a six-monitor
desk pays for one pair of feeders, not six, and on NVIDIA for one NVML session
rather than six. There is still only one id and one on/off switch.

## Host contract (Omarchy 4.0.3-1)

An installed third-party widget never gets the host Bar: its `bar` is a
`Ui/PluginBarApi.qml` facade and `bar.shell` a `services/PluginShellApi.qml`,
both scoped to this plugin's own id (`shell/plugins/bar/Bar.qml:2002-2003`,
`shell/shell.qml:221`). Those two files are the whole contract — a member that
exists only on the Bar reads back `undefined`, with nothing logged anywhere.
This widget uses `bar.barForeground`, `bar.fontFamily`,
`bar.run(command)`, `bar.showTooltip(target, text)` / `bar.hideTooltip(target)`
and `bar.shell.serviceFor("hyprconf.resources")`, plus the `bar`, `moduleName`
and `settings` the bar's `ModuleSlot.injectProps` sets on it.

The two feeders in `bin/` are run by absolute path, resolved from the service
file's own URL rather than from `PATH`: the shell loads an entry point as a
percent-encoded `file://` URL (`services/PluginRegistry.qml` `entryPointUrl` →
`Commons/Util.qml` `fileUrl`), so `Qt.resolvedUrl(".")` is that URL's directory
and `decodeURIComponent` gives the filesystem path back — a space or a `%` in
the path survives.
Re-verify both files, and the Quickshell API against
`/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`, after every Omarchy or Quickshell
upgrade.

## Dependencies

- `bash` ≥ 5 (both feeders; `hyprconf-stats` paces itself on the package's
  loadable `sleep` builtin when present and `/usr/bin/sleep` otherwise, which
  is the one `hyprconf-gpu-info`'s sysfs loops always use) — Omarchy's base.
- `hwdata` (`/usr/share/hwdata/pci.ids`, an Intel card's name and an AMD one
  the driver does not name itself — an APU has no `product_name`; a base
  dependency of `systemd`). Without it an Intel card reads "Intel Graphics"
  and such an AMD card reads "GPU <n>".
- `btop` for the click — Omarchy's base.
- `nvidia-utils` (`nvidia-smi`) on an NVIDIA box, optional: with no
  `nvidia-smi` the AMD and Intel sysfs paths are tried instead. On a hybrid
  laptop the `nvidia-smi --loop` stream holds the discrete GPU open for the
  whole session, which keeps it out of runtime D3 — disable the widget on
  battery if that matters.
- No `iproute2`: the default route is read from `/proc/net/route`.
