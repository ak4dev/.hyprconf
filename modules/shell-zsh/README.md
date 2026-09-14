# shell-zsh

## What

zsh and [powerlevel10k](https://github.com/romkatv/powerlevel10k) in the terminal, with no framework in between.

- **`zshrc` is the whole interactive shell** — ~70 readable lines. It sources Omarchy's own `default/bash/{env-bootstrap,envs,aliases}`, so Omarchy's `OMARCHY_PATH`, `EDITOR`, `BROWSER` and aliases keep flowing through as it updates (`env-bootstrap:10-16,37-40`, `envs:2,8,13`); initialises zoxide, because Omarchy aliases `cd` to a wrapper that calls it (`aliases:17-31`); sets history, completion and emacs keys (what Oh My Zsh's `lib/` used to supply); loads the prompt and the two Arch zsh plugins; and ends with a `fastfetch` greeting.
- **`~/.zshrc` gets one line** — a grep-guarded `source`, the idiom Omarchy's own `/etc/skel/.bashrc:2` uses (`[[ -r … ]] && source …`). Everything else in your file stays exactly where it is, above or below it, and an edit to `zshrc` here is live in the next shell. A re-apply leaves one copy of the line and no more, a line naming a checkout that has since moved is replaced rather than doubled, and a hyprconf 7.x `# >>> hyprconf >>>` … `# <<< hyprconf <<<` block is cut once — only when both markers are present in that order, since with one of them hand-removed a begin-to-EOF cut would eat everything you wrote below it. Such a file is left exactly as it is.
- **`~/.p10k.zsh` → this module's `.p10k.zsh`**: the pinned `config/p10k-classic.zsh` plus ~25 overrides, transcribed from the 1,739-line wizard dump it replaces. Never run `p10k configure` — it writes another dump over the file.
- **One pinned clone**, `~/.local/share/powerlevel10k` at a reviewed commit, `git clone --revision=<sha> --depth=1`, never pulled (AGENTS rule 8). powerlevel10k is AUR-only as a package, so `omarchy-pkg-add` cannot supply it.
- **kitty runs zsh** through this module's `hyprconf-zsh.conf` (`shell zsh`, resolved on `PATH` — kitty `utils.py:669-687`, `child.py:491`), included from `~/.config/kitty/kitty.conf` beside Omarchy's theme include. No `kitty.conf`? It is seeded from Omarchy's own stub first — the theme include lives only there — the way `omarchy-install-terminal:39-42` seeds `~/.config/kitty`.

The **login shell stays bash** — never `chsh`. This is the one place that fact is written down; everything else in the tree points here.

Omarchy's *installed* tree is bash-only: its rc chain, its uwsm session, SSH and every `omarchy-*` script read bash, and on 4.0.3-1 `grep -RIl zsh /usr/share/omarchy` finds it twice, inertly — a commented-out menu entry (`config/omarchy/extensions/omarchy-menu.jsonc:29`) and a comment in `migrations/1786952219.sh:8`. `/etc/skel` ships `.bashrc`, `.bash_profile` and `.bash_logout` and no zsh file. So zsh is the terminal's shell and nothing else's, and Omarchy's own updates keep flowing through the bash files `zshrc` sources.

Omarchy's `[omarchy]` repository does ship an `omarchy-zsh` package (starship, its own dotfiles, an `exec zsh` from `.bashrc`) — so "Omarchy is bash-only" is true of what is installed, not of what Omarchy offers. It is deliberately not adopted (rule 1 asks the question, and this is the answer): its `omarchy-setup-zsh` copies over `~/.zshrc`, `~/.bashrc` and `~/.inputrc`, its `templates/bashrc` `exec zsh`s out of every interactive bash — which is a login-shell change in all but name — and its shell files are not Omarchy's own `default/bash/*`, so its zsh would stop tracking Omarchy's updates. It also replaces this prompt.

## Requires

`zsh`, `zsh-autosuggestions`, `zsh-syntax-highlighting` (all `extra`), installed through `omarchy-pkg-add`, and `git` for the clone. With `--no-packages` (`HYPRCONF_NO_SUDO`) or no terminal for `sudo`, the packages are skipped with one line; an install that fails fails the module (the core names it; re-run after pacman's error); if zsh is still missing the module configures nothing and exits 0 — kitty pointed at an absent shell would not start. `hyprsync` needs `~/.local/bin/hyprconf`, the link the core installs. The greeting uses `~/.config/hyprconf/fastfetch.jsonc` when the `fastfetch` module is installed, plain `fastfetch` otherwise. The checkout has to stay where it is: `~/.zshrc` and `~/.p10k.zsh` point into it (move it and re-run — the old line is replaced, not doubled).

## Install alone

```bash
git clone --depth 1 --filter=blob:none --sparse -b stable https://github.com/ak4dev/.hyprconf ~/.hyprconf \
  && git -C ~/.hyprconf sparse-checkout set modules/shell-zsh && bash ~/.hyprconf/modules/shell-zsh/install
```

## Settings

Edit `zshrc` or `.p10k.zsh` in the checkout; both are live, no re-run needed. The prompt's own overrides are the `typeset -g POWERLEVEL9K_*` lines; everything else comes from the pinned template. Your own additions belong in `~/.zshrc`, above or below the source line.

## Undo

`bash modules/shell-zsh/install undo` — drops the `~/.zshrc` line (and the file itself when that leaves it empty; stock Omarchy ships none), the kitty include and `hyprconf-zsh.conf`, the `~/.p10k.zsh` link (restoring a `.p10k.zsh.stock` it saved, file or dotfiles link) and the clone it made. A `~/.local/share/powerlevel10k` of your own is left alone, and so are the three packages: the overlay never removes a package.

Two things it deliberately does not tidy. `~/.local/state/hyprconf` survives while another module's marker is still in it — undo the rest, or `rm -rf` it once you are done. And a `~/.config/kitty/kitty.conf` that did not end in a newline comes back one byte longer: the include had to terminate the last line first, and undo cannot tell that newline from one you wrote. Omarchy's own stub ends in a newline, so a stock box never sees it.

## Verified against Omarchy 4.0.3-1 — kitty 0.48.2, zsh 5.9.2, git 2.55.0, powerlevel10k pin `3308262`, reviewed 2026-09-01
