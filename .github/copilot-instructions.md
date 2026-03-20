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

## Commit Message Tags (Required)

When creating git commits in this repo, **always use one of the tags below**, and use this **exact subject-line format**:

`<tag>: [section] <message>`

Rules:
- The *subject line* must be readable in a single line and **≤ 140 characters** total.
- `[section]` should be a short area name (e.g., `installer`, `hyprland`, `theme`, `docs`, `infra`).
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

## Project Structure

This repo is the **hyprconf configuration suite** for Arch Linux + Hyprland: a standalone CLI/TUI binary (`hyprconf`) combined with the maintainer's personal dotfiles. Configs live under `stow/<package>/` and are symlinked into `$HOME` by `setup.sh` / `hyprconf sync`. The Python core library lives at `stow/hypr/.local/lib/hyprconf/`.

- Do not manually create files under `~/.config/` — add them to the appropriate `stow/<package>/` directory instead.
- Do not create new top-level stow packages without also adding any required binaries to the `packages` file.

## Package Management

- All required Arch packages must be listed in the `packages` file.
- The file is parsed by `setup.sh` with `grep -v '^\s*#'` — comments (`#`) and blank lines are ignored and can be used freely.
- When introducing any new binary dependency (in a config, script, or keybind), add its Arch package to `packages` in the appropriate commented section.
- Hardware-specific or optional packages must be commented out with a note explaining the condition (e.g. `# nvidia-utils` for Nvidia GPU users).
- Use `pacman -Qo <binary>` to confirm the correct package name before adding.

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
- New CLI flags: `--current`, `--next`, `--prev`, `--random`, `--wofi`, `--filter`, `--no-reload`.

## Testing Rules (Non-Negotiable)

- **100% test coverage is required for all new or modified code.** Before committing any change, write tests that exercise every new code path and every modified branch. Run `make test` and verify coverage does not decrease.
- **Never modify existing tests without explicit user notification and confirmation.** Tests are the safety net for all features. Silently changing a test to make it pass defeats its purpose. If a test needs to change, stop, explain why to the user, and get approval first.
- When adding a new feature (script, function, CLI command, config path), add corresponding tests in the appropriate `tests/` tier (`unit/`, `integration/`, `vm/`, or `install/`).
- Test files live under `tests/`. Run the full suite with `make test`.

## Scripts

- All scripts must use `#!/usr/bin/env bash` and `set -euo pipefail`.
- Prefer `hyprctl keyword` for runtime changes that do not require a full reload.
- Do not use `pkill` or `killall` in new scripts — use `kill <PID>` with a looked-up PID instead.

## Monitor Configs

- Monitor presets live in `stow/hypr/.config/hypr/` as `pcMonitors.<name>` files.
- When adding a new preset, add a corresponding keybind in `keybinds.conf` and document it in `README.md`.
