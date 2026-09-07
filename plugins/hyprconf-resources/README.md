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
loops exec `/usr/bin/sleep`). The network rates are the first wired link
that is up, else the default-route interface from `/proc/net/route`
(Wi-Fi, a tunnel). Columns are fixed-width, sized from their widest value,
so nothing shifts as the numbers change. On a multi-GPU box the **active**
card is shown — the one with the most VRAM in use (ties: utilisation, then
index), re-evaluated every sample; NVIDIA (`nvidia-smi --loop`), AMD
(`gpu_busy_percent`) and Intel (the `xe` driver's GT idle residency) in that
order. An Intel iGPU has no VRAM of its own, so it reads `shared`, and its
tooltip carries the GT clock where NVIDIA's carries power draw. A feeder that exits without ever emitting a line means the hardware is
not there and is left alone (the GPU cells stay blank but sized); one that
emitted a line and then died is restarted on a capped backoff — 1 s, 2 s,
4 s, 8 s, 16 s, 32 s, then parked until the shell restarts, and the ladder is
refilled by the next line that arrives. An Intel card in runtime suspend is
never touched: residency, hwmon and clock each resume an `xe` device on read,
so a tick that finds `power/runtime_status` saying anything but `active`
reads nothing off that card and ranks it idle. Click the CPU cell for `btop`
(`omarchy-launch-or-focus-tui btop`).

## Install

```bash
omarchy plugin add https://github.com/ak4dev/omarchy-hyprconf-resources --enable
```

It lands in the right section (`barWidget.defaultSection`); move it with
`omarchy bar move hyprconf.resources …`. `omarchy plugin disable
hyprconf.resources` takes it off the bar and sticks. `omarchy plugin remove
hyprconf.resources` deletes a git checkout; a folder copied in by hand is
moved to `~/.config/omarchy/plugins/.hyprconf.resources.bak.<timestamp>`
instead.

With the [hyprconf](https://github.com/ak4dev/.hyprconf) overlay installed,
its `install.sh` syncs this folder from the checkout on every run and
enables it once — unless the folder is a git checkout from `omarchy plugin
add`, which it leaves to `omarchy plugin update`.

## Settings

None: the widget reads no `omarchy bar set` key. The bar's own font and
foreground apply.

## Dependencies

- `bash` ≥ 5 (both feeders; `hyprconf-stats` paces itself on the package's
  loadable `sleep` builtin when present and `/usr/bin/sleep` otherwise, which
  is the one `hyprconf-gpu-info`'s sysfs loops always use) — Omarchy's base.
- `hwdata` (`/usr/share/hwdata/pci.ids`, an Intel card's name; a base
  dependency of `systemd`). Without it the card reads "Intel Graphics".
- `btop` for the click — Omarchy's base.
- `nvidia-utils` (`nvidia-smi`) on an NVIDIA box, optional: with no
  `nvidia-smi` the AMD and Intel sysfs paths are tried instead. On a hybrid
  laptop the `nvidia-smi --loop` stream holds the discrete GPU open for the
  whole session, which keeps it out of runtime D3 — disable the widget on
  battery if that matters.
- No `iproute2`: the default route is read from `/proc/net/route`.
