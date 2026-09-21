# yubikey

## What
`hyprconf-yubikey` on PATH (one symlink into `~/.local/bin`). Omarchy's `omarchy-setup-security-fido2` enrols a FIDO2 key for `sudo` and polkit; what it does not do is let the key unlock the encrypted root **at boot**. This is that missing half, on Omarchy's own boot chain — Limine, `limine-mkinitcpio`, mkinitcpio drop-ins, `omarchy snapshot`. Installing changes nothing: the tool is run by hand.

```bash
hyprconf-yubikey status     # devices, token slot, both drop-ins, the assembled kernel cmdline
hyprconf-yubikey enroll     # the whole setup, ending with the passphrase wiped (prompts: passphrase, PIN, touches, the recovery key)
hyprconf-yubikey sudo       # = omarchy-setup-security-fido2 (sudo + polkit)
hyprconf-yubikey disable    # back to Omarchy's boot prompt (it takes the recovery key); the LUKS slots stay
hyprconf-yubikey remove     # set a passphrase again, wipe the FIDO2 slot, then disable
hyprconf-yubikey help       # flags, what each step changes, the limits
```

`enroll` makes the key the only everyday way in. It installs `libfido2` (`omarchy-pkg-add`), takes an `omarchy snapshot create`, enrols the key with `systemd-cryptenroll --fido2-device=auto --fido2-with-client-pin=yes`, proves it opens the volume (`cryptsetup open --test-passphrase --token-only --token-type systemd-fido2`, that token type alone), creates a recovery key unlocked by the key (`--unlock-fido2-device=auto --recovery-key`) and has you type it back against its own keyslot, writes two drop-ins, rebuilds with `limine-mkinitcpio` and only then wipes every passphrase slot (`systemd-cryptenroll --wipe-slot=password`), reading the header back as JSON (`cryptsetup luksDump --dump-json-metadata`, `jq`) to prove the key and the recovery key are what is left. Any failure before the wipe leaves the passphrase working:

- `/etc/mkinitcpio.conf.d/zz-hyprconf-fido2.conf` — sourced after Omarchy's own (`zz-` sorts last), it swaps the busybox hook set for systemd's (`encrypt`→`sd-encrypt`, `udev`→`systemd`, `keymap`→`sd-vconsole`, `btrfs-overlayfs`→`sd-btrfs-overlayfs` when installed). Omarchy can rewrite its own drop-in on an update without undoing this.
- `/etc/limine-entry-tool.d/zz-hyprconf-fido2.conf` — `KERNEL_CMDLINE[default]+=" rd.luks.name=<UUID>=<mapper> rd.luks.options=<UUID>=fido2-device=auto,token-timeout=0"`, the way `omarchy-hibernation-setup:131-139` adds `resume=` in that same directory. The mapper name comes from `limine-entry-tool --get-cmdline default` — the cmdline limine actually assembles, which Omarchy asks for the same way (`bin/omarchy-upgrade-to-quattro:537-542`) — cross-checked against the live root, and read back afterwards to prove the drop-in reaches the kernel. `/etc/default/limine` is never edited and keeps `cryptdevice=`, so the box still boots if the hook set ever reverts.

At boot: plug the key in, enter its PIN, touch it. There is no passphrase prompt: `token-timeout=0` waits for the key for ever (crypttab(5)). Keep the recovery key safe: with the key lost, a live USB's `cryptsetup open <dev> root` takes it, and `hyprconf-yubikey remove` from the unlocked system sets a passphrase again. A box enrolled before 8.2.0 gets the new drop-in, the recovery key and the wipe by re-running `enroll`. `enroll` refuses a `/etc/vconsole.conf` whose first `XKBLAYOUT` is non-Latin unless `--allow-non-latin-layout` is given (the systemd initramfs always bundles that file, so the Latin recovery key could become untypeable where a prompt appears). Read-only snapshot boots keep their writable overlay only where `limine-mkinitcpio-hook` ships `sd-btrfs-overlayfs`; normal boots are unaffected either way.

## Requires
Omarchy (`omarchy-pkg-add`, `jq`), `systemd-cryptenroll`, `limine-mkinitcpio` and `limine-entry-tool` (both from `limine-mkinitcpio-hook`), a LUKS2 root, and `sudo` plus a terminal **when you run the tool** — installing needs none of that, and no packages. Root writes: the two drop-ins above and the LUKS header — a FIDO2 slot and a recovery-key slot added, the passphrase slots wiped (`remove`: one passphrase slot added, the FIDO2 slot wiped) — nothing else.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/yubikey && bash ~/.hyprconf/modules/yubikey/install
```

## Settings
None: every choice is a flag on `enroll` (`--device`, `--yes`, `--no-snapshot`, `--allow-non-latin-layout`), and the module writes no marker.

## Undo
`hyprconf-yubikey remove` **first**, while the tool is still on PATH — it asks for the recovery key and a new passphrase before the key's slot goes (`disable` keeps every LUKS slot, so its boot prompt takes only the recovery key); the recovery key stays until `sudo systemd-cryptenroll --wipe-slot=recovery <dev>` — then `bash ~/.hyprconf/modules/yubikey/install undo`, which removes the symlink and nothing else. `rd.luks.*` written inline on `/etc/default/limine` is only ever read here: `status` names it, `remove` leaves it — delete those parameters by hand, keeping `cryptdevice=`.

## Verified against Omarchy 4.0.4-1
limine-mkinitcpio-hook 1.38.0-1.1, mkinitcpio 41.1, systemd 261. The boot-chain facts and the files they were read from are in the tool's own header; `enroll`/`disable`/`remove` need hardware and are verified by hand, not in the suite; the slot JSON and `--wipe-slot` semantics are cryptsetup 2.8.7's `cryptsetup-luksdump(8)` and systemd 261's `systemd-cryptenroll(1)`.
