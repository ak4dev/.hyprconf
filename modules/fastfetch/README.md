# fastfetch

## What
The shell greeting's layout: one `fastfetch` config copied to
`~/.config/hyprconf/fastfetch.jsonc` — user, OS, kernel, packages, display, terminal, WM,
CPU, GPU and driver, memory, network, OS age and uptime between two rules, `arch2` logo.

It deliberately does **not** take `~/.config/fastfetch/config.jsonc`: that is the one user
config fastfetch reads (`fastfetch --list-config-paths`, first hit wins, no merge), and
Omarchy's About screen renders bare `fastfetch` there (`bin/omarchy-launch-about:161`),
skipping its window-fit measurement whenever that file exists (`custom_fastfetch_config`
`:16-18`, used at `:61` and `:95`). Omarchy 4 retired its own user copy to
`/etc/fastfetch/config.jsonc` (`bin/omarchy-upgrade-to-quattro:1553-1569`). Both are left
alone, so About stays stock; a link an earlier hyprconf release left at that path is
cleared on the first run, and any real file it displaced (`config.jsonc.stock`) put back.

## Requires
`fastfetch`, which is Omarchy base (`install/omarchy-base.packages:34`) — so no packages,
no `sudo`, no terminal, no running session.

## Install alone
```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/fastfetch && bash ~/.hyprconf/modules/fastfetch/install
```

## Settings
The greeting is the shell's: `modules/shell-zsh` runs `fastfetch -c
~/.config/hyprconf/fastfetch.jsonc` when that file exists, plain `fastfetch` otherwise. On
its own, put that line in your rc — the logo flags live in the config's `logo` block, so
`-c` is the whole command. Edit `config.jsonc` here and re-run: the copy is `cmp`-gated, so
a run that changes nothing writes nothing. Format variables are named
(`fastfetch --help <module>-format`), never positional.

## Undo
`bash ~/.hyprconf/modules/fastfetch/install undo` — removes the copy, and clears a link an
earlier release left at `~/.config/fastfetch/config.jsonc`, putting back the
`config.jsonc.stock` it displaced. Omarchy's `/etc/fastfetch/config.jsonc` is what is left.

## Verified against Omarchy 4.0.3-1 — paths above read from the installed tree; fastfetch 2.68.1
