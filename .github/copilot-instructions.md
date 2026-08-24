# AI Agent Instructions

hyprconf is an **overlay for [Omarchy](https://omarchy.org)**: `install.sh` layers
hyprconf's hotkeys, look'n'feel, monitor presets, bar widgets, shell and
configuration TUI onto a stock Omarchy install, always through Omarchy's own
tools and documented seams, and disturbs it as little as possible. The north
star and the binding repo rules live in [`AGENTS.md`](../AGENTS.md); this file
is the working rule set.

## Hyprland Documentation

When making any Hyprland configuration change, consult these resources in order:

1. **`docs/hyprland-reference.md`** (this repo) — curated cheatsheet of the Lua config syntax in active use: `hl.config`, `hl.monitor`, `hl.bind`/`o.bind`, window/workspace rules, animations, gestures, and the `hyprctl` forms that still work on Hyprland 0.56.
2. **The installed build's own stubs** — `/usr/share/hypr/stubs/hl.meta.lua` (the `hl.*` API for the running version) and `/usr/share/hypr/hyprland.lua` (the example config). More reliable than the wiki, whose Lua pages are JS-rendered.
3. **Hyprland wiki** — <https://wiki.hypr.land> — authoritative and always up to date. Key sections:
   - Monitors: <https://wiki.hypr.land/Configuring/Basics/Monitors/>
   - Variables: <https://wiki.hypr.land/Configuring/Basics/Variables/>
   - Binds: <https://wiki.hypr.land/Configuring/Basics/Binds/>
   - Window Rules: <https://wiki.hypr.land/Configuring/Basics/Window-Rules/>
   - Animations: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/>
   - hyprctl: <https://wiki.hypr.land/Configuring/Advanced-and-Cool/Using-hyprctl/>

**When adding syntax not covered in `docs/hyprland-reference.md`**, add a concise example to the appropriate section in that file.

---

## Omarchy Documentation

This whole repository runs on a machine it does not own and cannot pin: Omarchy ships breaking changes between releases, so **never work from memory or training data** — every assumption about its files, commands, defaults or seams must be re-derived from the system in front of you, in this order:

1. **The installed tree** — `/usr/share/omarchy/`, authoritative for the version actually running (`omarchy version`, `/usr/share/omarchy/version`). Read it freely; **never edit it** (the package owns it, and an update overwrites it):
   - `default/hypr/*.lua` — the Hyprland defaults the overlay layers onto (`helpers.lua` defines `o.bind`; `bindings/*.lua` shows which keys Omarchy binds, and which by **keycode**). Diff against these before adding a setting: restating a value Omarchy already sets creates drift the moment it retunes the default.
   - `config/` — the templates a fresh `$HOME` is seeded from (`omarchy refresh config <path>` re-copies one — **through a symlink**, see Known Quirks).
   - `bin/` — what a command really does, guards and exit codes included: `cat "$(which omarchy-theme-set)"`. Several are booby-trapped for non-interactive callers (`omarchy-default-terminal` exec()s a GUI window when the terminal is missing; `omarchy-install-terminal` prints a failure and exits 0).
   - `shell/` — the Quickshell shell: `Ui/BarWidget.qml` (the base every bar widget extends), `plugins/README.md` and `README.md` (the manifest contract), `services/PluginRegistry.qml` (`clonedFrom` resolution), `plugins/bar/widgets/` and `plugins/panels/clock/` (the widgets `install.sh` copies and patches).
2. **The live command surface** — `omarchy commands --json` lists every route with its group, args, aliases and `requires_sudo`; `omarchy <group> --help` documents one. Confirm a command exists and takes the arguments you think it does before calling it, and prefer the documented `omarchy <group> <action>` form over the underlying `omarchy-*` binary. Where the overlay needs a list of Omarchy's commands, themes, plugins, fonts or presets, **generate it at runtime from those commands** — a derived list tracks Omarchy, a hard-coded one rots.
3. **The manual** — <https://omarchy.org/manual/> — for user-facing behaviour and documented seams. The chapters the overlay overlaps: Monitors, Keyboard/Mouse/Trackpad, Themes, Making your own theme, Hotkeys, Shell Plugins, Toggles/Idle/Screensaver, Omarchy CLI, Backgrounds, Fonts, Dotfiles, Common tweaks, Updates.

**Extend only through documented seams** — a user theme, a shell plugin (or a copy of a built-in one, the way `omarchy plugin clone` makes it), a `~/.config/omarchy/hooks/*.d/` hook, an `include` appended to a config Omarchy owns, or one of the `~/.config/hypr/*.lua` files Omarchy `require`s *after* its defaults (`hyprland.lua`'s own "personal configuration" tail included). Nothing may write to `/usr/share/omarchy`, change the login shell, or run `pacman -Syu`/`pacman -R` (an ALPM AbortOnFail hook blocks sysupgrade forms, and the "foreign" set includes Omarchy itself). The one sanctioned write outside `$HOME` is the system Firefox policy (`/etc/firefox/policies/policies.json`) — Firefox reads enterprise policies only from root-owned paths; the stage sits behind the `--no-packages` gate beside the only other sudo and never runs without a terminal to take the password prompt. Nothing else touches `/etc`.

**Record what you verified.** Name the Omarchy version a change was checked against in the commit message, and cite the file or command backing each claim about Omarchy's behaviour — as the existing comments do. A claim with no traceable source is not verified, and a fix premised on stale knowledge is a regression even when the diff looks right.

---

## README

**`README.md` is the primary source of truth for any AI agent working on this project.** Inaccurate README content means flawed context for every future agent — treat drift as a correctness bug, not a documentation gap.

**The README must maintain 1:1 parity with the code.** Every installer stage, flag, package, hotkey, monitor preset, plugin id, TUI section, persistence path and behavioural detail that exists must be accurately reflected; nothing may appear in the README that no longer exists in the code.

**Any change must include a README review as a non-optional step.** Before committing, grep `README.md` for content related to what you changed and update anything that describes the old behaviour. Triggers (illustrative, not exhaustive):

- Adding, removing, or renaming packages in `packages`
- Adding, changing, or removing hotkeys in `hypr/bindings.lua`
- Adding or changing a monitor preset (`hypr/pcMonitors.<name>.lua`, `hypr/laptopMonitors.lua`) or `hypr/scripts/switch_monitor.sh`
- Adding, reordering, or changing an `install.sh` stage, flag, marker or path
- Adding or removing a TUI section, a persistence path, or a live-apply mechanism
- Adding or changing a plugin under `plugins/` or a widget copy `install.sh` makes
- Changing `hypr/looknfeel.lua` / `hypr/input.lua` deltas, `zsh/zshrc.block`, `kitty/hyprconf.conf`, or the hook

**Keep the README concise.** Every section must earn its place. Prefer tables and code blocks over narrative.

**Never alter the hyprconf branding block** (banner SVG + badges) at the top of `README.md`.

---

## Continuous Integration (must always be green)

Every push (and PR) to any branch triggers `.github/workflows/test.yml`: three jobs
in an `archlinux:latest` container — **Lint** (`make shellcheck` + `make lint`),
**Unit + Integration** (tiers 1-2, with `--cov=lib/hyprconf`), and **TUI**
(tier 3). All three must pass on **every** commit; a red run on `omarchy` or
`stable` is a release blocker, and `omarchy` must never be promoted to `stable`
while any workflow is red.

Reproduce CI locally before every push:

```bash
make lint && make shellcheck
python -m pytest tests/unit/ tests/integration/ tests/tui/ -q
```

- **CI runs as root.** The container's default user is uid 0, and root bypasses
  file-permission (DAC) checks. A test that asserts an operation *fails* on an
  unreadable/unwritable path — or any `[[ -r ]]` / `os.access` / mode-bit check —
  can pass as your user yet flip as root. Gate such logic on the euid
  (`(( EUID == 0 ))` / `os.geteuid() == 0`) and reproduce it as root before
  trusting a green local run: `unshare -r python -m pytest <file>`.
- Tiers 1-3 are the whole suite. There is no VM or install tier; behaviour that
  needs a live Omarchy session is verified by hand on the machine and recorded in
  the commit message (Omarchy version, command, file).

---

## Commit Messages (Conventional Commits)

This repo follows the [Conventional Commits](https://www.conventionalcommits.org/) standard:

`<tag>(<scope>): <message>`

Rules:
- The *subject line* must be readable in a single line and **≤ 140 characters** total.
- `(<scope>)` is optional but encouraged — use a short area name (e.g., `install`, `hotkeys`, `tui`, `plugins`, `monitors`, `zsh`, `docs`).
- Breaking changes: add `!` to the tag (e.g., `feat!: ...`) and/or a `BREAKING CHANGE:` footer.
- Name the Omarchy version a change was verified against.

Tags:
- `feat`: new user-facing functionality
- `fix`: bug fix
- `docs`: documentation-only changes
- `style`: formatting/whitespace (no behavior change)
- `refactor`: code restructure (no new feature/fix)
- `perf`: performance improvement
- `test`: add/fix tests
- `build`: build system/deps/tooling changes
- `ci`: CI pipeline/config changes
- `chore`: maintenance (non-prod code changes)
- `revert`: revert a previous commit

## Versioning (Semantic Versioning)

This repo follows [Semantic Versioning](https://semver.org/). The version lives in `lib/hyprconf/__init__.py` (`__version__`) and is bumped by `scripts/publish`:

- **PATCH** — `fix:`, `docs:`, `perf:`, `refactor:`, `style:`, `test:`, `build:`, `ci:`, `chore:` — no new user-facing features.
- **MINOR** — any `feat:` commit — new backward-compatible functionality.
- **MAJOR** — any `feat!:` / `fix!:` or `BREAKING CHANGE:` footer — removed/renamed hotkeys, stages, flags, plugin ids or paths.

## Project Structure

- `install.sh` is the only entry point. Every stage is idempotent and byte-stable across re-runs; user choices are set once behind a marker in `~/.local/state/hyprconf/`; every system path is env-overridable (`_HYPRCONF_*`) so the suite can point it at a fake tree.
- Do not create files under `~/.config/` by hand — add them to the repo and wire them through a stage.
- **The bash `hyprconf` is a thin launcher; config logic lives in the Python library.** `lib/hyprconf/schema.py` is the single source of truth for options; `keybinds.py`, `rules.py`, `monitors.py`, `config.py`, `file_edit.py`, `lua_syntax.py`, `hyprctl.py`, `paths.py` own their formats. Add new logic to the library as a bounded, tested module — never an inline `python3 -c`/heredoc, never a second copy of the schema, and never more lines in `tui/main.py` when an extraction would do.

## Repository Layout

| Path | Purpose | Needed by end users |
|---|---|---|
| `install.sh` | The overlay installer (idempotent stages) | ✔ |
| `packages` | Official-repo packages, installed via `omarchy-pkg-add` | ✔ |
| `hypr/` | `bindings.lua`, `input.lua`, `looknfeel.lua` override files; monitor presets; `hyprland.block.lua`; `scripts/` | ✔ |
| `bin/` | `hyprconf` launcher, `hyprconf-stats`, `hyprconf-gpu-info` | ✔ |
| `lib/hyprconf/` | Python library (symlinked to `~/.local/lib/hyprconf`) | ✔ |
| `tui/main.py` | Textual TUI (symlinked to `~/.config/hypr/scripts/hyprconf-tui`) | ✔ |
| `plugins/hyprconf-resources/` | Omarchy bar-widget plugin (resource readout) | ✔ |
| `plugins/hyprconf-workspaces/` | Omarchy bar-widget plugin replacing `omarchy.workspaces` via `clonedFrom` | ✔ |
| `themes/hyprconf/`, `wallpapers/` | Omarchy user theme; extra backgrounds | ✔ |
| `zsh/`, `kitty/`, `fastfetch/`, `hooks/` | Managed zshrc block + p10k; kitty include; fastfetch layout; post-update hook | ✔ |
| `infra/firefox/policies.json` | System Firefox privacy policy | ✔ |
| `assets/` | Banner SVG, screenshot | ✔ |
| `web/` | Static landing page (S3 + CloudFront) — **not user-facing** | ✗ |
| `tests/` | Tiers 1 unit / 2 integration / 3 TUI | ✗ |
| `scripts/publish` | Promotes `omarchy` → `stable` | ✗ |
| `docs/` | CONTRIBUTING.md, hyprland-reference.md, quickshell-reference.md | ✗ |
| `.github/` | CI workflow, these instructions | ✗ |

### Key layout rules

- **`web/` is a static page** — a single self-contained `web/index.html` (plus `CNAME` and image assets), no framework, build step, or tests; do not reintroduce a build app or external CDN/font requests.
- **`infra/firefox/policies.json`** targets a system path, not `$HOME`, which is why it lives in `infra/` rather than beside the `$HOME` payloads.
- **`.gitattributes` `export-ignore`** excludes dev-only paths from `git archive` tarballs: `tests/`, `scripts/`, `.github/`, `web/`, `docs/`, `pyproject.toml`, `Makefile`, `.editorconfig`, `AGENTS.md`.
- **No dead code directories** — if a directory is unused, remove it. Git history preserves it.

## Package Management

- Every binary the overlay needs on a fresh Omarchy goes in `packages`, in a commented section saying which hotkey/stage wants it. Things already in Omarchy's base (`eza`, `zoxide`, `fastfetch`, `yay`, `ttf-jetbrains-mono-nerd-basic`, `xdg-terminal-exec`, `foot` …) are deliberately **not** listed.
- `install.sh` parses the file itself (strips `#` comments and whitespace) and hands the list to `omarchy-pkg-add`, which is idempotent (`omarchy-pkg-missing` guard, `pacman -Q` verify). Never call `pacman -Syu`, `pacman -R`, `yay`, `makepkg` or `omarchy-pkg-aur-add`.
- Use `pacman -Qo <binary>` / `pacman -Si <pkg>` to confirm the official package name before adding it.
- **Official repositories only, never the AUR** — see `AGENTS.md`. An orphan package is not a free one: remove a package when the hotkey that wanted it goes.

## Keybindings

- All hotkeys live in `hypr/bindings.lua`, loaded by Omarchy's `~/.config/hypr/hyprland.lua` *after* its defaults. `mainMod` is `SUPER`; do not redefine it.
- Bind with `o.bind(keys, description, dispatcher, options)` — Omarchy's helper from `default/hypr/helpers.lua` — never bare `hl.bind`: only `o.bind` records the description `omarchy-menu-keybindings` (`SUPER+K`) lists. A string dispatcher becomes `hl.dsp.exec_cmd(...)`.
- Every key hyprconf takes over is **unbound first** (`rebind()` does `hl.unbind` + `o.bind`); Hyprland does not replace a bind on a repeat of the same combo — both fire.
- Omarchy declares digits and `-`/`=` by **keycode** (`SUPER + SHIFT + code:20`), which `hl.unbind` of the keysym does not match. Use `unbind_keycode()` for those (`KEYCODE` table in `bindings.lua`) or both bindings fire.
- One bind per line — the TUI and `lib/hyprconf/keybinds.py` address binds by file and line.
- Launch apps through Omarchy's launchers (`omarchy-launch-terminal/-browser/-editor/-nautilus`), never a binary name; the user's defaults follow.
- Volume, brightness and media keys, `SUPER+D` and `SUPER+K` are left to Omarchy on purpose. If a hotkey launches a program not in Omarchy's base, add it to `packages`.

## Testing Rules (Non-Negotiable)

- **Every new or modified code path must be covered by a test.** Write tests that exercise every new path and every changed branch, run `make test`, and do not let coverage regress (`--cov=lib/hyprconf`, reported with `--cov-report=term-missing`; not yet gated on a percentage — keep it high regardless).
- **Tests track features, but are never silently weakened.** When a change *intentionally* alters behaviour, update the affected test to assert the **new** contract in the same commit and call it out in the commit message. Never gut, delete or loosen a test to mask a regression or get a green run: if a test fails for any reason other than an intended, documented behaviour change, fix the code, not the test.
- Tiers: `tests/unit/` (library modules, shipped scripts, `install.sh` via fake `omarchy-*` bins in a throwaway `HOME`, PII and Firefox-policy guards), `tests/integration/` (publish pipeline plumbing via `git archive` and `scripts/publish --dry-run`), `tests/tui/` (Textual Pilot, headless). Run the full suite with `make test`.
- **All tiers are hermetic — they run in a minimal `archlinux:latest` CI container, NOT on a live desktop.** No running Hyprland or Omarchy shell, no real hardware, no configured services, no real `$HOME`, not your group memberships, and never mutating the container (`pacman` exists there but must not be invoked). Rules:
  - Never let a script-under-test read/write a hardcoded system path. Make it an env-overridable variable (`: "${_VAR:=/real/default}"`, never `readonly`) and point it at a `tmp_path` in the test (`_HYPRCONF_*` in `install.sh`, `HYPRCONF_STATS_*` / `HYPRCONF_GPU_*` in the feeders).
  - Stub every external command the script calls — `omarchy-*`, `hyprctl`, `git`, `jq`, `fc-list`, `sudo` — by prepending a fake-bins dir to `PATH`; never rely on a host binary being present or behaving a certain way.
  - Don't depend on ambient state: real `id`/group membership, a configured git identity, an installed package, or a TTY. Inject it (`_HYPRCONF_ASSUME_TTY`).
  - To reproduce CI locally: `podman run --rm -v "$PWD":/repo -w /repo archlinux:latest bash -c 'pacman -Syu --noconfirm --needed python python-pytest python-pytest-asyncio python-pytest-xdist python-textual && python -m pytest tests/unit tests/integration tests/tui -q'` (or `docker`).

## Workflow Rules (Non-Negotiable)

- **Run `make test` after every change, before committing.** Do not commit code that fails tests.
- **Every commit must include both tests and README updates for the code it touches.** A feature without tests is unverified; a feature without README coverage is invisible.
- **All regular work happens on the `omarchy` branch.** `stable` is written only by `scripts/publish`, which promotes `omarchy` → `stable`. Never push directly to `stable` unless the user explicitly asks.
- **Never push to any remote unless the user explicitly asks.** Commit locally, then wait for the user to say "push". The only exception is an instruction that unambiguously includes a push (e.g., "commit and push").
- **Never run `scripts/publish` unless the user explicitly says to publish.** Publishing promotes `omarchy` to `stable` and creates a release tag — a deliberate, user-directed action.
- **Every install-time fix must be idempotent and re-applied by the post-update hook.** The hook runs `install.sh --no-update --no-packages` after every `omarchy-update`, so a fix that only works on a fresh run, needs sudo, or is not byte-stable across re-runs is incomplete. Set-once choices go behind a marker in `~/.local/state/hyprconf/`.

## Scripts

- All scripts use `#!/usr/bin/env bash` and `set -euo pipefail`. Two deliberate exceptions: the post-update hook (`set -uo pipefail` — `omarchy-hook` must never see it abort an update) and `bin/hyprconf-stats` (`set -u` — a long-lived sampler that must survive a transient read failure).
- **`hyprctl keyword` is a silent no-op on Hyprland 0.56** (Lua parser: "keyword can't work with non-legacy parsers", exit 0). Use `hyprctl eval "hl.config({ … })"` for runtime changes (it reports failure, exit 7) and `hyprctl dispatch 'hl.dsp.…({ … })'` for dispatchers — `dispatch dpms on` is a 0.55-ism that errors under Lua.
- Hotkey-launched scripts have no visible stdout: report through `omarchy-osd` and `omarchy-notification-send`.
- Do not use `pkill` or `killall` in new scripts.

## Monitor Configs

- Presets live in `hypr/` as `pcMonitors.<name>.lua` (plus `pcMonitors.lua` = `pc` and `laptopMonitors.lua` = `laptop`); `install.sh` **seeds** them into `~/.config/hypr/` once and never overwrites them.
- Each preset carries its own `hl.workspace_rule` lines — `switch_monitor.sh` parses them to move existing workspaces after the reload.
- When adding a preset: add the file to the seed list in `stage_monitors`, the resolution in `switch_monitor.sh`'s usage line, a hotkey in `hypr/bindings.lua` (via `o.bind`, with `hl.unbind` first) if it deserves one, a row in `README.md`, and a test in `tests/unit/test_switch_monitor.py` / `test_omarchy_install.py`.

---

## Web Frontend (`web/`)

`web/` is a single self-contained static page — `web/index.html` plus image assets
(`favicon.svg`, `hyprconf.webp`). No framework, build step, test suite, or bundler,
and no external CDN/font requests (privacy). It is a hand-maintained reflection of
the README so others can see what the project is, framed impersonally ("a personal
Hyprland setup, shared as-is").

It is hosted on the existing **AWS S3 + CloudFront** at `hyprconf.sh` (bucket
`hyprconf-sh`). There is no deploy machinery in the repo — updates are **manual**:
`aws s3 cp web/… s3://hyprconf-sh/` plus a CloudFront invalidation. Do **not**
rebuild a CDK app, a deploy CLI, or a React frontend. `scripts/publish` is lint +
test → promote `omarchy` to `stable` (no deploy step). The only thing under `infra/`
is the system Firefox policy.

---

## No Personal Information (Non-Negotiable)

**Never commit personal data to the repository.** Before every push, verify that no file contains:

- Hardcoded home paths (`/home/<user>/`) — use `~`, `$HOME`, or relative paths
- AWS account IDs, access keys, or secrets — use environment variables or `aws sts get-caller-identity`
- Real usernames, emails, hostnames or IPs — use `$USER`, generic placeholders, or resolve at runtime

Everything the overlay installs (`hypr/`, `kitty/`, `zsh/`, `plugins/`, `hooks/` …) lands in any user's `$HOME`, so it must use `~`, `$HOME` or a runtime substitution (`@HYPRCONF_DIR@` in the hook). Plugin copies use the `hyprconf.*` namespace, never `omarchy plugin clone`'s `<username>.<id>`. `tests/unit/test_no_pii.py` scans every tracked file.

---

## Known Codebase Quirks

- **Bash 5.3 `$(< file 2>/dev/null)` is broken** — the redirect breaks the `$(<)` special form, returning empty. Use `read -r var < file` (no fork) or `$(cat file 2>/dev/null)`.
- **Number keys 3/4 are NOT bound to workspaces** — F1/F2 are used instead; `SUPER+3`/`SUPER+4` keep Omarchy's binds and `SUPER+SHIFT+4` is the screenshot key.
- **`hyprctl keyword` is a silent no-op on Hyprland 0.56** — prints "keyword can't work with non-legacy parsers" and exits 0. `adjust-gaps` and the TUI use `hyprctl eval`; `toggle-native-display` and `hyprconf-brightness` were removed for this reason and `install.sh` sweeps their old copies.
- **Omarchy binds digits and `-`/`=` by keycode** (`code:10…21`), so `hl.unbind` of the keysym leaves Omarchy's bind live and both fire — `unbind_keycode()` in `bindings.lua` is load-bearing (the screenshot key once moved the window to workspace 4 first).
- **`omarchy-default-terminal <t>` with `<t>` missing exec()s a floating GUI terminal** — fatal to a non-interactive run; `stage_terminal` asserts kitty exists first. `omarchy-install-terminal` prints "Failed to install" and exits 0, so it is never used.
- **`omarchy-theme-set` only takes its permissive path for a symlinked user theme** — a real directory inside a git checkout is filtered as a stranger's theme, which is why `~/.config/omarchy/themes/hyprconf` is a symlink.
- **`omarchy plugin clone` hardcodes `<username>.<id>`** — a username in shipped config is PII, so `install.sh` reimplements the copy under `hyprconf.clock` / `hyprconf.workspaces` with the same `clonedFrom` manifest rewrite; `shell.json`'s `bar.centerAnchor` does no clone resolution and must follow the swap.
- **`omarchy refresh config hypr/<file>` / `omarchy refresh hyprland` write through the override symlinks into the checkout** (`cp -f` follows links). `install.sh`'s `restore_clobbered_override` puts a byte-identical stock template back from git; a preset reset to the stock `monitors.lua` template is reported, not repaired (Omarchy keeps `monitors.lua.bak.<epoch>`).
- **`hyprctl dispatch dpms on` is a 0.55-ism** — under the Lua parser use `hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'`, and `hl.dsp.workspace.move({ workspace = N, monitor = "…" })` to rehome workspaces after a preset switch (a reload only places future workspaces).
- **Bar widgets: never size off `parent`** — the bar's ModuleSlot takes its height from the widget's implicit size, so `parent.height` closes a binding loop and QML drops it, leaving an invisible widget. Bind `implicitHeight` to content.
- **Never use `git update-index --skip-worktree`** — it hides files from the working tree while keeping them tracked; clear with `git update-index --no-skip-worktree <file> && git checkout -- <file>`.
- **Branding: `.hyprconf` vs `hyprconf.sh`** — the project name is stylised as **`.hyprconf`** (leading dot) except for the domain (`hyprconf.sh`), binary names (`hyprconf`, `hyprconf-stats`) and plugin ids (`hyprconf.*`).
