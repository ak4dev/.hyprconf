# themes

## What

- **`dracula`** — a user theme (`colors.toml` + its own wallpaper), symlinked into `~/.config/omarchy/themes/dracula`
  and **never activated**: pick it with `omarchy theme set dracula` or `SUPER+SHIFT+CTRL+SPACE`. Omarchy blesses the
  link — a linked theme takes the plain `cp -r` branch (`omarchy-theme-set:204-208,275`) and `omarchy theme update`
  skips it (`omarchy-theme-extras:12`, read by `omarchy-theme-update:5`) — so a `git pull` here is the theme update.
  Anything already at that name — a directory, or a link to a working copy of yours — is left alone with a message,
  and no backup is dropped beside it: `omarchy-theme-list:7` lists every directory and link there as a theme.
- **`backgrounds/<theme>/<file>`** — extra wallpapers (`gruvbox/gruvbox.jpg`), copied into
  `~/.config/omarchy/backgrounds/<theme>/` when absent. The picker scans two directories, both keyed to the *active*
  theme: that theme's own `backgrounds/` and this one (`omarchy-theme-bg-next:7-14`, `omarchy-theme-bg-switcher:11-14`)
  — filed anywhere else a wallpaper is invisible, and `omarchy theme bg install` only opens nautilus on the folder
  (`:5-9`). dracula's own wallpaper ships inside the theme, where Omarchy already looks.

## Requires

Coreutils, and `omarchy-theme-remove` for the undo — nothing else: no package, no `sudo`, no prompt, no marker. The link target and "copy when absent" are their own gates, so a re-run writes nothing.

## Install alone

```sh
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/themes && bash ~/.hyprconf/modules/themes/install
```

Or copy `dracula/` to the root of a repository of your own: anyone can then `omarchy theme install <url>` it, which
clones the repo root in and **activates** it (`omarchy-theme-install:24,32,56,63`).

## Settings

Add or drop a wallpaper by moving the file in or out of `backgrounds/<omarchy theme>/`. `dracula/colors.toml`'s header
names the values kept where Omarchy would otherwise derive one (`omarchy-theme-color:223,236`).

## Undo

`bash modules/themes/install undo`: `omarchy theme remove dracula` on our own link (`rm -rf` on a symlink unlinks it,
`omarchy-theme-remove:31-37` — a theme of yours there stays), and each seeded wallpaper where the bytes are still ours.

## Verified against Omarchy 4.0.3-1
