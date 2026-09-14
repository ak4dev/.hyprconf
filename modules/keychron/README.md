# keychron

## What
One udev rule at `/etc/udev/rules.d/70-keychron.rules` so [launcher.keychron.com](https://launcher.keychron.com) —
Keychron's web remapper, which drives a board over WebHID — can reach Keychron (`0x3434`) and Lemokey (`0x362d`)
boards and the mice behind their 2.4 GHz receivers. Without it the launcher lists no device: a `hidraw` node is created
`0600 root:root` (Arch's `50-udev-default.rules:18` sets no `MODE` for the subsystem) and every stock `uaccess` line for
`hidraw` is gated on an `ID_*` property these devices lack (`70-uaccess.rules:101,109,114,118`), so the browser, running
as you, cannot open it. `TAG+="uaccess"` is the whole mechanism: systemd's `73-seat-late.rules` turns the tag into a POSIX
ACL for whoever holds the active seat. Three things are load-bearing, and all three were verified on hardware:

- **`70-`, never `99-`** — `73-seat-late.rules` matches on `TAG==`, so a file sorting after it sets a tag nothing ever reads: correct in `udevadm info`, granting nothing.
- **Vendor alone** — the vendor-defined interface moves (`if01` on a Q2 Max, `if03` on a Link dongle, usage page `0xFF0A` on a 4K Link where the others use `0xFF60`; two dongles sharing a product id can expose different interface counts by pairing state), and the vendor match also covers the mice. The price: every HID interface gets a `hidraw` node, so while you hold the seat any process running as you can read those boards' raw reports.
- **No `MODE=`** — without a `GROUP=` it would mean `0660 root:root`, which grants a desktop user nothing; the ACL is what grants access. (Omarchy's own `default/udev/framework16-qmk-hid.rules` carries a `MODE="0660"` that buys it nothing, for the same reason.)

**Not covered:** a board paired over *Bluetooth* — its `hidraw` parent is a Bluetooth device and `ATTRS{idVendor}` lives on the USB parent these lines walk up to, so a different match is needed. Untested here.

## Requires
`sudo` and a terminal to answer its prompt; no packages, no running session. Omarchy has no udev command
(`omarchy commands --json` carries no udev route) but ships this shape: `install/hardware/framework/qmk-hid.sh:4-6`
copies `default/udev/framework16-qmk-hid.rules` into `/etc/udev/rules.d`. The rule is written only when the bytes
differ, then `udevadm control --reload-rules` and `udevadm trigger --subsystem-match=hidraw` reach devices already plugged
in — reload the launcher tab afterwards. Without a terminal, or with `--no-packages` (which the post-update hook passes),
it says so in one line and does nothing; it never fails the run.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/keychron && bash ~/.hyprconf/modules/keychron/install
```

## Settings
Another vendor is one more `SUBSYSTEM=="hidraw", ATTRS{idVendor}=="<id>", TAG+="uaccess"` line in `70-keychron.rules` (`lsusb` for the id); re-run, and the edited rule replaces the installed one.

## Undo
`bash ~/.hyprconf/modules/keychron/install undo` — `sudo rm` plus a rules reload. Every new `hidraw` node is
root-only again; an ACL already granted lasts until you re-plug the board or log out.

## Verified against Omarchy 4.0.3-1
Paths above read from the installed tree; systemd 261.2-1, udev's own rules as Arch ships them.
