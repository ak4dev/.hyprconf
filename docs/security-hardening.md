# Security hardening

This documents the hardening hyprconf applies automatically and the hands-on
steps that require your YubiKey and a reboot to validate (so they are deliberately
**not** run unattended).

## Applied automatically (every install + `hyprconf sync`)

| Area | What | Where |
|---|---|---|
| **Power udev rule (root LPE fix)** | The AC-change udev rule now executes a **root-owned** copy at `/usr/local/lib/hyprconf/hyprconf-power-monitor`, never a `$HOME` path. A stale rule pointing into `/home` is migrated on sync. | `setup.sh:setup_power_monitor` |
| **Idle → power off on battery** | hypridle powers the machine **off** after 60 min idle on battery (RAM keys flushed, disk re-encrypted at rest) and suspends on AC. | `hypridle.conf` + `hyprconf-idle-action` |
| **Kernel sysctls** | `kptr_restrict`, `dmesg_restrict`, `yama.ptrace_scope=1`, unprivileged BPF off, BPF JIT hardening, TTY ldisc autoload off, rp_filter, ICMP-redirect off. | `/etc/sysctl.d/90-hyprconf-hardening.conf` |
| **Resolver** | LLMNR + mDNS responders disabled. | `/etc/systemd/resolved.conf.d/90-hyprconf-hardening.conf` |

All are reversible — delete the drop-in file (or revert the rule) and re-sync.

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

## Hands-on: key-only LUKS (remove the passphrase fallback)

By default the disk unlocks with the YubiKey **or** the original passphrase — and
that passphrase is, by installer default, your login password. So the disk is only
as strong as that one reused secret. To make the disk **key-only**:

```
hyprconf yubikey harden-luks
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

## Hands-on: close the Evil-Maid gap (Secure Boot + signed UKI)

Neither key-only LUKS nor idle-poweroff fixes this: `/boot` is an unencrypted ESP
and Secure Boot is off, so someone with brief physical access can tamper with the
kernel/initramfs and capture your data the next time *you* unlock. The fix is a
**signed Unified Kernel Image** (kernel + initramfs + cmdline as one signed EFI
binary) under **Secure Boot**.

> Do this with the passphrase/recovery key still working, and ideally rehearse in a
> VM first — a signing/firmware mistake can leave the machine unbootable.

1. Put the firmware in **Setup Mode** (clear the platform key in the UEFI menu).
2. Keys + enrollment:
   ```
   sudo pacman -S sbctl
   sudo sbctl create-keys
   sudo sbctl enroll-keys -m          # -m keeps Microsoft keys (needed by some firmware/dGPUs)
   ```
3. Build a **UKI** via mkinitcpio: in `/etc/mkinitcpio.d/linux.preset` set an
   `_uki=` output path under the ESP and drop the separate `_image=`, then
   `sudo mkinitcpio -P`. Put the kernel cmdline in `/etc/kernel/cmdline`.
4. Point a systemd-boot entry at the UKI (or boot the UKI directly), then sign it:
   ```
   sudo sbctl sign -s /boot/EFI/Linux/arch-linux.efi
   sudo sbctl sign -s /boot/EFI/systemd/systemd-bootx64.efi
   sudo sbctl sign -s /boot/EFI/BOOT/BOOTX64.EFI
   sudo sbctl verify
   ```
5. Reboot, enable Secure Boot in the firmware, confirm `bootctl status` shows
   `Secure Boot: enabled` and `sbctl status` is good.
6. (Best) bind LUKS to the **TPM2 with a PCR policy** so the disk only unlocks on
   an unmodified boot chain: `sudo systemd-cryptenroll --tpm2-device=auto
   --tpm2-pcrs=7+11 /dev/nvme0n1p2` (keep the YubiKey + recovery key enrolled).

---

## Notes / residual items

- **Password reuse (installer default):** the full-disk installer still sets
  `user == root == LUKS` to one password and does not lock root — left as-is to
  preserve emergency-mode recovery and CI. `harden-luks` removes the disk side of
  the reuse; if you want distinct secrets, set a separate root password
  (`sudo passwd root`) and change your login password so it differs from the LUKS
  recovery key.
- **`curl | bash` install trust:** the installer is unsigned. Until a published
  signature exists, prefer cloning the repo, reading `install.sh`/`setup.sh`, and
  running them locally over piping the URL straight to a shell.
- **What hardening does *not* cover:** anything that already runs code as your user
  (malicious AUR/pip/npm deps, browser RCE). `ptrace_scope=1` and the root-owned
  power rule blunt the blast radius, but the primary defense remains not running
  untrusted code as your user.
