# modules/hypr — notes for the integrator (delete this file)

## BLOCKED — one change in here needs the USER's own yes, not a reviewer's (hypr.0#7)

The module removes five hotkeys that are daily muscle memory. The finding's own `do` says
"User's call (muscle memory)", so **do not commit this module until the user has said yes in
their own words**; the audit evidence is sound but it is a preference, not a defect.

Removed from `bindings.lua` (all five are a second key for something Omarchy already binds):
`SUPER+D` → `omarchy-menu toggle` (Omarchy: `SUPER+SPACE`, `default/hypr/bindings/utilities.lua:1`);
`SUPER+SHIFT+V` → `omarchy-menu-clipboard`, whose whole body is `omarchy-shell shell toggle
omarchy.clipboard` (`/usr/bin/omarchy-menu-clipboard:6` = Omarchy's `SUPER+CTRL+V`,
`bindings/clipboard.lua:48`); `SUPER+L` and `SUPER+SHIFT+Escape` → `omarchy-system-lock`
(Omarchy: `SUPER+CTRL+L`, `utilities.lua:126`); `SUPER+SHIFT+BACKSPACE` →
`omarchy-hyprland-monitor-internal toggle` (Omarchy: `SUPER+CTRL+Delete`, `utilities.lua:32`).
Two of them also gave a stock key back: `SUPER+L` → "Toggle workspace layout" (`tiling.lua:13`),
`SUPER+SHIFT+BACKSPACE` → "Toggle window gaps" (`utilities.lua:20`). The other three displaced
nothing (`grep -rn` over `default/hypr/bindings/` finds no `SUPER+D`, `SUPER+SHIFT+V` or
`SUPER+SHIFT+Escape` on 4.0.3-1).

**If the user says yes:** commit as `feat(hotkeys)!` with a `BREAKING CHANGE:` footer naming the
five keys, and delete the matching README rows in the legacy tree (see Delete/rewire).
**If the user says no:** one hunk, no other file moves —
1. put back in `bindings.lua`, with a one-line comment each (hypr.0#7's fallback: "If kept, cut
   each comment to one line"), the five binds as they read in the legacy `hypr/bindings.lua:45,
   125, 138-139, 145` — note `:139` was a bare `o.bind`, which must come back as `rebind(...)`
   so hypr.0#9 stays landed;
2. drop `'" + D"'`, `'" + L"'`, `'" + SHIFT + V"'`, `'" + SHIFT + Escape"'` and
   `'" + SHIFT + BACKSPACE"'` from the forbidden tuple in `test_hypr.py` (the
   `omarchys-own-binds` case) and trim its comment to the nine keys that remain;
3. trim `bindings.lua`'s "Left to Omarchy on purpose" comment back to the first sentence.
Nothing in `install`, the tools, the README or the other two suites depends on it.

## Gates

Built against Omarchy 4.0.3-1 (Hyprland 0.56.2). `pytest modules/hypr -q` → 38 passed;
`shellcheck --severity=warning` + a `--include=SC2086` pass clean on `install` and both tools;
`bash -n` clean; `luac -p` clean on all six `.lua`; `ruff check` / `ruff format --check` clean;
`tests/unit/test_no_pii.py` still green with the module in the tree; `git status --short` shows
only `?? modules/`. Also proved by hand: the folder copied to a scratch dir and run under
`env -i` installs; a second run leaves an identical inode/mtime/size/link snapshot and records
no command; `undo` restores the three stock templates with no `.bak`, and is a clean rc=0 no-op
on a machine that never installed.

## Findings landed

| id | what landed |
|---|---|
| hypr.0#6 | the three overrides are cmp-gated `install -m 644` copies; a pre-module symlink is removed first. No refresh guard, no stock cache, no `.stock`. |
| hypr.0#4 | `unbind_keycode()` and its 19 call lines are gone: `rebind()` does the keycode unbind itself (`KEYCODE` completed to 0-9 + minus/equal). The pairing test is replaced by one that pins the fold. |
| hypr.0#8 | the ten workspace key pairs are a table-driven loop, the shape `default/hypr/bindings/tiling.lua:20-25` uses. "One bind per line" is no longer true of `bindings.lua` — drop it from README/AGENTS (it is no longer true of the presets either, see #12). |
| hypr.0#7 | **breaking, and BLOCKED above**: the five duplicate hotkeys are gone from `bindings.lua` and pinned as forbidden in `test_hypr.py`. |
| hypr.0#9 | moot: the single bare `o.bind` was the `SUPER+SHIFT+Escape` lock, removed by #7. Nothing outside `rebind()` binds now; the tests keep the `(rebind\|o\.bind)` alternation on purpose (it catches a future bare one). |
| hypr.0#10 | `input.lua`'s seven-line gesture comment is four lines, keeping the two load-bearing facts. |
| hypr.0#11 | decided **keep `laptop`, cut it to the delta**: `eDP-1` and the `output = ""` catch-all were `config/hypr/monitors.lua:8` verbatim (`preferred/auto/auto`), which this toggle loads after — so they are gone and only the three externals at `scale = 2` remain. Not deleted outright: `stock` is *not* equivalent (it drops the forced scale and the auto-right/auto-left placement), and removing a preset name is a breaking change on a machine that uses it. `test_the_laptop_preset_states_only_what_stock_does_not` pins the new shape. |
| hypr.0#12 | `looknfeel.lua` 91 → 72 lines: the 18-line Steam essay is 3, the header and gaps notes are shorter. Kept whole: the shadow's theme-clobber warning and the `smart_split` paragraph — the two facts with no second home. |
| hypr.0#14 | landed as the module itself plus the README's tool-free sentence ("copy one there and reload") and **one** resolution rule (see #10 below). |
| hypr.0#16 | the kitchen 3070 history note is gone; the bedroom `119.88` note stays (it is the rationale for the odd literal, not history). |
| hypr.0#3 | bind rationale cut to the lua, one home each: the `{ omarchy = … }` idiom two lines, the resize `relative = true` why one paragraph (it is in no other file now that `docs/hyprland-reference.md` goes), the gaps and screenshot notes two lines each. Every out-of-module `README.md > …` pointer is gone from the payload — see Delete/rewire. |
| hypr.0#15 | the `desc:`-not-connector *why* has one home in the module README's third bullet; each preset keeps one header line and drops the catch-all paragraph. The 3070→5090 narrative is gone from the preset and from the test docstring. |
| hypr.0#17 | `test_config_exec_targets.py` is merged into `test_hypr.py` as `test_every_hyprconf_command_bound_ships_in_the_module`, on that file's full-line `_code()` stripper (one stripper in the module, not two), carrying the silent-no-op sentence. |
| hypr.0#18 | `test_the_hotkey_tools_are_bound_by_name` is not carried over. |
| hypr.0#19 | `test_natural_scroll_is_the_default` is not carried over (the README table is the contract). |
| hypr.0#20 | the deltas test is the shadow rule (`enabled` present, `range\|color\|render_power` forbidden) plus the `hl.gesture(` presence check; the nine-name blacklist and the value pins are gone. |
| hypr.0#21 | the Steam test is six lines over `looknfeel.lua` alone (tile, then the Friends-List float, in that order, and no class-wide re-float); the glob over the other five `.lua` is gone. |
| hypr.0#22 | the two blacklist tests are one test parametrized over `(scope, forbidden)` — Omarchy's own binds against the bind lines, the ten XF86 names against all code so an unbind is caught too. Its comment now cites `default/hypr/bindings/media.lua:2-9,24-29` and `bin/omarchy-audio-output-volume:86` / `bin/omarchy-brightness-display:87` instead of a root-README section. |
| hypr.0#23 | the launcher-idiom test is key-agnostic: the four `{ omarchy = … }` values must appear somewhere in the binds, and no launcher or app binary anywhere else. |
| hypr.0#24 | the three preset tests are one, parametrized over `DESK_PRESETS`: `desc:`-or-catch-all outputs, `desc:` workspace rules, the catch-all present, and both serial shapes rejected. |
| tools-hypr.0#1 | `_get_gap` is one `jq` expression: `.css // "0" \| split(" ")[0] \| tonumber`. The `custom`/`int` branches and their two test cases are gone. |
| tools-hypr.0#4 | one folder: tool + presets + install + README + tests. `stage_monitors`' seeding moves in (still seed-if-absent, now globbed). |
| tools-hypr.0#5 | the toggles-seam mechanism has one home: the tool's header, summarised once in the module README. |
| tools-hypr.0#6 | the truecolor palette and `log_step`/`log_ok`/`log_warn` are gone; `die()` and `osd()` remain (a plain `printf` to stderr plus Omarchy's own channels). |
| tools-hypr.0#7 | the `Presets:` line is derived from `~/.config/hypr/*Monitors*.lua`, so a new preset needs no edit to the tool; `-h/--help` exits 0, a bare run exits 1. |
| tools-hypr.0#8 | the path-traversal whitelist is gone — and cannot regress: `$1` is matched against labels derived from the directory listing and is never pasted into a path. `test_a_preset_name_can_never_name_a_file_outside_the_config_dir` pins that (rule 8: the guard was removed *and* the hazard structurally removed, not just dropped). |
| tools-hypr.0#9 | `stock` is `omarchy-hyprland-toggle hyprconf-monitor-preset off` (bin/omarchy-hyprland-toggle:17,30-32,54), not a hand-rolled rm+reload; the `omarchy` alias is gone with it, and the tool says in one line why the `on` half cannot be reused (`:18,21-27` refuses a source outside Omarchy's own tree). The undo test asserts the toggle call, not a `hyprctl reload` count. |
| tools-hypr.0#10 | one resolution rule instead of two patterns tried in order, and the error names the preset, not a filename that may not be the one it looked for. **Filenames not renamed** — see Deviations. |
| tools-hypr.0#12 | the `sed`-over-Lua walk is `hyprctl workspacerules -j \| jq`, filtered to a non-empty monitor and a numeric workspace. Verified on the installed tree: Omarchy's defaults declare no `hl.workspace_rule` at all and the one it writes at runtime carries a layout and no monitor (`omarchy-hyprland-workspace-layout-toggle:17`). The "one statement per line, in that exact form" convention dies with it. |
| tools-hypr.0#13 | the 43-line `/sys/class/drm` + text-`hyprctl monitors` + `for delay in 1 2 3` block is one unconditional wake, the shape `omarchy-hyprland-monitor-internal:12-14,22` uses for its own user-initiated enable. **Cannot be verified here** (see Live verification). |
| tools-hypr.0#14 | the fake `hyprctl`'s `keyword` branch and the docstring clause about it are gone from `test_gaps.py` (the tool never makes that call). |
| tools-hypr.0#15 | four step cases (`+` mid, `+` from 0, `-` mid, `-` clamped at 1), the `field` parameter gone with the `custom` case, and the two usage tests are one parametrized over `("sideways", None)`. |
| tools-hypr.0#16 | `test_no_inline_python` is not carried over (AGENTS' deliberate-choices table is where that rule lives). |
| tools-hypr.0#19 | every preset-tool test is in `modules/hypr/test_monitor_preset.py`, on the `box` fixture, with no installer harness. |
| tools-hypr.0#20 | no `cfg_src` and no per-run copy: the helper writes the presets straight into the box's own `~/.config/hypr`, and the runner takes the box. |
| tools-hypr.1#1 | the "an edit survives re-selecting it" case is folded into the copy test (edit the seeded file, re-run, assert the toggle holds the edited bytes); the separate test is gone. |
| install-core.3#8 | no duplicated `mkdir`; one `mkdir -p` for both `~/.config/hypr` and `~/.local/bin`. |
| install-core.3#9 | the 14-line seeding essay is two sentences in the install header. |
| install-core.3#10 | the seed list is a glob (`"$dir"/*Monitors*.lua`) in the install and in the undo — **with the `[[ -f $f ]] || continue` guard the finding prescribes**, since nullglob is unset; `test_a_folder_with_no_preset_installs_the_rest` pins it (without the guard the run dies `install: cannot stat …/*Monitors*.lua` after the overrides and before the tool links). The undo loop needs no guard: an unmatched pattern reaches `rm -f` as a literal path. |
| install-core.3#11 | one idiom per intent: cmp-then-`install` for the overrides, seed-if-absent for the presets. Nothing is rewritten unconditionally. |
| install-core.3#14 | the tools are `ln -sfn`ed behind a `readlink` guard (so a re-run writes nothing); no `@HYPRCONF_DIR@`, no sed render, no tmp+cmp+mv. |
| install-core.3#16 | the "not on PATH" warning is gone (`default/bash/env-bootstrap:37-40` guarantees it). |
| install-core.1#16 | one link shape, one guard; no `.stock` copies anywhere in this module. |
| install-core.1#10, #11, #12, #17, #20 | all moot under BRIEF decision 1: with copies there is no `restore_clobbered_override`, no `~/.local/state/hyprconf/stock/` cache, no token test, no double execution per run and no derived pre-pull loop to explain. #11 is landed as its Option A. |
| install-core.1#18 | narrowed to nothing to back up: the overrides are copies, and the one `[[ -L ]] && rm -f` is the pre-module migration. A user's own symlink at `~/.config/hypr/bindings.lua` is removed (its target file is never written or deleted), which `test_a_pre_module_symlink_is_replaced_by_a_file` pins; `undo` then leaves Omarchy's stock template there. The finding's other two sites (fastfetch, `.p10k.zsh`) belong to those modules. |

## Findings carried to the integrator — they touch files this phase may not edit

- **hypr.0#13** (doc-only, the one finding in the bundle with nowhere to land inside the module).
  `looknfeel.lua:22` (legacy `hypr/looknfeel.lua:24`) sets `inactive_opacity = 0.8`, which
  Omarchy's own window rule multiplies — so no table row stating "0.8 vs 1" tells the whole
  truth. Add one clause to the look'n'feel row wherever it ends up (today root `README.md:231`;
  the ≈130-line README after the docs pass) — the clause, verbatim:

      0.8 — Omarchy tags every window `+default-opacity` (default/hypr/windows.lua:6) and applies
      `opacity = "0.985 0.96"` to the tag (:25), so the effective inactive alpha is ~0.77, while
      the apps Omarchy takes out of the tag with `tag = "-default-opacity", opacity = "1 1"`
      (apps/steam.lua:3, apps/qemu.lua:1) come out at exactly 0.8.

  Citations re-read on 4.0.3-1 today: the rule **is at `windows.lua:25`** (`:24` is the comment
  above it, and the finding's own `:25` is right — the review note that said `:24` is wrong).
  Do **not** take the finding's second half (re-expressing it as `o.window({ tag =
  "default-opacity" }, …)`): that restates Omarchy's own `0.985` and breaks deltas-only.
  Live-verification caveat: the multiplier semantics are Hyprland's documented window-rule
  behaviour but are not verifiable on this box (no Hyprland source, no session) — compare a
  browser window with a `steam.*` one before writing the number, and drop the "~0.77" if it
  does not hold.

## Deviations (decide or carry forward)

- **Preset filenames kept** (`pcMonitors.bedroom.lua`, `pcMonitors.kitchen.lua`,
  `laptopMonitors.lua`) against tools-hypr.0#10's `<label>Monitors.lua` proposal:
  `final-layout.md`'s module tree names these three, and a rename orphans an already-seeded,
  possibly edited file under rule 5 (seed-if-absent would put a fresh default beside it under the
  new name). The *concept* is gone from the tool — one derivation, not two patterns — so a rename
  later is a pure file move plus a migration.
- The module calls `hyprctl reload` only when an override actually changed; the core's own
  trailing `hyprctl reload` in `main()` is now redundant for hypr.
- The payload names no file outside the module any more (hypr.0#3/#15): the four surviving
  `README.md` mentions in `bindings.lua` and the presets all read "README.md in this folder", and
  the test that cited "README › Hotkeys" now cites Omarchy's own media binds. Nothing in the
  module breaks if the root README's Keybindings / Look'n'feel / Monitor presets sections are
  folded into the ≈130-line module table, as `final-layout.md:268` plans — but hypr.0#13 above
  needs *a* home for the look'n'feel row wherever that lands.

## Delete / rewire in the legacy tree

- `install.sh`: `stage_hotkeys`, `stage_looknfeel`, `stage_monitors`, `link_hypr_override`,
  `restore_clobbered_override` (and the `~/.local/state/hyprconf/stock/` cache it writes), the
  derived pre-pull repair loop at the top of `stage_pull`, and their `main()` calls. `stage_bin`
  stops installing `hyprconf-gaps` / `hyprconf-monitor-preset` (it goes entirely once every tool
  module has landed). `backup_before_link` stays until `stage_fastfetch` moves — its other caller.
  `main()`'s closing line still says "SUPER+D still opens Omarchy's menu": false now, SUPER+D is
  unbound (Omarchy's menu is SUPER+SPACE) — and it is the one line to revisit first if the user
  says no to hypr.0#7.
- Payload: `hypr/` (all six `.lua` and `hypr/README.md`), `bin/hyprconf-gaps`,
  `bin/hyprconf-monitor-preset` — all copied here, none moved.
- Tests: `tests/unit/test_hypr_overrides.py`, `tests/unit/test_monitor_preset.py`,
  `tests/unit/test_gaps.py` (all three superseded). In `tests/unit/test_omarchy_install.py`: the
  `PRESETS` tuple, the preset tests (reaches-every-preset, seeded-once, the two workspace ones, the
  refresh-never-reaches-a-preset one), `LINKED_OVERRIDES`, the nine clobber-guard tests, the
  `_switch` helper, and the two hypr tools in the shipped-tool-lands-on-path list.
- `README.md`: the five removed hotkey rows (`:171`, `:200`, `:202`, `:203`) and both "Displaced"
  rows (`:219`, `:220`) — **only once the user has said yes to hypr.0#7**; the hotkeys /
  look'n'feel / monitors stage rows; the refresh-guard + stock-cache paragraph under Sync; "Dark
  outputs get a `dpms` wake retry."; "one bind per line"; the `@HYPRCONF_DIR@` clause for these two
  tools; the Reverting-to-stock lines for the hypr symlinks (`bash modules/hypr/install undo`
  replaces them). **Add** hypr.0#13's clause to the look'n'feel table row (above). Worth one line:
  a machine installed before the split keeps `~/.config/hypr/*.lua.stock` and
  `~/.local/state/hyprconf/stock/` — both are now dead and can be deleted.
- `AGENTS.md`: the "Live files — the symlink hazard" section; the deliberate-choices symlink row
  (→ "hypr copied, `hyprconf hypr` after an edit"); the `omarchy refresh` clobber quirk ("Keep the
  links, the guard and the cache"); the `is_lit` unseamed-read sentence under Scripts (that read is
  gone); the integration-map rows for Hyprland binds / hotkeys / monitor presets / tools. Rule 6's
  "never overwrite a seeded preset" and "never touch `monitors.lua`" both still hold here.
- `docs/CONTRIBUTING.md`: the `hypr/` and `bin/` tree rows, the three test-file rows, and any seam
  list naming `is_lit`.

## Cross-module facts

- `bindings.lua` binds `hyprconf-gaps` and `hyprconf-monitor-preset` by name; both ship here, so no
  other module may ship a tool with those names. A missing target is a silent Hyprland no-op.
- No packages, no sudo, no TTY, no state marker — the module is order-free anywhere in the loop and
  needs neither `HYPRCONF_NO_SUDO` nor `_HYPRCONF_ASSUME_TTY`.
- The root `conftest.py` derives its `omarchy-*` fakes from shipped bash/Lua, so
  `omarchy-refresh-config`, `omarchy-hyprland-toggle`, `omarchy-osd` and
  `omarchy-notification-send` are faked for every suite the moment this module is in the tree.
- `test_gaps.py` / `test_monitor_preset.py` share basenames with the legacy suites; both trees
  import cleanly today only because `tests/` and `tests/unit/` are packages. Delete the legacy pair
  in the same commit that wires this module in.

## Live verification (none of it possible on this laptop)

1. **The dpms wake (tools-hypr.0#13)** — the retry loop existed for an observed aquamarine/nvidia-open
   failed-CRTC bug on the two-NVIDIA desktop, and a single unconditional wake replacing it is
   unverified. On that machine: `hyprconf-monitor-preset bedroom`, then `kitchen`, then back, with a
   previously disabled output in each target. If an output stays dark, restore a retry — but read the
   names with `hyprctl monitors -j | jq -r '.[].name'`, never `/sys/class/drm` or the text format.
2. **The workspace re-homing (tools-hypr.0#12)** — `hyprctl workspacerules -j` returns
   `{workspaceString, enabled, monitor}` (verified live by the audit on 0.56.2), but whether a
   `desc:<make> <model>` monitor survives that round trip is unverified. On the desktop, switch
   presets and confirm workspaces 1-6 land on the right panels; both a `desc:` and a resolved
   connector are valid `hl.dsp.workspace.move` selectors, so either answer is fine — no move at all
   is not.
3. **The copies** — `omarchy refresh hyprland`, then `hyprconf hypr`: the live config must come back
   and the checkout must never have changed (`git status` clean throughout).
4. **The keycode fold (hypr.0#4)** — after the first install, `hyprctl reload && hyprctl configerrors`,
   then check `SUPER+1..0`, `SUPER+SHIFT+1..0`, `SUPER+SHIFT+=`, `SUPER+SHIFT+-` and `SUPER+SHIFT+4`
   each fire once (a missed keycode unbind shows up as Omarchy's action firing too).
5. **The five removed hotkeys (hypr.0#7)** — the user's call, on their own hands. See BLOCKED above.
6. **The opacity clause (hypr.0#13)** — compare a browser window with a `steam.*` one before writing
   "≈0.77" into the README row; the multiplier is documented Hyprland behaviour, not measured here.
