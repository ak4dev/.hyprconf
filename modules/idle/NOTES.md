# modules/idle — notes for the integrator (delete this file)

## Findings landed

- **install-core.2#21** — `stage_idle` no longer re-implements `omarchy-shell-config`'s
  `commit()`. The module is `( source "$(command -v omarchy-shell-config)" && commit
  '.idle = ((.idle // {}) + { screensaver: 900 })' )`, the seam `bin/omarchy-bar:10` uses.
  The subshell is required (`bin/omarchy-shell-config:51` EXIT trap, `:9-12` `fail` → exit 1).
  The `refresh_shell_config` fallback to `omarchy-shell -q shell rescanPlugins` (`:14-18`)
  comes free; the distinct "no shell.json to edit" diagnostic is gone, as the finding said.
- **install-core.2#19** — the 11-line header is down to the rule-1/2 citation (no
  `omarchy commands --json` route, `omarchy-toggle-idle` is only stay-awake), the helper
  facts with file:line, why the subshell, and the one set-once sentence. Everything
  user-facing lives in `modules/idle/README.md`.
- **install-core.2#22** — moot here: one module, one marker, no boilerplate to factor out.
  `${HYPRCONF_STATE:-$HOME/.local/state/hyprconf}/idle-applied` keeps the legacy name, so an
  already-installed box does not re-apply.
- **install-core.3#1** — landed as its "source Omarchy's own helper" half rather than the
  hyprconf-local `shell_json_edit` helper: that finding's `do` argued against sourcing, but
  2#21's `do` and `final-layout.md` § "Where the three disagreed" (`idle.screensaver` row)
  settle it the other way, and the second read-modify-write it wanted to unify
  (`follow_center_anchor`) now lives in `modules/bar-clock`. Nothing shared is left to
  extract; each module carries the one edit it makes.

## Citation corrections (post-review pass)

- Two anchors were off and are now fixed everywhere (`install`, `README.md`, this file):
  the 150 s default is `shell/plugins/services/idle/Service.qml:17,21` (line 17 is
  `defaultScreensaverSeconds: 150`; 18 is `defaultLockSeconds`), and the no-deep-merge
  fact is `shell/shell.qml:73-88` (`applyShellConfig()` at 73, the "We do not deep-merge"
  comment at 74-75, `shellConfig = user || defaults` at 88). Both re-read in the installed
  4.0.3-1 tree. No other citation changed; gates re-run green.

## Not landed

- **install-core.2#20** (sync/setup split, no markers) — decision 6 in `BRIEF.md`: one
  set-once marker per user choice stays. The module keeps `idle-applied`.

## Delete / rewire in the legacy tree (dev v7.0.0 line numbers)

- `install.sh`: the `stage_idle` header + function, **lines 745-780**, and the `stage_idle`
  call in `main()`, **line 1500**. Nothing else in `install.sh` is idle-only. Two comments
  elsewhere refer to the stage by name and must be re-worded, not deleted, when their own
  code moves: **1162** (`follow_center_anchor`'s "deliberately NOT omarchy-shell-config's
  commit() the way stage_idle goes") and **1184** ("Same shape as stage_idle's
  warn-and-carry-on") — both belong to `modules/bar-clock`.
- `tests/unit/test_omarchy_install.py`: `test_screensaver_timeout_is_set_once` (**956-976**),
  `test_the_screensaver_edit_goes_through_omarchys_own_shell_config_helper` (**977-1001**),
  `test_a_shell_config_the_helper_refuses_leaves_no_marker` (**1002-1019**); the
  `SHELL_CONFIG_FAKE` transcription (**114-160**) and the two lines that install it
  (**237-239**) go with them — nothing else in the file uses it. The shipped-defaults
  fixture at **259-263** is used by other stages; check before removing.
- `README.md`: the idle table row (**line 79**) becomes the module-table row pointing at
  `modules/idle/README.md`; the revert block (**line 405**) currently says
  "`idle.screensaver` … stays at 900 s until you edit it" — that is no longer true, replace
  it with `bash ~/.hyprconf/modules/idle/install undo`.
- `AGENTS.md`: the integration-map row **35** ("Font, default apps, terminal, idle") loses
  its `shell.json` `idle.screensaver` + `omarchy-shell shell reloadConfig` half. There is
  **no** "`idle.screensaver` written with `jq`" deliberate-choices row left to delete — the
  foundation bugs step already removed it when `stage_idle` started sourcing the helper.
- `docs/CONTRIBUTING.md`: `grep -n idle` finds nothing idle-specific beyond the stage/test
  lists; re-check once the other modules land.
- No payload to move or delete: this module ships only `install`, `README.md`, `test_idle.py`.

## Live verification (not done — no live desktop touched)

1. `bash ~/.hyprconf/modules/idle/install` on a box whose `idle-applied` marker already
   exists: must print nothing and change nothing (verified hermetically; confirm on the box).
2. On a box WITHOUT the marker: confirm `~/.config/omarchy/shell.json` gains
   `idle.screensaver: 900` with `idle.lock` untouched, the running shell picks it up
   (`shell/shell.qml:134-143` watcher, plus the helper's `reloadConfig`), and the
   screensaver really starts at 15 min.
3. `install undo` then `omarchy restart shell`: the screensaver is back to 150 s
   (`shell/plugins/services/idle/Service.qml:17,21` default — the user file no longer
   carries the key and the shell does not deep-merge, `shell/shell.qml:73-88`).
4. First install on a machine with no `~/.config/omarchy/shell.json` at all: the run
   materialises one from `$OMARCHY_PATH/config/omarchy/shell.json` (`source_file():20-26`),
   key-sorted by `jq -S`. That is Omarchy's own behaviour but it is a visible new file —
   worth eyeballing once.

Non-hermetic check already run here (isolated `HOME`, faked `omarchy-shell`, REAL
`/usr/bin/omarchy-shell-config`): apply → `idle {lock: 300, screensaver: 900}`; second run
exit 0, no write; `undo` → `idle {lock: 300}`, marker gone.
