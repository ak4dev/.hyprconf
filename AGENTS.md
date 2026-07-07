# Agent Instructions

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full rule set.

Hyprland config reference (syntax cheatsheet): [`docs/hyprland-reference.md`](docs/hyprland-reference.md)

Quickshell API reference (bar/QML cheatsheet): [`docs/quickshell-reference.md`](docs/quickshell-reference.md) — when touching `stow/quickshell/`, always re-verify APIs against the quickshell.org docs for the **installed** version (see the Quickshell Documentation section of the copilot instructions).

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

## Audit principles (the standing bar for every change)

These are the invariants the project is continuously audited against. Every change
— feature, fix, or refactor — must satisfy **all** of them, **in the same commit**,
and future work must keep them true automatically. The full rule set lives in
[`.github/copilot-instructions.md`](.github/copilot-instructions.md); these are the
non-negotiables:

1. **Tests move in lockstep with features.** Adding or changing a feature (CLI
   subcommand, flag, script, config path, package, addon) means adding or updating
   its tests in the *same* commit, in the correct tier (`unit` / `integration` /
   `tui` / `vm` / `install`). When a change intentionally alters behaviour, update
   the affected test to assert the **new** contract and say so in the commit
   message — never silently weaken, delete, or loosen a test just to get a green
   run. A feature without a test is unfinished. Run `make test` before every commit.

2. **Docs move in lockstep too.** `README.md` and this file keep 1:1 parity with
   the code — every command, flag, subcommand, package, keybind, and theme.
   Adding or renaming one means updating both in the same commit. Treat doc drift
   as a correctness bug, not a follow-up. The web frontend (`web/index.html`) is a
   hand-maintained static reflection of the README, **not** a 1:1 mirror — keep its
   high-level claims (feature list, theme count, install command) honest, but it
   need not enumerate every command.

3. **Unit/integration tests stay hermetic.** They must pass in a minimal
   `archlinux:latest` CI container — no running Hyprland session, no real
   hardware, no host tools, no ambient state, and never mutating the container
   (don't shell out to `pacman`). No reading/writing real system paths. Make
   system paths env-overridable (`: "${_VAR:=/default}"`, never `readonly`) and
   point them at a `tmp_path`; stub external commands via a fake-bins `PATH`.
   Anything needing a live session/hardware goes in the `vm`/`install` tier.

4. **Security invariants never regress.** Ship fail-closed (new network features
   opt-in); keep the lock screen (hyprlock) and a real install's LUKS
   **password-only**; never weaken sshd; pass secrets via stdin, never argv; leave
   no `NOPASSWD`/keyfile/secret artifact behind; `udev RUN+=` only ever targets a
   root-owned path; escape user-controlled values embedded in generated
   JSON/config; harden conservatively (never break the browser sandbox or the VPN).

5. **Hygiene & consistency.** `shellcheck` and `ruff` (pyflakes/bugbear) stay
   clean; no dead code; no committed build artifacts; install-time fixes stay
   `hyprconf sync`-patchable; addons follow the five-function pattern.

6. **Thin bash, logic in Python — don't grow the monoliths.** The bash `hyprconf`
   is a dispatcher + system-orchestration layer; config-editing logic (the option
   schema, get/set/configure, validation) lives in the tested Python library
   (`stow/hypr/.local/lib/hyprconf/`, dispatched via `cli.py`). Add new config logic
   there and have bash delegate (`python3 "$CLI_LIB/cli.py" <cmd>`) — never a new
   inline `python3 -c`/heredoc or a second copy of the schema (`schema.py` is the
   single source of truth). The large files (`hyprconf`, `switch_theme.py`,
   `gpu-passthrough.sh`) must not grow; when you touch one, extract a bounded,
   tested module rather than adding to it.

## Repo rules

- **Never commit PII.** No real names, emails, hostnames, IPs, MAC addresses, serial numbers, API keys/tokens, or absolute paths containing the user's home directory (e.g. `/home/<user>`) may appear in tracked files — configs, docs, scripts, or commit messages. Sanitize/genericize before committing, under all circumstances.

- **The web frontend is a static page, not an app.** `web/` is a single self-contained `web/index.html` (plus `CNAME` and image assets) — no React, build step, test suite, or bundler, and no external CDN/font requests (privacy). It exists so others can see what the project is: a static reflection of the README, framed impersonally ("a personal Hyprland setup, shared as-is"). Do not reintroduce a framework, a build, or tests, and do not grow it into a docs app.

- **Hosting is the existing AWS S3 + CloudFront — kept, but managed manually.** The static page lives in the `hyprconf-sh` S3 bucket behind a CloudFront distribution whose UA-router function serves `install.sh` to `curl`/`wget` and the page to browsers — that is what makes `bash <(curl -fsSL hyprconf.sh)` work. What was removed is the *deploy machinery*: the CDK app (`infra/cdk/`), the `hyprconf deploy`/`teardown` commands, and `web/deploy.sh`. Update the live site manually (`aws s3 cp web/… s3://hyprconf-sh/` + a CloudFront invalidation). `scripts/publish` is lint + test → promote dev to stable (no deploy step). Do **not** rebuild the CDK app, a deploy CLI, or a React frontend; `infra/` holds only the system Firefox policy.

- **Posture: a personal config shared as-is.** This is one person's daily-driver setup, published as reference and inspiration — not a maintained product. Favor removing scaffolding over adding it; there is no support or feature-request obligation.
