# terminal-kitty — integrator notes (delete this file)

## Findings landed

- **shell-misc.0#2** (terminal-kitty.json) — `hyprconf.conf`'s header cut from 15 comment lines
  to 4, rewritten to the 4.0.3 layout (user file = theme include + overrides, real defaults in
  `/etc/xdg/kitty/kitty.conf`). The zsh sentence is gone with the `shell` line (see 1#19).
  The old `OMARCHY_KITTY_CONF` fixture is replaced by `UPGRADED_KITTY_CONF` in this module's
  test, which models the *upgraded* box (migration `1788745941.sh:11-13` only refreshes a
  sha-matched stock file, so a hyprconf box keeps the fat 4.0.0 file) — the fresh-install shape
  is the box fixture's `config/kitty/kitty.conf`, used for the seeding test.
- **install-system.0#2 / #3** (packages.json) — `modules/terminal-kitty/packages` is one name plus
  one trailing `# why`; the prose in the root `packages` file is not carried over. Read with the
  same comment-stripping line loop, no seam.
- **install-core.2#11** — the default terminal is now **set-once** behind
  `${HYPRCONF_STATE}/terminal-applied` (rule 5), not re-asserted on every hook run. A failed
  setter writes no marker, so the next run records the choice once the value reads back as kitty.
- **install-core.2#12** — `stage_terminal` + `stage_kitty_include` are one module; no
  stage-in-a-stage call, no global resolved in `main()`.
- **install-core.2#15** — no dead `grep -q '^shell '` guard, and no comment printf'd into the
  user's file.
- **install-core.1#19** — `resolve_zsh` and `_HYPRCONF_ZSH` are gone from this module entirely:
  it writes no `shell` line. **shell-zsh owns that**, in its own `hyprconf-zsh.conf` plus its own
  `include hyprconf-zsh.conf` line. Verified the two are order-free: kitty resolves a bare program
  name on PATH (`/usr/lib/kitty/kitty/child.py:491`) and a missing `include` is a logged no-op
  (`/usr/lib/kitty/kitty/conf/utils.py:346`).
- **install-core.0#9** — no `_HYPRCONF_PKG_ADD`, no `_HYPRCONF_KITTY_BIN`, no `_HYPRCONF_ZSH*`.
  Presence is asked of `omarchy-pkg-present` (a faked `omarchy-*` command), so the tests need no
  product seam. `_HYPRCONF_ASSUME_TTY` is the only `_HYPRCONF_*` left, for the sudo gate.
- **install-core.2#13 / #14 / #16 / 0#10** were already landed in the worktree's `install.sh`
  during the foundation phase; the module carries the same behaviour (warn-and-skip, 4.0.3 facts,
  unconditional include) with one change: when `~/.config/kitty/kitty.conf` is absent it is now
  **seeded from `$OMARCHY_PATH/config/kitty/kitty.conf`** before the include is appended, so the
  box does not end up with a user file that has our include and not Omarchy's theme include
  (the theme include lives only in the user file — `/etc/xdg/kitty/kitty.conf` has none). The
  shape is `omarchy-install-terminal:39-42`'s own seed-when-absent.

## Not landed

- Nothing from the two bundles was skipped. `install-core.2#8` (a shared `interactive()` helper)
  is a core-level dedupe: each module carries its own two-line gate by contract, so there is
  nothing to share.

## Delete from the legacy tree when this module is wired in

- `install.sh`: `stage_terminal` (`:630-675`), `stage_kitty_include` (`:677-714`, incl. its header),
  `resolve_zsh` (`:377-391`) and its two call sites/ordering comment in `main()` (`:1493-1495`),
  the `: "${_HYPRCONF_ZSH_BIN:=zsh}"` seam (`:51`) **only after shell-zsh lands** (`stage_shell`
  still reads `_HYPRCONF_ZSH` at `:1338`), and `kitty` from the root `packages` file.
- Payload: `kitty/` (the whole directory — `kitty/hyprconf.conf` is copied here, header rewritten).
- Tests in `tests/unit/test_omarchy_install.py`: `OMARCHY_KITTY_CONF` (`:36-46`), `_terminal_stub`
  (`:103-112`) and `_setup`'s kitty.conf seeding (`:254-255`), `test_default_terminal_is_never_set_to_an_absent_kitty`,
  `test_a_failed_terminal_setter_does_not_take_the_install_down`, `test_kitty_conf_gains_only_the_include`,
  `test_hyprconf_kitty_include_file_is_self_contained`, `test_the_shell_line_is_written_once_however_often_the_stage_runs`,
  `test_the_include_is_written_even_with_no_user_kitty_conf`, `test_shell_line_points_at_zsh_only_when_zsh_exists`
  (the last two zsh ones move to **shell-zsh**, not here), the `"kitty"` PAYLOAD entry (`:330`),
  `REPO_ROOT / "kitty" / "hyprconf.conf"` in the scan roots (`:1513`), and the
  `omarchy-default-terminal` assertions at `:1163`, `:1265` and `:2436`.
- Docs: `README.md:74` (terminal row), the `kitty` row at `:241`, `kitty/` in the payload sentence
  at `:117`, the revert line at `:393`; `AGENTS.md` integration-map Shell row (the `kitty.conf`
  include half) and rule 6's "never rewrite Omarchy's `kitty.conf` beyond the one `include`";
  `docs/CONTRIBUTING.md:43` (tree entry `kitty/hyprconf.conf`) and `ZSH_BIN`/`ZSH` in the
  `install.sh` seam list at `:141`.
- `pyproject.toml`: `testpaths = ["modules", "tests"]`.

## Cross-module facts

- **shell-zsh** must ship `hyprconf-zsh.conf` (with `shell zsh`) *and* append its own
  `include hyprconf-zsh.conf` line to `~/.config/kitty/kitty.conf`. This module appends only its
  own include and `undo` strips only its own two lines, so the two never collide.
- **font**: `omarchy-font-set` appends `font_family` to `~/.config/kitty/kitty.conf`
  (`bin/omarchy-font-set:33-40`). Our include goes last, and `hyprconf.conf` sets no font, so the
  order is harmless — a test here pins that `hyprconf.conf` restates nothing Omarchy owns.

## Live verification

1. On a real box, after `omarchy refresh config kitty/kitty.conf` (which drops the include), the
   next run must put it back and kitty must still pick up `cursor_trail`/`background_opacity`.
2. Two includes in the 4.0.3 stub (ours + shell-zsh's) with `omarchy-font-set` appending
   `font_family` beside them — `kitty +runpy 'from kitty.config import *'` or just a restart.
3. `install undo` on this laptop: the fat 4.0.0-era `kitty.conf` must come back byte-identical
   minus the two lines (its mode and, if any, its symlink preserved by `sed --follow-symlinks -i`).
4. The stock-default claim: `omarchy-default-terminal` with no `~/.config/xdg-terminals.list`
   prints `foot` (from `/usr/share/xdg-terminal-exec/hyprland-xdg-terminals.list`).
