# AI Agent Instructions

## README

**Always update `README.md` when making any change that could contradict or become inconsistent with its contents.** This includes:

- Adding, removing, or renaming packages in the `packages` file
- Adding, changing, or removing keybindings in `keybinds.conf`
- Adding or removing autostart entries in `hyprland.conf`
- Adding new stow packages or scripts under `stow/`
- Adding new themes to `theme-switcher/themes/`
- Changing monitor config logic in `setup.sh` or adding new monitor presets
- Any change to the ZSH setup in `setup.sh`

## Project Structure

This is a **GNU Stow dotfiles repo** for Arch Linux + Hyprland. Configs live under `stow/<package>/` and are symlinked into `$HOME` by `setup.sh` or `hyprsync`.

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
- Every theme JSON must include at minimum: `background`, `foreground`, `accent`, and `wallpaper` keys.
- `kitty`, `vscode`, and `firefox` keys are optional but should be included when the theme has matching support.
- When adding a new theme, add its name to the themes table in `README.md`.

## Scripts

- All scripts must use `#!/usr/bin/env bash` and `set -euo pipefail`.
- Prefer `hyprctl keyword` for runtime changes that do not require a full reload.
- Do not use `pkill` or `killall` in new scripts — use `kill <PID>` with a looked-up PID instead.

## Monitor Configs

- Monitor presets live in `stow/hypr/.config/hypr/` as `pcMonitors.<name>` files.
- When adding a new preset, add a corresponding keybind in `keybinds.conf` and document it in `README.md`.
