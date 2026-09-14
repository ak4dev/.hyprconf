# modules/font — notes for the integrator (delete this file)

## Findings landed

- **install-core.3#7** (already landed in the worktree's `stage_font` before the split, carried
  over verbatim): the family goes to `omarchy-font-set` literally, no fc-list pre-check, no
  `geist.*(nerd|mono)` fallback. `test_the_family_goes_to_omarchy_verbatim` asserts the single
  call and that the module never runs `fc-list` itself.
- **install-core.2#22** (marker shape, local to this module): one marker, spelled once, behind
  `${HYPRCONF_STATE:-$HOME/.local/state/hyprconf}`. With a single site in the module there is no
  `applied`/`mark_applied` helper pair to add — the finding's de-duplication is satisfied by the
  split itself. The state directory stays hyprconf's own (not `omarchy-state set`), per the
  finding's own verdict.
- **install-system.0#2 / #3** (the packages file): the module ships `packages` with one name and
  one trailing `# why`, plus the one-line no-AUR pointer to AGENTS rule 3. The AbortOnFail
  paragraph, the hand list of Omarchy base packages and the Firefox/VS Code paragraph are not
  copied. The line reader keeps inline-comment stripping; the `_HYPRCONF_PKG_ADD` seam is gone —
  `omarchy-pkg-add` is a stubbed `omarchy-*` name in the `box` fixture, as final-layout says.

## Findings reported against, not landed

- **install-core.2#20** — "report: one marker per choice stays" (BRIEF decision 6, AGENTS rule 5).
  No sync/setup split: the module keeps `font-applied`, and keeps the retry the marker buys (a
  first run without the package writes no marker, so the next run finishes the job).

## Deliberate behaviour change from `stage_font`

`stage_packages` did **not** bow out without a TTY (AGENTS rule 6: "the packages stage does not —
a missing package then fails on sudo and the run dies there"). This module does: a missing
`otf-geist-mono-nerd` with `HYPRCONF_NO_SUDO` set or no terminal prints one pointer line and exits
0, which is the module contract in `final-layout.md`. A *failed* `omarchy-pkg-add` (sudo declined,
pacman error) still exits non-zero and the core loop reports `failed: font` — no font is set on
that run and no marker is written. **AGENTS rule 6's sentence needs rewording in the docs pass.**

## What to delete / rewire in the legacy tree

- `install.sh`: `stage_font` (the comment block and body, `install.sh:866-895`) and its call at
  `:1499`. Replace with the module call.
- `packages`: the font block (`packages:17-21`). The whole file, `stage_packages`
  (`install.sh:446-461`), its call in `main` (`:1492`) and the `_HYPRCONF_PKG_ADD` seam go once
  `terminal-kitty` and `shell-zsh` have taken the other four names — **shared with those two
  modules, not mine to remove alone**. The bootstrap sentinel `install.sh:1486`
  (`[[ -d $HERE/hypr && -f $HERE/packages ]]`) must be re-pointed at something that still exists
  (the core in final-layout tests `-d $HERE/modules`).
- `tests/unit/test_omarchy_install.py`: the "The system font" section, `test_the_font_family_goes_
  to_omarchy_verbatim` and `test_font_marker_waits_for_omarchy_font_set_to_succeed` (`:1085-1120`)
  — both re-land here as `test_the_family_goes_to_omarchy_verbatim` and
  `test_a_rejected_family_warns_writes_no_marker_and_is_retried`; `"omarchy-font-set"` in the stub
  list (`:185`) once no other stage calls it. `test_packages_file_lines_are_plain_package_names`
  is **shared**: either widen it to iterate `modules/*/packages` in `tests/test_scans.py`, or drop
  it — each module now pins its own shape (mine:
  `test_the_packages_file_holds_plain_package_names`). `docs/CONTRIBUTING.md:203` names that test
  as part of the mechanical floor and must follow it.
- `README.md`: the `font` stage row (`:78`) and the `otf-geist-mono-nerd` packages-table row
  (`:242`) become the module table's font row + this README. `:100` (set-once list) and `:398`
  (`omarchy font set <name>` in the revert block) are **shared lines** — leave the font mention
  only where the module table points.
- `AGENTS.md`: the "Font, default apps, terminal, idle" integration-map row loses its font half;
  rule 5's set-once list and rule 6's sudo-stage list are shared lines for the docs pass.
- `docs/CONTRIBUTING.md:12` (the `packages` tree line) — shared with the other two package modules.

## Cross-module facts

- `omarchy-font-set` appends `font_family` to `~/.config/kitty/kitty.conf`, creating the file if
  kitty is present (`bin/omarchy-font-set:33-40`). **terminal-kitty** owns that file's one
  `include hyprconf.conf` line and must keep tolerating a `font_family` line beside it; order does
  not matter to this module.
- The marker keeps the legacy name `font-applied`, so a machine that already ran the old
  `install.sh` will not have its font re-asserted after the split.
- The module never calls `omarchy-install-font`: it `exec`s a floating terminal
  (`bin/omarchy-install-font:20-21`), needs a graphical session and returns no status.

## Live verification (not done here — no live desktop from this agent)

1. `bash modules/font/install` on a box where the package is already in: `omarchy font current`
   prints `GeistMono Nerd Font`, the bar and kitty redraw (the setter runs `omarchy-restart-shell`
   and `pkill -USR1 kitty`).
2. A second run, and a run through the post-update hook (`--no-packages`): nothing printed beyond
   the module header, `~/.config/fontconfig/fonts.conf` unchanged.
3. `bash modules/font/install undo` then `omarchy font set 'JetBrainsMono Nerd Font'`: fontconfig
   and kitty go back, and the next install offers GeistMono again.
