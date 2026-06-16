# AI Agent Instructions

## Hyprland Documentation

When making any Hyprland configuration change, consult these resources in order:

1. **`docs/hyprland-reference.md`** (this repo) — curated cheatsheet covering all syntax features in active use: monitor syntax, keybind types, window rules, hyprlock/hypridle/hyprpaper config, env vars, animations, and useful `hyprctl` commands.
2. **Hyprland wiki** — <https://wiki.hyprland.org> — authoritative and always up to date. Key sections:
   - Monitors: <https://wiki.hyprland.org/Configuring/Monitors/>
   - Variables: <https://wiki.hyprland.org/Configuring/Variables/>
   - Binds: <https://wiki.hyprland.org/Configuring/Binds/>
   - Window Rules: <https://wiki.hyprland.org/Configuring/Window-Rules/>
   - Animations: <https://wiki.hyprland.org/Configuring/Animations/>
   - hyprlock: <https://wiki.hyprland.org/Hypr-Ecosystem/hyprlock/>
   - hypridle: <https://wiki.hyprland.org/Hypr-Ecosystem/hypridle/>
   - hyprpaper: <https://wiki.hyprland.org/Hypr-Ecosystem/hyprpaper/>
   - hyprctl: <https://wiki.hyprland.org/Configuring/Using-hyprctl/>

**When adding features not covered in `docs/hyprland-reference.md`**, add a concise example of the new syntax to the appropriate section in that file.

---

## README

**`README.md` is the primary source of truth for any AI agent working on this project.** Inaccurate README content means flawed context for every future agent — treat drift as a correctness bug, not a documentation gap.

**The README must maintain 1:1 parity with the full feature set and functionality of this suite.** Every command, flag, subcommand, config file, script, package, keybind, section, and behavioural detail that exists in the codebase must be accurately reflected in the README. Conversely, nothing should appear in the README that no longer exists in the code.

**Any configuration change must include a README review as a non-optional step.** Before committing, grep `README.md` for content related to what you changed. If any section — feature bullet, table row, install step, code example, or any other reference — describes or implies the old behaviour, update it to match reality. This applies to every change, regardless of how small it seems. The trigger list below is illustrative, not exhaustive:

- Adding, removing, or renaming packages in the `packages` file
- Adding, changing, or removing keybindings in `keybinds.conf`
- Adding or removing autostart entries in `hyprland.conf`
- Adding new stow packages or scripts under `stow/`
- Adding new themes to `theme-switcher/themes/`
- Changing any logic in `setup.sh` (detection, install steps, service management, etc.)
- Adding new monitor presets
- Any change that affects functionality or the user experience — new CLI subcommands, changed behaviour, new TUI sections, installer changes, etc.

**Keep the README concise.** Every section must earn its place. Avoid repetition and verbose narrative; prefer tables and code blocks. The README must be clean and well-structured for human readers too.

**Never alter the hyprconf branding block** (banner SVG + badges) at the top of `README.md`.

---

## Commit Messages (Conventional Commits)

This repo follows the [Conventional Commits](https://www.conventionalcommits.org/) standard:

`<tag>(<scope>): <message>`

Rules:
- The *subject line* must be readable in a single line and **≤ 140 characters** total.
- `(<scope>)` is optional but encouraged — use a short area name (e.g., `sync`, `theme`, `network`, `tui`, `docs`).
- Breaking changes: add `!` to the tag (e.g., `feat!: ...`) and/or a `BREAKING CHANGE:` footer.

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

This repo follows [Semantic Versioning](https://semver.org/). Version bumps are determined by the commits in a release:

- **PATCH** (`2.0.x`) — `fix:`, `docs:`, `perf:`, `refactor:`, `style:`, `test:`, `build:`, `ci:`, `chore:` — no new user-facing features.
- **MINOR** (`2.x.0`) — any `feat:` commit — new backward-compatible functionality.
- **MAJOR** (`x.0.0`) — any `feat!:` / `fix!:` or `BREAKING CHANGE:` footer — removed/renamed commands, changed CLI interface, or other incompatible changes.

A release containing at least one `feat:` commit gets a minor bump; at least one breaking change gets a major bump. Otherwise it's a patch.

## Project Structure

This repo is the **hyprconf configuration suite** for Arch Linux + Hyprland: a standalone CLI/TUI binary (`hyprconf`) combined with the maintainer's personal dotfiles. Configs live under `stow/<package>/` and are symlinked into `$HOME` by `setup.sh` / `hyprconf sync`. The Python core library lives at `stow/hypr/.local/lib/hyprconf/`.

- Do not manually create files under `~/.config/` — add them to the appropriate `stow/<package>/` directory instead.
- Do not create new top-level stow packages without also adding any required binaries to the `packages` file.
- **The bash `hyprconf` is a thin dispatcher; config logic lives in the Python library.** `get`/`set`/`configure`/`keybind`/`rule`/`monitor`/`lock`/`idle`/`paper`/`schema`/`autodetect` all delegate to `cli.py`. Add new config-editing logic to `stow/hypr/.local/lib/hyprconf/` and delegate from bash (`python3 "$CLI_LIB/cli.py" <cmd>`) — never reintroduce an inline `python3 -c`/heredoc or a bash copy of the option schema (`schema.py` is the single source of truth). Keep the large files (`hyprconf`, `switch_theme.py`, `gpu-passthrough.sh`) from growing — extract a bounded, tested module when you touch them.

## Repository Layout

This is a monorepo — all components (dotfiles, Python library, static site, tests) are tightly coupled and version-lock to each other. Splitting into separate repos would add coordination overhead with no benefit.

| Directory | Purpose | Needed by end users |
|---|---|---|
| `stow/` | Dotfiles symlinked into `$HOME` by GNU Stow | ✔ |
| `install/` | `install.sh` | ✔ |
| `assets/` | Banner SVG/script, screenshot | ✔ |
| `theme/` | Vendor extension bundles (Firefox .xpi, VS Code .vsix) | ✔ |
| `infra/firefox/` | System Firefox privacy policy (`policies.json`) | ✔ |
| `web/` | Static landing page (S3 + CloudFront) — **not user-facing** | ✗ |
| `tests/` | All test tiers (unit/integration/tui/vm/install) | ✗ |
| `scripts/` | `publish` script for releases | ✗ |
| `docs/` | CONTRIBUTING.md, hyprland-reference.md | ✗ |
| `.github/` | CI workflows, copilot instructions | ✗ |

### Key layout rules

- **`web/` is a static page** — a single self-contained `web/index.html` (plus `CNAME` and image assets), no framework, build step, or tests. It is a reflection of the README so visitors can see what the project is; do not reintroduce a build app or external CDN/font requests.
- **`theme/` contains vendor extension bundles** — NOT hyprconf themes. Hyprconf theme JSONs live at `stow/hypr/.config/hypr/scripts/theme-switcher/themes/`. The `theme/` name is legacy; do not add hyprconf theme JSONs here.
- **`infra/firefox/policies.json`** is a system-level Firefox policy (installed by `setup.sh:setup_firefox` to `/etc/firefox/policies/policies.json`). It belongs in `infra/`, not `stow/`, because it targets a system path, not `$HOME`.
- **`.gitattributes` `export-ignore`** excludes dev-only directories from `git archive` tarballs: `tests/`, `scripts/`, `.github/`, `web/`, `docs/`, `pyproject.toml`, `Makefile`, `.editorconfig`, `AGENTS.md`.
- **No dead code directories** — if a directory is unused, remove it. Git history preserves it.

## Package Management

- All required Arch packages must be listed in the `packages` file.
- The file is parsed by `setup.sh` with `grep -v '^\s*#'` — comments (`#`) and blank lines are ignored and can be used freely.
- When introducing any new binary dependency (in a config, script, or keybind), add its Arch package to `packages` in the appropriate commented section.
- Hardware-specific or optional packages must be commented out with a note explaining the condition (e.g. `# nvidia-utils` for Nvidia GPU users).
- Use `pacman -Qo <binary>` to confirm the correct package name before adding.
- **Keep the core `packages` list minimal (project vision: minimal core + bolt-on).** Anything heavy or specialised (a VPN provider's CLI, GPU-passthrough tooling, an alternate browser) belongs in an **addon**, not the base. Only add to `packages` what a private desktop universally needs.

## Addons (`hyprconf addon <name>`)

Optional, bolt-on package sets live in the `_addon_*` functions of `stow/hypr/.local/bin/hyprconf` (current addons: `dev`, `vfio`, `vpn`, `librewolf`). To add one, register the name in `_ADDON_NAMES` and add a matching `case` branch to each of the five functions — there are no others to touch:

- `_addon_description` — one-line summary shown by `hyprconf addon`.
- `_addon_packages` — space-separated official-repo (`pacman`) packages.
- `_addon_aur_packages` — space-separated AUR (`yay`) packages.
- `_addon_post_install` — arbitrary post-steps; **print guidance, never run interactive/blocking commands** (sign-ins, prompts) — addon installs must stay unattended.
- `_addon_is_installed` — returns 0 when the addon's key package is present (drives the status column).

Add unit coverage for the new entry (see `tests/unit/test_hyprconf_vpn.py`'s addon tests) and list it in the README addon table.

## Keybindings

- All keybindings live in `stow/hypr/.config/hypr/keybinds.conf`.
- Group new bindings with related existing ones and add a comment if the group is new.
- `$mainMod` is `SUPER`. Do not redefine it.
- If a keybind launches a program not yet in `packages`, add it.

## Theme Switcher

- Themes live in `stow/hypr/.config/hypr/scripts/theme-switcher/themes/` as JSON files.
- Every theme JSON must include at minimum: `background`, `foreground`, `accent`, and `comment` keys.
- `kitty`, `vscode`, `firefox`, and `wallpaper` keys are optional. If `kitty` is absent, a conf is auto-generated from the palette.
- `ai:` prefix is reserved for AI-original themes with no external VS Code/Firefox dependency.
- When adding a new theme, add its name (and palette concept for `ai:` themes) to the themes tables in `README.md`.
- New CLI flags: `--current`, `--next`, `--prev`, `--random`, `--pick`, `--filter`, `--no-reload`.

## Testing Rules (Non-Negotiable)

- **100% test coverage is required for all new or modified code.** Before committing any change, write tests that exercise every new code path and every modified branch. Run `make test` and verify coverage does not decrease.
- **Tests track features, but are never silently weakened.** When a change *intentionally* alters behaviour, update the affected test to assert the **new** contract in the same commit and call it out in the commit message — keeping tests in lockstep with features is required, not optional. What's forbidden is silently gutting, deleting, or loosening a test to mask a regression or just to get a green run: if a test fails for any reason other than an intended, documented behaviour change, fix the code, not the test.
- When adding a new feature (script, function, CLI command, config path), add corresponding tests in the appropriate `tests/` tier (`unit/`, `integration/`, `vm/`, or `install/`).
- Test files live under `tests/`. Run the full suite with `make test`.
- **Unit/integration tests must be hermetic — they run on a bare `ubuntu-latest` CI runner, NOT Arch.** `make test` passing on a dev Arch box is necessary but NOT sufficient: the GitHub `Tests` workflow runs `tests/unit` + `tests/integration` on Ubuntu, which lacks Arch/Hyprland tooling (`pacman`, `hyprctl`, `nmcli`, `stow`, often `nft`/`pciutils`), has `/bin/sh` → `dash` (not bash), and no real `/sys/kernel/iommu_groups`, writable `/etc`, or the developer's group memberships. A test that reads or writes a real system path, calls a host tool, or depends on `$USER`'s groups will pass locally and fail CI. Rules:
  - Never let a script-under-test read/write a hardcoded system path (`/etc/...`, `/sys/...`, `/proc/...`, `/boot/...`). Make the path an env-overridable variable (`: "${_VAR:=/real/default}"`) and point it at a `tmp_path` in the test. Never use `readonly` for such a path.
  - Stub every external command the script calls (prepend a fake-bins dir to `PATH`); never rely on a host binary being present or behaving a certain way.
  - Don't depend on ambient state: real `id`/group membership, real `/proc/cmdline`, a configured git committer identity, an installed package, or a TTY. Inject it.
  - If a behaviour genuinely needs Arch/a live session/hardware, put the test in the `vm`/`install` tier (gated behind `--run-vm`/`--run-install`), not `unit`/`integration`.
  - To reproduce the CI environment locally without Docker: run the suite in an Ubuntu rootfs via `bwrap` (the dev box ships it), or at minimum sanity-check that no unit/integration test touches a real system path.

## Workflow Rules (Non-Negotiable)

- **Run `make test` after every change, before committing.** Do not commit code that fails tests. If tests fail, fix the failure before proceeding.
- **Every commit must include both tests and README updates for the code it touches.** Tests protect the integrity of the change; the README keeps the project documentation in sync. A feature without tests is unverified. A feature without README coverage is invisible. Both are required, not optional — treat a missing test or README update the same as a failing test.
- **All regular work is pushed to `dev` only.** Never push directly to `stable` or any other branch unless the user explicitly asks.
- **Never push to any remote unless the user explicitly asks.** Commit locally, then wait for the user to say "push". Unsolicited pushes risk exposing unreviewed changes, PII, or broken code. The only exception is if the user's instruction unambiguously includes a push (e.g., "commit and push").
- **Never run `scripts/publish` unless the user explicitly says to publish.** Publishing promotes `dev` to `stable` and creates a release tag — it is a deliberate, user-directed action, not a side-effect of regular development. When in doubt, commit locally and wait.
- **Hardware detection and generated config changes must be sync-patchable.** Any change to hardware detection logic (touchscreen, keyboard, accelerometer, GPU) or to files generated at setup/sync time (e.g. `60-hardware.conf`) must land exclusively in code paths that `hyprconf sync` already calls — specifically `setup_hardware_features()`, `write_hardware_conf()`, and `stow_all_packages()`. This guarantees existing installs are fully patched by running `hyprconf sync` with no manual intervention. Never gate such logic behind install-only paths.
- **All install-time fixes must also be applied by `hyprconf sync`.** Any bug fix or configuration that belongs in the install path (packages, services, system config files) must also be applied idempotently in the `hyprconf sync` code path — `sync_services()`, `setup_hardware_features()`, `write_hardware_conf()`, or a dedicated helper called from the sync block in `main()`. A user on an older install must be able to pick up the fix by running `hyprconf sync` with no manual steps. Never land a fix only in `install/install.sh` without a matching idempotent sync-time counterpart.

## Scripts

- All scripts must use `#!/usr/bin/env bash` and `set -euo pipefail`. Two deliberate exceptions: a **sourced** library (e.g. `assets/banner.sh`) must NOT set shell options (they would leak into the caller's shell), and a script that does its own explicit error handling via a `die`/`|| ...` pattern (e.g. `hyprconf-vpn`, `yubikey-fido2-setup`) may use `set -uo pipefail` to avoid `-e`'s fragility — do not add `-e` to these.
- Prefer `hyprctl keyword` for runtime changes that do not require a full reload.
- Do not use `pkill` or `killall` in new scripts — use `kill <PID>` with a looked-up PID instead.

## Monitor Configs

- Monitor presets live in `stow/hypr/.config/hypr/` as `pcMonitors.<name>` files.
- When adding a new preset, add a corresponding keybind in `keybinds.conf` and document it in `README.md`.

---

## Web Frontend (`web/`)

`web/` is a single self-contained static page — `web/index.html` plus image assets
(`favicon.svg`, `hyprconf.webp`). No framework, build step, test suite, or bundler,
and no external CDN/font requests (privacy). It is a hand-maintained reflection of
the README so others can see what the project is, framed impersonally ("a personal
Hyprland setup, shared as-is").

It is hosted on the existing **AWS S3 + CloudFront** at `hyprconf.sh`: the
`hyprconf-sh` S3 bucket sits behind a CloudFront distribution whose UA-router
function serves `install.sh` to `curl`/`wget` and the page to browsers — this is
what makes `bash <(curl -fsSL hyprconf.sh)` work. What was removed is the
*elaborate deploy machinery*: the CDK app (`infra/cdk/`), the `hyprconf
deploy`/`teardown` CLI, and `web/deploy.sh`. Updates are now **manual** — `aws s3
cp web/… s3://hyprconf-sh/` plus a CloudFront invalidation. Do **not** rebuild the
CDK app, a deploy CLI, or a React frontend. `scripts/publish` is test → promote dev
to stable (no deploy step). The only thing under `infra/` is the system Firefox
policy.

---

## No Personal Information (Non-Negotiable)

**Never commit personal data to the repository.** Before every push, verify that no file contains:

- Hardcoded home paths (`/home/<user>/`) — use `~`, `$HOME`, or relative paths
- AWS account IDs, access keys, or secrets — use environment variables or `aws sts get-caller-identity`
- Real usernames, emails, or IPs — use `$USER`, generic placeholders, or resolve at runtime

Config files under `stow/` must use `~` or relative paths since they are stowed into any user's `$HOME`.

---

## Known Codebase Quirks

These findings may help future agents avoid common pitfalls:

- **Never use `git update-index --skip-worktree`** — this hides files from the working tree while keeping them tracked. If `.gitignore` or `.editorconfig` goes missing, editors and tools silently break. If a previous rebase sets skip-worktree flags, clear them immediately with `git update-index --no-skip-worktree <file> && git checkout -- <file>`.
- **Branding: `.hyprconf` vs `hyprconf.sh`** — the project name is stylised as **`.hyprconf`** (with leading dot) everywhere except when referring to the domain/URL, which is **`hyprconf.sh`**. Never write "hyprconf" without a leading dot unless it's the domain, a CLI binary name (`hyprconf theme`, `hyprconf sync`), or the install command.
- **Default theme is `ai:circuit`** — `setup.sh:reapply_current_theme()` defaults to `ai:circuit` when no theme state exists.
- **Bash 5.3 `$(< file 2>/dev/null)` is broken** — the redirect breaks the `$(<)` special form, returning empty. Use `$(cat file 2>/dev/null)` instead.
- **Number keys 3/4 are NOT bound to workspaces** — F1/F2 are used instead for workspaces 3/4.
- **`iwd` package** is commented out in `packages` but referenced in `setup.sh` — guarded by `command -v iwctl` so systems without iwd don't fail.
- **Theme count** must be updated in the README badge, the README theme tables, and the hardcoded count in `web/index.html` when adding themes.
- **`theme/` dir is vendor extensions** — NOT hyprconf themes. Firefox .xpi and VS Code .vsix bundles live here. Hyprconf theme JSONs are at `stow/hypr/.config/hypr/scripts/theme-switcher/themes/`.
- **btop `color_theme` regex** — `switch_theme.py` uses `re.sub()` with `count=1` to replace the first `color_theme` line only. Without `count=1`, duplicate lines accumulate.
- **`_kill_process_if_running`** catches `PermissionError` — multi-user systems may have processes owned by other users that `pgrep` finds but `os.kill` can't signal.
- **`strip_comment()` in `file_edit.py`** uses `(^|\s)#.*$` regex — this can destroy `#hex` colour values. Hyprland generally uses `rgb()`/`0x` notation, but hyprlock/hyprpaper CAN use `#hex`.
- **`adw-gtk3`** is commented out in `packages` (AUR-only, optional) — `_resolve_gtk_theme()` in `switch_theme.py` has a fallback when it's absent.