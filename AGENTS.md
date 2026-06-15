# Agent Instructions

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full rule set.

Hyprland config reference (syntax cheatsheet): [`docs/hyprland-reference.md`](docs/hyprland-reference.md)

## Project vision (the north star)

hyprconf is an **instantly-deployable, privacy-focused** Arch Linux + Hyprland
system: one command from the ISO to a fully-encrypted, themed, hardened desktop
with no manual post-install steps. Every decision an agent makes must serve this
vision. When a change could be read multiple ways, choose the reading that best
upholds these principles:

1. **Instantly deployable.** A fresh install must produce a complete, working
   system unattended — FDE, bootloader, networking, desktop, theme, firewall,
   and hardening all applied with no follow-up. Every install-time fix must also
   be reproducible by `hyprconf sync` on existing installs (see the sync-patch
   rules below); never strand users on a manual step.

2. **Private by default.** The baseline is hardened without being asked: full-disk
   LUKS2 encryption, hardened resolver (LLMNR/mDNS off) and kernel sysctls,
   telemetry-free Firefox, no inbound SSH on desktops. A change may *add* privacy;
   it must never silently *reduce* it. New network-facing features ship closed
   (opt-in), not open.

3. **Minimal core, bolt-on everything else.** The base install stays lean — only
   what a private desktop needs. Anything heavier or specialised (GPU passthrough,
   dev tooling, a VPN provider's CLI, alternate browsers) is a `hyprconf addon`,
   never forced into the base. Prefer official-repo packages; justify every
   addition to the core `packages` list. If you're unsure whether something
   belongs in the base, it's an addon.

4. **Feature parity with [Omarchy](https://omarchy.org), but leaner and more
   private.** Match its base desktop feature set (unified CLI, theming, firewall,
   sensible defaults) while staying more minimal and more private than it.

5. **Modern privacy, no vendor lock-in.** Ship first-class network privacy:
   provider-agnostic VPN management (`hyprconf vpn` drives any NetworkManager
   OpenVPN/WireGuard profile), an opt-in fail-closed VPN-only kill-switch, and
   privacy-browser options (LibreWolf). Features are pluggable: never hard-wire a
   single vendor (ProtonVPN is *an* option via an addon, not a dependency).

**Decision rule for any new feature:** does it keep the base minimal (or is it an
addon)? does it preserve or improve privacy and ship fail-closed? is it
sync-patchable, documented in the README, and tested? does it avoid vendor
lock-in? If any answer is "no", reshape the change until they're all "yes".

## Repo rules

- **Never commit PII.** No real names, emails, hostnames, IPs, MAC addresses, serial numbers, API keys/tokens, or absolute paths containing the user's home directory (e.g. `/home/<user>`) may appear in tracked files — configs, docs, scripts, or commit messages. Sanitize/genericize before committing, under all circumstances.
