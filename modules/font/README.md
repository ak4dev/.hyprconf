# font — the system monospace font

## What

Sets **GeistMono Nerd Font** as the system monospace, once, through Omarchy's own
`omarchy-font-set`: it writes `~/.config/fontconfig/fonts.conf` (what the shell, Qt apps
and anything resolving `monospace` read), rewrites or appends `font_family` in
`~/.config/kitty/kitty.conf` and restarts the shell (`bin/omarchy-font-set:57-72,33-42,74`); the
family is handed over verbatim, since the setter greps `fc-list` itself and refuses a
name it does not know (`:24-27`). Omarchy's `ttf-jetbrains-mono-nerd-basic` stays
installed and selectable, and the choice is **set once**: after the first run the font is
yours, and the post-update hook never takes it back.

## Requires

`otf-geist-mono-nerd` (`extra`), from the `packages` file beside this README, installed
with `omarchy-pkg-add` when `omarchy-pkg-present` says it is missing. That needs `sudo`:
with `HYPRCONF_NO_SUDO` set (what `--no-packages` and the post-update hook pass) or no
terminal for the prompt, the module prints one pointer line and exits 0.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/font && bash ~/.hyprconf/modules/font/install
```

## Settings

The family is the `family=` line in `install`; `omarchy font set <name>` changes it any
time (`omarchy font list` names them). Deleting the marker
`${HYPRCONF_STATE:-~/.local/state/hyprconf}/font-applied` offers the font again next run.

## Undo

`bash install undo` drops the marker and prints the command that puts Omarchy's own font
back — it restarts the shell, so it stays yours: `omarchy font set 'JetBrainsMono Nerd Font'`.

Verified against Omarchy 4.0.3-1.
