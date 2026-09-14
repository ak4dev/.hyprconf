# shell-zsh

## What

zsh and [powerlevel10k](https://github.com/romkatv/powerlevel10k) in the terminal, with no framework in between.

- **`zshrc` is the whole interactive shell** — ~70 readable lines. It sources Omarchy's own `default/bash/{env-bootstrap,envs,aliases}`, so Omarchy's `OMARCHY_PATH`, `EDITOR`, `BROWSER` and aliases keep flowing through as it updates (`env-bootstrap:16,37-40`, `envs:2,8,13`); initialises zoxide, because Omarchy aliases `cd` to a wrapper that calls it (`aliases:17-31`); sets history, completion and emacs keys (what Oh My Zsh's `lib/` used to supply); loads the prompt and the two Arch zsh plugins; and ends with a `fastfetch` greeting.
- **`~/.zshrc` gets one line** — a grep-guarded `source`, the idiom Omarchy's own `/etc/skel/.bashrc:9` uses. Your file is never rewritten, and an edit to `zshrc` here is live in the next shell. A pre-module `# >>> hyprconf >>>` block is cut once, and only when both markers are present in order.
- **`~/.p10k.zsh` → this module's `.p10k.zsh`**: the pinned `config/p10k-classic.zsh` plus ~25 overrides, transcribed from the 1,739-line wizard dump it replaces. Never run `p10k configure` — it writes another dump over the file.
- **One pinned clone**, `~/.local/share/powerlevel10k` at a reviewed commit, `git clone --revision=<sha> --depth=1`, never pulled (AGENTS rule 8). powerlevel10k is AUR-only as a package, so `omarchy-pkg-add` cannot supply it.
- **kitty runs zsh** through this module's `hyprconf-zsh.conf` (`shell zsh`, resolved on `PATH` — kitty `utils.py:669-687`, `child.py:491`), included from `~/.config/kitty/kitty.conf` beside Omarchy's theme include. No `kitty.conf`? It is seeded from Omarchy's own stub first — the theme include lives only there — the way `omarchy-install-terminal:39-42` seeds `~/.config/kitty`.

The **login shell stays bash** — never `chsh`. Omarchy is bash-only, so its rc chain, uwsm session, SSH and scripts are untouched. Omarchy's repository also ships an `omarchy-zsh` package (starship, its own dotfiles, an `exec zsh` from `.bashrc`); it is deliberately not adopted — its setup script overwrites `~/.zshrc`, `~/.bashrc` and `~/.inputrc`, and it replaces this prompt.

## Requires

`zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` (all `extra`), installed through `omarchy-pkg-add`, and `git` for the clone. With `--no-packages` (`HYPRCONF_NO_SUDO`) or no terminal for `sudo`, the packages are skipped with one line; if zsh is still missing the module configures nothing and exits 0 — kitty pointed at an absent shell would not start. `hyprsync` needs `~/.local/bin/hyprconf`, the link the core installs. The greeting uses `~/.config/hyprconf/fastfetch.jsonc` when the `fastfetch` module is installed, plain `fastfetch` otherwise.

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/shell-zsh && bash ~/.hyprconf/modules/shell-zsh/install
```

The checkout has to stay where it is: `~/.zshrc` and `~/.p10k.zsh` point into it. Move it and re-run — the old line is replaced, not doubled.

## Settings

Edit `zshrc` or `.p10k.zsh` in the checkout; both are live, no re-run needed. The prompt's own overrides are the `typeset -g POWERLEVEL9K_*` lines; everything else comes from the pinned template. Your own additions belong in `~/.zshrc`, above or below the source line.

## Undo

`bash modules/shell-zsh/install undo` — drops the `~/.zshrc` line (and the file itself, if it holds nothing else and the module made it), the kitty include and `hyprconf-zsh.conf`, the `~/.p10k.zsh` link (restoring a `.p10k.zsh.stock` it saved) and the clone it made. A `~/.local/share/powerlevel10k` of your own is left alone, and so are the three packages: the overlay never removes a package.

## Verified against Omarchy 4.0.3-1

kitty 0.48.2, zsh 5.9.2, git 2.55.0, powerlevel10k pin `3308262`, reviewed 2026-09-01.
