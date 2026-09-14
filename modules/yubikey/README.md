# yubikey

## What
`hyprconf-yubikey` on PATH (one symlink into `~/.local/bin`). Omarchy's `omarchy-setup-security-fido2` enrols a FIDO2 key for `sudo` and polkit; what it does not do is let the key unlock the encrypted root **at boot**. This is that missing half, on Omarchy's own boot chain — Limine, `limine-mkinitcpio`, mkinitcpio drop-ins, `omarchy snapshot`. Installing changes nothing: the tool is run by hand.

```bash
hyprconf-yubikey status     # devices, token slot, both drop-ins, the assembled kernel cmdline
hyprconf-yubikey enroll     # the whole setup (prompts: LUKS passphrase, FIDO2 PIN, touch)
hyprconf-yubikey sudo       # = omarchy-setup-security-fido2 (sudo + polkit)
hyprconf-yubikey disable    # back to passphrase-only boot; the LUKS slot stays
hyprconf-yubikey remove     # wipe the FIDO2 slot, then disable
hyprconf-yubikey help       # flags, what each step changes, the limits
```

`enroll` installs `libfido2` (`omarchy-pkg-add`), takes an `omarchy snapshot create`, enrols the key with `systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes`, then writes two drop-ins and rebuilds with `limine-mkinitcpio`:

- `/etc/mkinitcpio.conf.d/zz-hyprconf-fido2.conf` — sourced after Omarchy's own (`zz-` sorts last), it swaps the busybox hook set for systemd's (`encrypt`→`sd-encrypt`, `udev`→`systemd`, `keymap`→`sd-vconsole`, `btrfs-overlayfs`→`sd-btrfs-overlayfs` when installed). Omarchy can rewrite its own drop-in on an update without undoing this.
- `/etc/limine-entry-tool.d/zz-hyprconf-fido2.conf` — `KERNEL_CMDLINE[default]+=" rd.luks.name=<UUID>=<mapper> rd.luks.options=<UUID>=fido2-device=auto"`, the way `omarchy-hibernation-setup:131-139` adds `resume=` in that same directory. The mapper name comes from `limine-entry-tool --get-cmdline default` — the cmdline limine actually assembles, which Omarchy asks for the same way (`bin/omarchy-upgrade-to-quattro:537-542`) — cross-checked against the live root, and read back afterwards to prove the drop-in reaches the kernel. `/etc/default/limine` is never edited and keeps `cryptdevice=`, so the box still boots if the hook set ever reverts.

At boot: plug the key in, enter its PIN, touch it; with no key present systemd waits `token-timeout` (30 s) and falls back to the passphrase. No passphrase slot is ever touched. `enroll` refuses a `/etc/vconsole.conf` whose first `XKBLAYOUT` is non-Latin unless `--allow-non-latin-layout` is given (the systemd initramfs always bundles that file, so a Latin passphrase could become untypeable). Read-only snapshot boots keep their writable overlay only where `limine-mkinitcpio-hook` ships `sd-btrfs-overlayfs`; normal boots are unaffected either way.

## Requires
Omarchy (`omarchy-pkg-add`), `systemd-cryptenroll`, `limine-mkinitcpio` and `limine-entry-tool` (both from `limine-mkinitcpio-hook`), a LUKS2 root, and `sudo` plus a terminal **when you run the tool** — installing needs none of that, and no packages. Root writes: the two drop-ins above and a FIDO2 LUKS slot, nothing else.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/yubikey && bash ~/.hyprconf/modules/yubikey/install
```

## Settings
None: every choice is a flag on `enroll` (`--device`, `--yes`, `--no-snapshot`, `--allow-non-latin-layout`), and the module writes no marker.

## Undo
`hyprconf-yubikey remove` **first**, while the tool is still on PATH (`disable` keeps the LUKS slot) — then `bash ~/.hyprconf/modules/yubikey/install undo`, which removes the symlink and nothing else. A box enrolled by hyprconf 4.0.0–4.2.0 has `rd.luks.*` written inline on `/etc/default/limine`, which this tool only reads: `status` names them, `remove` leaves them — delete those two parameters by hand, keep `cryptdevice=`.

## Verified against Omarchy 4.0.3-1
limine-mkinitcpio-hook 1.38.0-1.1, mkinitcpio 41.1, systemd 261. The boot-chain facts and the files they were read from are in the tool's own header; `enroll`/`disable`/`remove` need hardware and are verified by hand, not in the suite.
