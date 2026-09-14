# terminal-kitty

## What — kitty as Omarchy's default terminal, plus two kitty preferences as an include

- `omarchy-default-terminal kitty` — **once**, behind `~/.local/state/hyprconf/terminal-applied`.
  It writes `~/.config/xdg-terminals.list` (`bin/omarchy-default-terminal:31-35`), which SUPER+RETURN,
  `$TERMINAL`, the floating terminals and the menu all resolve through. Change it later with
  `omarchy default terminal <name>` — hyprconf will not take it back.
- `hyprconf.conf` (cursor trail, 0.85 opacity) → `~/.config/kitty/`, plus one `include
  hyprconf.conf` line at the END of `~/.config/kitty/kitty.conf` — created from Omarchy's own
  stub when you have none, since from 4.0.3 the user file is optional and the defaults live in
  `/etc/xdg/kitty/kitty.conf`, merged *below* it. The include restates nothing Omarchy sets.
- Left alone: the body of `kitty.conf`, the login shell (never `chsh` — why, in
  [`shell-zsh`](../shell-zsh/README.md)), everything outside `$HOME` but the package. `omarchy refresh config kitty/kitty.conf` drops the include; the next run restores it.
  `shell zsh` is **not** here — `shell-zsh` ships its own kitty include (`hyprconf-zsh.conf`), so
  kitty runs zsh once both are installed, in either order.

## Requires

Omarchy 4.0.3-1 and `kitty` (official `extra`), from this module's `packages` via `omarchy-pkg-add` —
skipped with a pointer line, never a failure, under `HYPRCONF_NO_SUDO` (`--no-packages`) or with no
terminal for sudo; an install that fails fails the module (the core names it; re-run after pacman's
error). A box without kitty is left untouched.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/terminal-kitty && bash ~/.hyprconf/modules/terminal-kitty/install
```

## Settings — `HYPRCONF_STATE` (default `~/.local/state/hyprconf`), `OMARCHY_PATH`, `HYPRCONF_NO_SUDO`

## Undo

`bash modules/terminal-kitty/install undo` — strips the include, removes `hyprconf.conf` and the
marker, and hands the default back to Omarchy's stock `foot` only while kitty is still current
(`/usr/share/xdg-terminal-exec/hyprland-xdg-terminals.list`, omarchy-settings 4.0.3-1).

## Verified against Omarchy 4.0.3-1 — kitty 0.48.2-1, omarchy-settings 4.0.3-1.
