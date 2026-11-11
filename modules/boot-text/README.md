# boot-text

## What
The scrolling boot log in place of Omarchy's splash: systemd's `[  OK  ] Started …` lines and the kernel's warnings, from the bootloader to the login screen. One drop-in, `/etc/limine-entry-tool.d/00-hyprconf-boot-text.conf`, adds three parameters to the cmdline Limine assembles. A `limine-mkinitcpio` rebuild follows, because with UKIs the cmdline is inside the boot image (`migrations/1791581004.sh`).

Omarchy's `quiet splash loglevel=0 systemd.show_status=false` lives in `omarchy-defaults.conf`, which the `omarchy-settings` package owns and its migrations rewrite. A drop-in can only append (`+=`) or replace the whole cmdline (`=`, which would have to restate the LUKS and resume parameters) (`/etc/limine-entry-tool.conf`, "Operators"). So this module adds its own values for those keys and makes sure they come later on the line. The kernel and systemd take the last value of a key.

**The `00-` prefix is load-bearing.** `limine-entry-tool` puts what it reads first *last* on the cmdline. A rebuilt `/boot/limine.conf` shows the order: `/etc/default/limine` first, then the drop-ins in reverse alphabetical order, each file's `+=` lines reversed too. A name sorting before `omarchy-defaults.conf` is therefore what places these values after Omarchy's. A `zz-` name, the first one shipped, placed them before Omarchy's, where they lost. Each value then does this:

- `splash=verbose`: plymouthd checks it before `splash`, wherever each sits ("no default splash because kernel command line has option splash=verbose", in `/usr/bin/plymouthd`), so Plymouth stays but runs in its text mode.
- `loglevel=4`: linux-omarchy's `CONFIG_CONSOLE_LOGLEVEL_DEFAULT`, which is what a boot without `quiet` prints (warnings and errors).
- `systemd.show_status=true`: systemd reads the last assignment of a key (`carries_param`, `migrations/1791581004.sh`).

**Plymouth stays on purpose, not `plymouth.enable=0`.** mkinitcpio's `systemd` install hook adds no console password agent, so Plymouth is what asks for the passphrase or a FIDO2 PIN ([yubikey](../yubikey/README.md)). In text mode it asks in text. The themed unlock screen goes with the splash, and `omarchy plymouth set` shows nothing until undo. Omarchy's other parameters stay as they are. Its `systemd.tty.term.console=dumb`, the fix for a boot that hangs on a black screen 1 in 10, leaves the status lines uncoloured.

## Requires
Omarchy booting through Limine (`limine-mkinitcpio`, from `limine-mkinitcpio-hook`; without it the module says so and skips), plus `sudo` and a terminal. No packages. A re-run with the drop-in already in place asks for nothing. Under `--no-packages` or without a terminal it prints one pointer line and skips. `limine-mkinitcpio` exits 0 even when a build fails, so its output is read too. On an `ERROR:` line the previous images stay on the ESP (they still boot), and the run says to finish with `sudo limine-mkinitcpio`.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/boot-text && bash ~/.hyprconf/modules/boot-text/install
```

## Settings
To change how much the kernel says, edit `loglevel=` in `00-hyprconf-boot-text.conf` (7 is every kernel message), then re-run. The edited drop-in replaces the installed one, and the images are rebuilt.

## Undo
`bash ~/.hyprconf/modules/boot-text/install undo`: `sudo rm` of the drop-in, then a `limine-mkinitcpio` rebuild. Omarchy's splash and themed unlock screen return from the next boot.

## Verified against Omarchy 4.5.0-3
limine-mkinitcpio-hook 1.40.0-2, plymouth 26.134.222-3, systemd 262.1-1, linux-omarchy 7.2.15-1. The paths and strings above were read from the installed tree. The boot itself needs a reboot, so it is verified by hand, not in the suite.
