# modules/themes — notes for the integrator (delete this file)

## Findings landed

| id | how |
|---|---|
| `shell-misc.0#6` | Documentation half, per the judge: the directory stays in-tree (no second repository, no submodule, no new network touch — rule 8). README › Install alone tells a taker to copy `dracula/` to the root of a repo of their own, with the `omarchy theme install` citation (`omarchy-theme-install:24,32,56,63`) and the fact that it activates. The finding's other half — the stale "omarchy-theme-update skips a link" comment — was already corrected in the foundation phase (`install.sh:732-734` and `AGENTS.md:49` both cite `omarchy-theme-extras:12` now); the module carries that citation forward and adds the `omarchy-theme-update:5` half that reads it. |
| `shell-misc.0#7` | `light_foreground = "#f8f8f2"` deleted from the module's `dracula/colors.toml` (`omarchy-theme-color:223` derives exactly that — the theme sets no `colorN` key). `brown` and `dark_background` kept; `dark_background` is now named in the header with the reason (`:236` would derive a darker mix, and `default/themed/{neovim.lua,t3code.json,hermes.yaml}.tpl` read the key). Pinned by `test_colors_toml_omits_what_omarchy_derives_to_the_same_value`. |
| `install-core.3#6` | Wallpaper kept (judge's call); the table and its parser are gone. |
| `install-core.3#5` | The destination theme is the directory name: `backgrounds/gruvbox/gruvbox.jpg`, one glob loop, `[[ -f $f ]] || continue` because nothing sets `nullglob`. Adding or dropping a wallpaper is now a file operation with no code edit. |
| `install-core.3#4` | The "Omarchy scans two theme-keyed directories" fact has one home in the module — the `install` header, with both citations; the README carries the user-facing half and the test docstring points at it rather than restating the mechanism. |
| `install-core.1#16` | Moot as a shared helper under the module split (a module never sources anything). The rule itself is landed here: `mkdir -p` the parent, refuse a real directory with a message, `ln -sfn` only when the target differs. No `.stock` backup: the refused case is a *directory*, and the module never overwrites one. |
| `install-core.2#17` | Landed as modularity, not staleness. The comment in `modules/themes/install` cites `theme_came_from_a_repo` (`omarchy-theme-set:204-208`) and the `cp -r` branch (`:275`) — written fresh against 4.0.3-1, which is what it was verified on, so AGENTS' "provenance stays as written" is not in play for this new file. `omarchy theme remove dracula` is the undo for both shapes. |

## Beyond the findings

- **Undo is safer than the legacy README line.** `rm ~/.config/omarchy/backgrounds/gruvbox/gruvbox.jpg` (README:396) removed whatever was at that path; the module removes it only when the bytes are still ours, and removes the link only when it still points into this module. Both are tested.
- **No `omarchy-theme-set` anywhere**, asserted on the code, not on a run.
- The module calls exactly one Omarchy command, `omarchy-theme-remove`, and only from `undo`.

## What to delete / rewire in the legacy tree

- `install.sh`: `stage_theme` (716-743) and `stage_backgrounds` with its comment header (831-864), plus their calls at :1496 and :1498; the module replaces both.
- Payload: `themes/` and `wallpapers/` (copied, not moved — `modules/themes/dracula/` and `modules/themes/backgrounds/gruvbox/gruvbox.jpg`; the copy of `colors.toml` has the `light_foreground` line removed and a longer header, so take the module's version, not a re-copy).
- `tests/unit/test_omarchy_install.py`: `PAYLOAD` entries `"themes"` and `"wallpapers"` (:332-333), `test_theme_is_installed_as_a_symlink` (:922), `test_a_user_installed_theme_directory_is_left_alone` (:941) and `test_wallpapers_are_seeded_where_omarchy_looks_and_then_left_alone` (:1069) with the `# Wallpapers` banner above it (:1063-1066). Keep `test_never_switches_the_active_theme` (:933) only if it still scans `install.sh`; the module's own copy of that assertion is `test_installing_never_activates_a_theme`.
- `README.md`: row `theme` (:75), row `backgrounds` (:77), the `themes/`+`wallpapers/` names in the payload line (:117), and the two revert clauses (:394 `rm ~/.config/omarchy/themes/dracula`, :396 the gruvbox lines) — the module table row replaces all of it.
- `docs/CONTRIBUTING.md`: tree lines :39 (`themes/dracula/`) and :41 (`wallpapers/`).
- `AGENTS.md`: the Theme row of the integration map (:34) loses its `themes/dracula` half, and the deliberate-choices row "`themes/dracula` symlinked … not copied" (:49) moves to this module's README (the reason is already written there).

## Cross-module facts

- `modules/firefox-theme` owns the other half of AGENTS' Theme row (`themed/userChrome.css.tpl` + the theme-set hook). Nothing is shared between them: this module never renders a template and never runs `omarchy-theme-refresh`.
- Nothing else writes `~/.config/omarchy/themes/` or `~/.config/omarchy/backgrounds/`.
- `omarchy-theme-remove` must stay covered by the box's fake list — it is derived from the tree, and this module is the only file that names it.

## Live verification (not doable hermetically)

1. `omarchy theme set dracula` on the box, then `omarchy theme update` — the linked theme must be skipped, not pulled (`omarchy-theme-extras:12`).
2. `SUPER+CTRL+SPACE` with gruvbox active — `gruvbox.jpg` appears beside Omarchy's five.
3. `omarchy theme remove dracula` on the live link — the checkout must survive (`rm -rf` on a symlink).
4. Re-render check after dropping `light_foreground`: `omarchy theme set dracula` and confirm nothing in `~/.local/state/omarchy/current/theme/` changed against the old palette (the key derives to the same `#f8f8f2`).
