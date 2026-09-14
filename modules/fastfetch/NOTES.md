# fastfetch module — notes for the integrator (delete this file)

## Findings

Landed:

- **install-desktop.0#1** — greeting kept, shadowing stopped. Per BRIEF decision 11 the
  target is `~/.config/hyprconf/fastfetch.jsonc` (a **copy**, `cmp`-gated), not the
  finding's `~/.config/fastfetch/hyprconf.jsonc` and not a symlink: nothing else on the box
  reads hyprconf's own directory, and a copy keeps the module runnable from a dropped
  folder.
- **install-desktop.0#2** — indentation (was 8 spaces / tab+space on the first two module
  entries), the two trailing-space keys (`OS Age `, `Uptime ` rendered ` : ` with a double
  gap), Omarchy's one-line OS Age (`/etc/fastfetch/config.jsonc:142`), and every positional
  format replaced by the names `fastfetch --help <module>-format` lists (2.68.1): title,
  os, kernel (`{release}` — the positional hid that), display, cpu, wm, gpu driver.
  `test_every_format_names_its_variables` and `test_keys_and_indentation_render_once` pin it.
  Rendering diffed before/after on this box: identical but for the two double gaps.
- **install-desktop.0#3** — the GPU row's `{1} {2}` is already `{name}` in the dev tree
  (landed before this phase); its sibling GPU Driver row now uses `{driver}`. The
  *optional* half — folding the driver into the GPU row and deleting the row — is **not**
  taken: it changes what the user sees, which is taste, not a defect.
- **install-core.3#12** — `~/.config/fastfetch/config.jsonc` is never written, so
  `omarchy-launch-about` gets Omarchy's own layout and its window-fit measurement back. The
  `--logo arch2 --logo-color-1 green --logo-color-2 green` flags moved from
  `zsh/zshrc.block:53` into the config's `logo` block (verified: `fastfetch -c` alone now
  renders byte-identically to the old flags + old config).

Not landed / deviations:

- `final-layout.md`'s one-liner says the module "backs up a foreign file once". It does
  not: the old backup existed because the path was Omarchy's; at hyprconf's own path there
  is nothing of anyone else's to displace, and BRIEF decision 11 says copy + `cmp` + undo.
  What *is* kept is the migration below, which restores the old stage's `.stock`.
- **install-core.1#16 / .1#18** are already landed in the dev tree as
  `backup_before_link()` (install.sh:353). The fastfetch call site goes with the stage;
  **keep the helper** — `link_hypr_override` still uses it.
- `install-core.3#13` was rejected upstream; nothing here relates to it.

## Delete / rewire in the legacy tree

- `install.sh`: `stage_fastfetch` (939-952) and its call at 1504. Its
  `backup_before_link` call goes with it; the helper stays.
- Payload `fastfetch/config.jsonc` (copied here, then edited — take **this** copy, not the
  old one) and the `"fastfetch"` member of `PAYLOAD` (`tests/unit/test_omarchy_install.py:331`).
- Tests: `test_fastfetch_config_is_linked_with_a_stock_backup` (1861-1872) and
  `test_fastfetch_link_without_existing_config_makes_no_backup` (1875-1881); and in
  `test_a_dotfiles_link_at_an_override_path_is_backed_up_as_a_link` (832-…) drop the
  `config.jsonc` entry from `theirs`/`links` (843, 847) — the hypr and p10k halves stay
  until those modules land.
- Docs: `README.md:83` (the symlink table row), `:117` (`fastfetch/` in the payload list),
  `:397` (the revert line — replaced by the module's undo line); `README.md:26`'s Greeting
  row now points at this module. `docs/CONTRIBUTING.md:44` (tree row). `AGENTS.md:51` — the
  `~/.config/fastfetch/config.jsonc` symlink row leaves the deliberate-choices table
  entirely; its stated reason ("reads first") was the side effect that shadowed About.

## Cross-module

- **shell-zsh** owns the greeting: `zsh/zshrc.block:50-53` becomes
  `fastfetch -c "$HOME/.config/hyprconf/fastfetch.jsonc"` when that file exists, plain
  `fastfetch` otherwise, and **drops the `--logo*` flags** (now in the config). Nothing
  else reads the file.
- No `packages` file (fastfetch is Omarchy base,
  `install/omarchy-base.packages:34`), no state marker (no user choice), no `sudo`, no TTY
  or `HYPRCONF_NO_SUDO` gate needed, and the module calls no `omarchy-*` command — a test
  pins `box.commands == []`.
- `undo` `rmdir`s `~/.config/hyprconf` only while it is empty, so a later module may share
  that directory safely.

## Live verification (user, on each machine)

1. This laptop has the old `~/.config/fastfetch/config.jsonc` → checkout symlink. The first
   run of this module removes it (no `.stock` exists there, so nothing is restored); after
   that, `omarchy-launch-about` should show Omarchy's own About layout, logo and fitted
   window again.
2. Open a new shell: the greeting renders with the `arch2` green logo from the config, via
   `fastfetch -c ~/.config/hyprconf/fastfetch.jsonc` (shell-zsh).
