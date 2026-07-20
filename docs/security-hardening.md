# Security hardening

This documents the hardening hyprconf applies automatically and the hands-on
steps that require your YubiKey and a reboot to validate (so they are deliberately
**not** run unattended).

## Applied automatically (every install + `setup.sh --sync`)

| Area | What | Where |
|---|---|---|
| **Power udev rule (root LPE fix)** | The AC-change udev rule now executes a **root-owned** copy at `/usr/local/lib/hyprconf/hyprconf-power-monitor`, never a `$HOME` path. A stale rule pointing into `/home` is migrated on sync. | `setup.sh:setup_power_monitor` |
| **Idle → power off on battery** | hypridle powers the machine **off** after 60 min idle on battery (RAM keys flushed, disk re-encrypted at rest) and suspends on AC. | `hypridle.conf` + `hyprconf-idle-action` |
| **Kernel sysctls** | `kptr_restrict`, `dmesg_restrict`, `yama.ptrace_scope=1`, unprivileged BPF off, BPF JIT hardening, TTY ldisc autoload off, rp_filter, ICMP-redirect off. | `/etc/sysctl.d/90-hyprconf-hardening.conf` |
| **Resolver** | LLMNR + mDNS responders disabled. | `/etc/systemd/resolved.conf.d/90-hyprconf-hardening.conf` |
| **Screen-locker PAM shields** | Every installed locker (`hyprlock`, and COSMIC's `cosmic-greeter`) gets a password-only `system-auth` stack. A missing file would fall through to `/etc/pam.d/other` (`pam_deny`); an inherited `pam_u2f` would return `PAM_AUTHINFO_UNAVAIL` because the locker runs as your user and cannot read the `0640 root:root` authfile. Either way the screen could never be unlocked. Corrected on sync, so a locker installed later is repaired automatically. | `setup.sh:ensure_locker_pam` |
| **Browser** | Firefox hardened via an enterprise `policies.json` (telemetry/studies/Pocket off, uBlock Origin force-installed) plus a `user.js` reapplied on every theme switch. | `/etc/firefox/policies/policies.json` + profile `user.js` |

All are reversible — delete the drop-in file (or revert the rule) and re-sync.

For a privacy-focused browser beyond hardened Firefox, install **LibreWolf** (a
Firefox fork with RFP and telemetry stripped) manually from the AUR: `yay -S
librewolf-bin`. It is auto-themed by the same engine; hyprconf applies only
theme prefs to it, leaving LibreWolf's own hardening untouched.

### Opt-in: disable unprivileged user namespaces

`90-hyprconf-hardening.conf` ships two commented lines:

```
#kernel.unprivileged_userns_clone = 0
#user.max_user_namespaces = 0
```

Uncommenting them blocks a large class of kernel privilege-escalation bugs but
**breaks Flatpak and the Chromium/Chrome sandbox**. Enable only if you don't use
those, then `sudo sysctl --system`.

### Tuning the idle behaviour

`hyprconf-idle-action` takes `auto | poweroff-if-battery | suspend-if-ac | status`.
Edit the timeouts in `~/.config/hypr/hypridle.conf`. To **hibernate instead of
power off** (keeps your session, still flushes RAM keys), set up encrypted swap
≥ RAM inside the LUKS container, add the `resume` hook + `resume=` kernel param,
then replace `poweroff` with `systemctl hibernate` in `hyprconf-idle-action`.

---

## VPN-only mode (kill-switch)

`hyprconf-vpn` drives any VPN profile NetworkManager manages — OpenVPN (via the
core `networkmanager-openvpn` plugin) or WireGuard — provider-agnostically:

```
hyprconf-vpn status [--json]     # connection + kill-switch state (the bar reads --json)
hyprconf-vpn import <file>       # .ovpn → OpenVPN, .conf → WireGuard
hyprconf-vpn connect [name]      # defaults to the only profile if just one
hyprconf-vpn killswitch on|off|status
```

`killswitch on` enforces **fail-closed, VPN-only networking** — if the tunnel
drops, traffic is blocked rather than leaking onto the clear net. Two backends,
chosen automatically:

- **ProtonVPN** (manual AUR install: `yay -S proton-vpn-cli`): delegates to
  Proton's own maintained kill-switch (`protonvpn config set kill-switch
  standard`), which also covers DNS and re-connection.
- **Generic** (any other NM VPN): a self-contained nftables table
  `inet hyprconf_killswitch` hooked at `output priority -10` (so it drops before
  ufw's chains ever see the packet). Policy `drop`, with explicit accepts for
  loopback, `ct state established,related` (keeps a live tunnel + its control
  channel up), the VPN tunnel device (`tun0`/`wg0`), the local LAN + DHCP, and
  the detected VPN server endpoint(s) so the tunnel can re-establish. The
  ruleset is written to `/etc/hyprconf/killswitch.nft`.

Notes:

- The generic table is **session-scoped** — it is not auto-loaded at boot (a
  mis-set kill-switch must never strand a machine with no network). To make it
  persist, wire `/etc/hyprconf/killswitch.nft` into `nftables.service`.
- `hyprconf-vpn status` reports `Kill-switch: ON … no VPN up — traffic is
  fail-closed` so the blocked-and-disconnected state is unambiguous.
- Turn it off with `hyprconf-vpn killswitch off` (removes the table / unsets the
  Proton setting).

---

## Hands-on: key-only LUKS (remove the passphrase fallback)

By default the disk unlocks with the YubiKey **or** the original passphrase — and
that passphrase is, by installer default, your login password. So the disk is only
as strong as that one reused secret. To make the disk **key-only**:

```
yubikey-fido2-setup harden-luks
```

It refuses unless a FIDO2 slot already exists, **enrolls an offline recovery key
first** and makes you acknowledge saving it, pushes you to register a **backup
YubiKey**, and only then wipes the passphrase slot. Afterwards:

- Unlock = YubiKey + PIN, or the recovery key at the prompt.
- **Store the recovery key offline** (password manager / paper in a safe) and keep
  a **second enrolled YubiKey** — losing your only key without these = data loss.
- Verify by rebooting **before** you rely on it: the YubiKey unlocks; the old
  passphrase no longer does.

Check slots any time: `sudo systemd-cryptenroll /dev/nvme0n1p2`.

---

## Close the Evil-Maid gap (Secure Boot + signed UKI): `hyprconf-secureboot`

**A YubiKey LUKS unlock does not, by itself, stop this.** Two separate bypasses:

1. **Boot-chain tampering.** `/boot` is an unencrypted ESP and the initramfs is
   unsigned, so someone with brief physical access can trojan it to capture the
   unwrapped **LUKS master key** the next time *you* unlock — your FIDO2 PIN and
   touch don't help, you hand them to what looks like a normal boot. Once they have
   the master key they never need your YubiKey again.
2. **The coexisting passphrase slot.** The installer sets the LUKS passphrase equal
   to your login password and keeps it as a slot, so an attacker can ignore the
   YubiKey and brute-force that weaker, reused slot offline.

The fix is **layered** — all three together, because each closes a different hole:

| Layer | Closes | Command |
|-------|--------|---------|
| Secure Boot + **signed UKI** (kernel+initramfs+cmdline as one signed EFI binary) | boot-chain tampering | `hyprconf-secureboot setup` |
| **Firmware admin password** + locked boot menu | someone just disabling Secure Boot | *(manual, in UEFI)* → `hyprconf-secureboot ack-firmware-password` |
| **Key-only LUKS** (FIDO2 + recovery key, no passphrase) | the weak passphrase slot | `hyprconf-secureboot harden` |

> Keep the passphrase/recovery key working until you've tested a reboot, and ideally
> rehearse in a VM — a signing/firmware mistake can leave the machine unbootable. If
> a boot fails, **disable Secure Boot in firmware to recover** (the UKI still boots
> with SB off), fix, and re-sign.

### Automated flow

```
sudo hyprconf-secureboot setup     # installs sbctl, converts to a signed UKI,
                                   # creates+signs keys, verifies, installs a
                                   # pacman verify hook, and enrolls keys if the
                                   # firmware is already in Setup Mode
```

`setup` is idempotent and refuses to enroll keys unless `sbctl verify` is clean
(enrolling over an unsigned chain would brick the next Secure-Boot-on boot). It
picks a **key policy** automatically — own-keys-only where safe, or keeps Microsoft
keys (`--microsoft`) when a discrete GPU / option-ROM-dependent firmware is detected
— and you can force either with `--own-keys-only` / `--microsoft`.

Then finish the two **irreducibly manual** steps in your UEFI menu — software can't
do these — and verify:

1. Set an **Administrator/Supervisor password** and lock the one-time boot menu /
   disable USB boot (a setup password alone often still allows F12 boot). Then
   `hyprconf-secureboot ack-firmware-password`.
2. Set **Secure Boot → Enabled** (and, if `setup` couldn't enroll, first enter Setup
   Mode and run `hyprconf-secureboot enroll`).
3. Back in Linux: `hyprconf-secureboot status` → expect `Secure Boot: enabled` and
   `sbctl verify: clean`. `hyprconf-secureboot status` reports if SB is later turned off.

It **stays** signed across `linux` / `systemd` / `sbctl` upgrades: every binary is
tracked with `sbctl sign -s`, so sbctl's own pacman hook re-signs it, and a
hyprconf verify hook warns loudly if anything ends up unsigned.

### Optional: TPM2 measured-boot binding

`hyprconf-secureboot tpm-bind` binds LUKS unlock to the TPM so the disk only unlocks
on an unmodified boot chain. **FIDO2 remains the default factor** (the TPM is never
in the FIDO2 path). Note PCR 11 (the UKI measurement) changes on every kernel
update, so plain `7+11` must be **re-enrolled each update**; PCR 7 + PIN is stable
and recommended. A PIN blocks auto-unlock if the machine is stolen powered-off.

### What this does *not* cover

Secure Boot is a signature gate, not a complete defense. Residual, out of scope:
**DMA** (Thunderbolt/PCILeech) and **cold-boot** RAM extraction of the master key
(mitigate with IOMMU/kernel DMA protection and preferring poweroff/hibernate over
suspend); **rollback** to an old, validly-signed UKI; and a **fully compromised
running OS** (root can read the master key and the sbctl keys). If you kept Microsoft
keys, also keep the firmware's **DBX** revocation list current via `fwupdmgr`.

---

## Notes / residual items

- **Root account is locked (admin is sudo-only):** the full-disk installer sets the
  single password on the **user account + LUKS only** and runs `passwd -l root`, so
  there is no separate root credential to reuse, guess, or leak. Admin is done via
  `sudo` (the user is in `wheel`). Trade-off: single-user/`rescue.target` mode uses
  `sulogin`, which refuses a locked root — so recover a broken `sudoers`/PAM (or a
  lost YubiKey once `pam_u2f` guards sudo) from the **Arch live USB + `arch-chroot`**,
  not on-machine rescue. This is sharper under Secure Boot: the signed-UKI cmdline
  can't be edited at the boot menu, so live-USB recovery is the only path. Still want
  an on-machine root? `sudo passwd -u root && sudo passwd root` re-enables it.
  The install password is still shared between the user login and LUKS; `harden-luks`
  removes the disk side of that reuse.
- **`curl | bash` install trust:** the installer is unsigned. Until a published
  signature exists, prefer cloning the repo, reading `install.sh`/`setup.sh`, and
  running them locally over piping the URL straight to a shell.
- **What hardening does *not* cover:** anything that already runs code as your user
  (malicious AUR/pip/npm deps, browser RCE). `ptrace_scope=1` and the root-owned
  power rule blunt the blast radius, but the primary defense remains not running
  untrusted code as your user.
