# vscode

## What
- Installs **VS Code** when missing, through Omarchy's own `omarchy-install-editor-vscode`:
  `visual-studio-code-bin` from Omarchy's `[omarchy]` repository (never the AUR); it **overwrites**
  `~/.vscode/argv.json` and `~/.config/Code/User/settings.json` (`update.mode none`; `:10,24`), runs
  `omarchy-theme-set-vscode` — and it **opens VS Code once** when done, by design.
  Not set-once: a later run that finds the package gone installs it again.
- Sets **`code` as the default editor**, once: `omarchy-launch-editor` (so `SUPER+C`) resolves it, and
  `omarchy default editor helix` moves the key with it. Seeded only once the package is really there —
  set-once means a choice recorded for an absent VS Code would never be retried. (`SUPER+C` is safe
  either way: `omarchy-launch-editor:21` falls back to `nvim` for an editor that is not on PATH.)
- Removes nothing. Arch's `code` (Code - OSS) conflicts with the package and stock Omarchy never
  installs it — if you did, the install fails inside Omarchy's installer and this module prints the
  retry command; drop `code` yourself first.

## Requires
`omarchy-install-editor-vscode`, `omarchy-pkg-present`, `omarchy-default-editor`. The package install
needs **sudo**: skipped with a pointer line under `--no-packages` (`HYPRCONF_NO_SUDO`) or with no
terminal for the password prompt — the post-update hook's path. No payload, no `packages` file.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/vscode && bash ~/.hyprconf/modules/vscode/install
```

## Settings
Marker `~/.local/state/hyprconf/editor-applied` (`$HYPRCONF_STATE` moves the directory); the pre-module
`defaults-applied` — one marker for browser and editor both — is migrated to it on the first run, delete
both to seed again. The default itself lives in `~/.local/state/omarchy/defaults/editor`.

## Undo
`bash modules/vscode/install undo` — the default editor returns to Omarchy's stock `nvim` if this
module seeded it and it is still `code` (a pick made after the install stays); the marker goes;
VS Code stays installed (`omarchy pkg drop visual-studio-code-bin` if you want it gone).

## Verified against Omarchy 4.0.4-1
`bin/omarchy-install-editor-vscode:6,10,24,27,29` (unguarded `omarchy-pkg-add`, the two `>` writes, theme, backgrounded
launch; no `set -e`, so it always exits 0), `bin/omarchy-pkg-present:6-8`, `bin/omarchy-default-editor:9-15,33-34,36`
(read-back; write, then the notification whose status the script returns), `bin/omarchy-pkg-add:12` (sudo), `bin/omarchy-update:10-12` (hook children get a pty).
