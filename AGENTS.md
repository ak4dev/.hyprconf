# Agent Instructions

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for the full rule set.

Hyprland config reference (Lua syntax cheatsheet): [`docs/hyprland-reference.md`](docs/hyprland-reference.md)

Omarchy bar-widget plugin reference (the QML this repo's plugin needs): [`docs/quickshell-reference.md`](docs/quickshell-reference.md) — when touching `plugins/`, re-verify every API against the installed qmltypes (`/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`) and Omarchy's shell sources (`/usr/share/omarchy/shell/`).

Omarchy platform reference (the host system): the installed tree at `/usr/share/omarchy` is authoritative for the version actually running (`omarchy version`), `omarchy commands --json` is the live command surface, and the manual at <https://omarchy.org/manual/> is the published behaviour. Before touching anything in this repo, re-verify against all three — see **Never work from memory about Omarchy** below.

## Project vision (the north star)

hyprconf is a **lean deployment mechanism — `install.sh` plus the shipped
payload — that ports the hyprconf configuration suite's functionality onto a
stock Omarchy install through Omarchy's own tools and seams**: hotkeys,
look'n'feel, monitor presets, bar widgets, shell, theme bridges and `bin/`
tools, disturbing that install as little as possible. Omarchy owns the base
system; hyprconf never competes with it. When a
change could be read multiple ways, choose the reading that best upholds these
principles:

1. **Use Omarchy's own tools.** Every job Omarchy already has a command, seam or
   mechanism for is done through that — see the first repo rule below. A
   hand-rolled replacement is a drift bug, not a feature.

2. **Extend only through documented seams.** A user theme under
   `~/.config/omarchy/themes/`, a shell plugin (or a copy of a built-in one, the
   way `omarchy plugin clone` makes it), a hook under
   `~/.config/omarchy/hooks/*.d/`, an `include` appended to a config Omarchy
   owns (kitty), the `~/.config/hypr/{bindings,input,looknfeel,monitors}.lua`
   files Omarchy `require`s after its defaults, and the "personal configuration"
   tail of `~/.config/hypr/hyprland.lua`. Nothing writes to `/usr/share/omarchy`,
   changes the login shell, or runs `pacman -Syu` / `pacman -R`. The one write
   outside `$HOME` is the system Firefox policy, behind the `--no-packages` gate.

3. **Never work from memory about Omarchy.** Re-derive every claim from the
   running system (rule below).

4. **Idempotent, reversible, set-once for user choices.** Every `install.sh`
   stage re-runs safely and byte-stably; the post-update hook re-applies the
   overlay after every `omarchy-update`, so anything that is a *choice* — font,
   default apps, clock format, workspaces widget, active theme, active
   `monitors.lua` — is applied once (or never) and left to the user from then
   on. Every stage has a stock-restoring undo (`.stock` backups, `omarchy
   plugin disable`, `switch_monitor.sh stock`, managed-block markers).

5. **Private by default.** The Firefox policy ships telemetry off and uBlock
   Origin force-installed; nothing phones home; **official repositories only,
   never the AUR** (rule below). A change may add privacy, never reduce it.

6. **Tests and docs move in lockstep.** Hermetic unit + integration suites, CI
   green, no PII. See the audit principles.

7. **Posture: a personal config shared as-is.** One person's setup, published as
   reference — not a maintained product. Favour removing scaffolding over adding
   it. `web/` is a static page hosted manually on S3.

**Decision rule for any change:** does Omarchy already do it? does it go through
a documented seam? was it verified against the installed Omarchy? is it
idempotent and reversible, and does it leave user choices alone? is it hermetic,
tested, documented in the README, and free of PII and the AUR? If any answer is
"no", reshape the change until they are all "yes".

## Audit principles (the standing bar for every change)

Every change — feature, fix, or refactor — must satisfy **all** of these, **in the
same commit**:

1. **Tests move in lockstep with features.** Adding or changing a stage, flag,
   script, config path, package, hotkey, preset or plugin means adding or
   updating its tests in the same commit, in the right suite (`unit` /
   `integration`). When a change intentionally alters behaviour, update
   the affected test to assert the **new** contract and say so in the commit
   message — never silently weaken, delete or loosen a test to get a green run.
   Run `make test` before every commit.

2. **Docs move in lockstep too.** `README.md` and this file keep 1:1 parity with
   the code — every stage, flag, package, hotkey, preset, plugin id and path.
   Doc drift is a correctness bug. `web/index.html` is a hand-maintained
   static reflection, not a mirror.

3. **Tests stay hermetic.** Both suites must pass in a minimal `archlinux:latest`
   container as root — no running Hyprland or Omarchy shell, no host tool that
   touches the desktop, no real `$HOME`, no ambient state, never mutating the
   container. Make every
   system path env-overridable (`: "${_VAR:=/default}"`, never `readonly`) and
   point it at a `tmp_path`. Every command that could touch the desktop or
   the system — `omarchy-*`, `hyprctl`, `sudo`, `chsh`, `fc-list`,
   `systemd-cryptenroll`, `limine-update` … — is **always** a fake bin first
   on `PATH` (the suite once put a notification on the owner's desktop).
   Pure tools are real when present and the test skips otherwise: `jq`,
   `luac`, `cp`, `python3`, `shellcheck`, and `git` for `init`/`add`/
   `commit`/`checkout` inside a throwaway clone (`clone` and `pull` stay
   stubbed — never the network, never the real repository).

4. **Restraint invariants never regress.** Never `chsh`; never rewrite
   Omarchy's `kitty.conf` beyond the one `include`; never point
   `omarchy-default-terminal` at a terminal that is not installed (it checks
   nothing — `stage_terminal` asserts kitty first); never `pacman -Syu` /
   `pacman -R`; never switch the active theme; never overwrite a seeded preset;
   never re-assert a set-once choice; never write outside `$HOME` except the
   Firefox policy. `tests/unit/test_omarchy_install.py` asserts these.

5. **Hygiene.** `shellcheck` and `ruff` clean; no dead code; no committed
   artefacts; no PII. Favour deleting over adding: every line ships to a user's
   `$HOME`, so anything not needed to deploy the overlay goes.

6. **GitHub CI must always be green.** Every push must leave
   `.github/workflows/test.yml` passing. Before pushing run `make lint`,
   `make shellcheck` and `make test` locally. CI runs as **root** in the
   container, and root bypasses DAC checks — gate any `[[ -r ]]`/`os.access`
   logic on the euid and reproduce with `unshare -r python -m pytest …`. Never
   promote `omarchy` → `stable` while any workflow is red.

## Repo rules

- **ALWAYS use Omarchy's own config tools and binaries when possible.** Before
  writing any custom mechanism — a script, a config edit, a file copy — check
  whether Omarchy already ships a command or seam that does the job
  (`omarchy commands --json`, `/usr/share/omarchy/bin/`, `omarchy bar set`,
  `omarchy-pkg-add`, themes, shell plugins and `omarchy plugin clone`, hooks
  under `~/.config/omarchy/hooks/*.d/`) and use that instead. A hand-rolled
  replacement for something Omarchy already does is a drift bug: it bypasses
  Omarchy's own state, OSDs and migrations, and breaks on its next release.
  A custom path is acceptable only where Omarchy demonstrably has no tool for
  the job, and the code comment must say so, citing what was checked.

- **Never work from memory about Omarchy — check the running system and the current docs before every change.** This repo sits on a system it does not own and cannot pin: Omarchy ships breaking changes between releases, and every assumption about its files, commands, defaults or seams is a drift bug waiting to happen. An "obvious" fact about Omarchy that was true when a doc was written is not evidence. Before writing, reviewing or reasoning about anything in this repo:

  1. **Read the installed source.** `/usr/share/omarchy/` is authoritative for the version this machine runs (`omarchy version`, `/usr/share/omarchy/version`): `default/hypr/*.lua` for the Hyprland defaults the overlay layers onto, `config/` for the templates a fresh `$HOME` is seeded from, `bin/` for what a command actually does (`cat "$(which omarchy-theme-set)"`) including its guards and its exit codes, `shell/` for the Quickshell plugin contract. Read it freely; **never edit it** — the omarchy package owns it and an update overwrites it.
  2. **Enumerate from the machine, never from memory.** `omarchy commands --json` lists every route with its group, args, aliases and `requires_sudo`. Use it to confirm a command exists and takes the arguments you think it does, and prefer the documented `omarchy <group> <action>` form over the underlying `omarchy-*` binary. Where the overlay needs a list of Omarchy's commands, themes, plugins, fonts or presets, **derive it at runtime from those commands** rather than hard-coding a snapshot — a generated list tracks Omarchy, a literal one rots.
  3. **Re-verify against the published manual** at <https://omarchy.org/manual/> whenever a change touches user-facing behaviour or a documented seam — Monitors, Keyboard/Mouse/Trackpad, Themes, Hotkeys, Shell Plugins, Toggles/Idle/Screensaver, Omarchy CLI, Dotfiles and Common tweaks are the chapters the overlay overlaps.
  4. **Record what you checked.** Name the Omarchy version the change was verified against in the commit message, and cite the specific file or command that justifies each claim about Omarchy's behaviour, the way the existing comments do (`omarchy-default-terminal` checking nothing before it writes `~/.config/xdg-terminals.list`; `omarchy-theme-update` skipping a symlinked theme dir — its `[[ ! -L ]]` guards `git pull` — while `omarchy-theme-set`'s `-d` test and `cp -r` follow the link, which is why a symlinked user theme works; the ALPM AbortOnFail hook; `omarchy-refresh-config`'s `cp -f` through a symlink). A claim about Omarchy with no traceable source is not verified.

  This binds documentation and review as much as code: a "fix" premised on stale knowledge of Omarchy is a regression even when the diff looks right.

- **Avoid the AUR at all costs — and never install from it without asking first.** Official repositories only. Every package this project installs automatically, on any code path (`install.sh`, `packages`, or anything added later), must come from an official Arch repository. If a feature appears to require an AUR package, **stop and raise it with the user, and verify the package, before implementing anything** — do not add it, do not add an AUR helper call, and do not quietly pick an AUR-only dependency to make a feature work. AUR packages remain something the user installs manually, by choice.

  This binds the overlay deliberately: Omarchy ships `yay`, uses the AUR itself, and exposes `omarchy-pkg-aur-add`. Its availability is not permission to use it — hyprconf does not reach for the AUR just because the host platform does. Enforced by the scans in `tests/unit/test_omarchy_install.py` (no `yay`, no `makepkg`, no `omarchy-pkg-aur-add`).

- **Never commit PII.** No real names, emails, hostnames, IPs, MAC addresses, serial numbers, API keys/tokens, or absolute paths containing the user's home directory (e.g. `/home/<user>`) may appear in tracked files — configs, docs, scripts, or commit messages. Use a placeholder (`testuser`, `/home/$USER`, `~`) even in test fixtures. Enforced across **every tracked file** by `tests/unit/test_no_pii.py`, which derives the identities to search for — login name, home directory name, hostname, git email — from the environment at runtime, so the guard itself never has to name them. This is also why plugin copies use the `hyprconf.*` id namespace rather than `omarchy plugin clone`'s `<username>.<id>`.

- **The hypr override files are symlinks into the checkout, and `omarchy refresh` writes through them.** `omarchy refresh config hypr/<file>` and `omarchy refresh hyprland` `cp -f` Omarchy's template onto `~/.config/hypr/<file>` — which is a link into `hypr/` here — so the checkout's file becomes the stock template (observed on Omarchy 4.0.0). `install.sh` restores such a file from git when it is byte-identical to the template and reports a preset reset to the stock `monitors.lua` template (Omarchy's own `.bak.<epoch>` holds the user's copy). Keep the symlinks (the Omarchy manual's dotfiles chapter recommends stow-style links) and keep the guard.

- **The web frontend is a static page, not an app.** `web/` is a single self-contained `web/index.html` (plus `CNAME` and image assets) — no React, build step, test suite, or bundler, and no external CDN/font requests (privacy). It exists so others can see what the project is: a static reflection of the README, framed impersonally ("a personal Hyprland setup, shared as-is"). Do not reintroduce a framework, a build, or tests, and do not grow it into a docs app.

- **Hosting is the existing AWS S3 + CloudFront — kept, but managed manually.** The static page lives in the `hyprconf-sh` S3 bucket behind a CloudFront distribution. There is no deploy machinery in the repo: update the live site manually (`aws s3 cp web/… s3://hyprconf-sh/` + a CloudFront invalidation). `scripts/publish` is lint + test → promote `omarchy` to `stable` (no deploy step). Do **not** rebuild a CDK app, a deploy CLI, or a React frontend; `infra/` holds only the system Firefox policy.

- **Posture: a personal config shared as-is.** This is one person's daily-driver setup, published as reference and inspiration — not a maintained product. Favor removing scaffolding over adding it; there is no support or feature-request obligation.
