# modules/bar-clock — notes for the integrator (delete this file)

Built additively: nothing outside `modules/bar-clock/` was touched, and
`plugins/hyprconf-clock/` was **copied**, not moved.

Gates run here: `pytest modules/bar-clock -q` (20 passed, 0.6 s, no skips on
this box — two tests skip where Omarchy is absent), `shellcheck
--severity=warning` and `--include=SC2086` on `install`, `bash -n`,
`ruff check` + `ruff format --check`, `qmllint --bare` on the QML,
`node --check` on `plugin/Model.js`.

## Findings landed

| id | what landed |
|---|---|
| plugins-bar.0#14 | `plugin/Model.js` trimmed from 296 lines to 89: the nine declarations `BarWidget.qml` calls (`MS_PER_DAY`, `CLOCK_FORMATS`, `VERTICAL_CLOCK_FORMATS`, `clockFormats`, `clockFormatRing`, `nextClockFormat`, `isoWeekLiteral`, `pad2`, `isoWeek`), verbatim. **Evidence for dropping the calendar half** (the judge left the file whole): a QML document resolves `import "Model.js"` against its own directory, so the stock `Panel.qml` — loaded by absolute `file://` URL out of `$OMARCHY_PATH` — reads Omarchy's Model.js, never ours. Verified live under Qt 6.11.2, not from docs: a `Panel.qml` in dir B loaded from a `Main.qml` in dir A got **B's** Model.js (`qml` exit code carried the answer). The finding's hardcoded-`file://`-import variant was correctly rejected by the verifier and is not used. `test_model_js_is_omarchys_label_math_and_only_that` compares each kept declaration to the installed stock file, so drift in the label math still turns red; the dead calendar math no longer can. |
| plugins-bar.0#17 | `plugin/README.md` is the single home for the two-step undo: the two commands kept, the eight lines of FileView prose cut to one clause. The module README's Undo section points at `install undo`. |
| plugins-bar.0#9 | The "with the hyprconf overlay installed…" paragraph and the `omarchy plugin remove` backup prose are gone from `plugin/README.md`; the remove/disable behaviour is one sentence. "Keeping it current" is gone — the recipe lives in `BarWidget.qml`'s header. |
| plugins-bar.0#12 | `BarWidget.qml`'s header stays the single technical home of the three deltas; nothing was added anywhere else. The install's comment carries only the seam citations and the set-once reasoning. |
| plugins-bar.1#1 | `plugin/manifest.json` `version` frozen at `1.0.0` (nothing reads it; Omarchy's own plugins never move theirs). `test_the_manifest_claims_the_stock_clock_slot` pins it with the why. |
| install-core.4#5, #15 | The four plugin stages' shared machinery is gone from this module: one 137-line self-contained `install`, no `stage_*`, no 28-line stage comment (the facts live in `plugin/`'s header and READMEs). |
| install-core.4#9 | Symlink instead of the staged copy: `sync_plugin_dir`, `dir_modes` and the exec-bit self-heal do not exist here. A `.git` checkout is left alone; a real folder is moved aside once as `.hyprconf.clock.bak.<UTC ts>` (omarchy-plugin-remove:106's shape). |
| install-core.4#7, #8 | One rescan per run (`omarchy-shell shell rescanPlugins`), not two, and **no** `omarchy-restart-shell` fallback — a widget sync can no longer bounce a live desktop's shell. |
| install-core.4#11 | `wait_for_swap` and the `_JQ_IDS` global are gone. The one wait that guards the anchor read-modify-write is `settled()`, and it is skipped entirely when there is nothing to wait for. |
| install-core.4#12 | The dangling-anchor repair runs on **every** run with the narrow guard the verifier asked for: the stale id must be on no bar section *and* on no installed plugin, and `hyprconf.clock` must really be on the bar. An anchor on a widget the user merely disabled is left alone (tested). |
| install-core.4#13 | The anchor write is an `if`, not a `&& mv` tail: a failed write warns on stderr, removes its tmp, and never reports success or kills the run (tested by blocking `shell.json.tmp` with a directory). |
| install-core.2#7, #22 | No "already …" narration and no marker boilerplate: one marker, one guard, silence in the steady state. |
| test-install-a.2#5, #6, #7, #8, #10, #14, test-install-a.2#1 | `test_bar_clock.py` is 20 tests on the `box` fixture: no README-prose lint, no `test_clock_widget_id_carries_no_username`, no 70-line `SHELL_MODEL`, no full-installer run to validate a folder, and the duplicated anchor test replaced by three that exercise the guard (dangling / user's own / not-on-the-bar). |

## Findings NOT landed

- **plugins-bar.0#15** (report only, as the brief says): Omarchy 4.0.3's own
  `shell/plugins/panels/clock/BarWidget.qml:112-114` still hardcodes
  `precision: SystemClock.Minutes`, so the module is still needed. The upstream
  ask — a `precision`/`seconds` setting on `omarchy.clock` — would delete this
  whole module and leave one `omarchy bar set omarchy.clock format` line. That
  is a request to file upstream, outside this repo; nothing here waits on it.
- **plugins-bar.0#8** (the 404 install URL) was already fixed in the working
  tree before this module was built; `plugin/README.md` keeps the working
  by-hand path, repointed at `modules/bar-clock/plugin`.
- **plugins-bar.0#13** (drop the moduleName forward): the header already says
  it is a back-compat shim for pre-4.0.3 installs and costs two lines. Kept —
  the plugin is meant to install on a stranger's box of unknown vintage.
- **plugins-bar.1#10/#11/#12/#13/#15/#16/#17/#18** are `tests/`-side findings
  for the integrator's `tests/test_scans.py` / `test_plugins.py` pass, not this
  module: the clock's share of them is already discharged here (the parity
  test, the qmllint parse and the implicit-size rule live in
  `test_bar_clock.py`; the source-grep duplicate of the parity test is gone).

## What to delete or rewire in the legacy tree

1. `install.sh`: `stage_clock` (:1238-1263) and its call in `main()` (:1507);
   `wait_for_shell_json` (:1113-1123), `_JQ_IDS` (:1125), `wait_for_swap`
   (:1130-1133), `follow_center_anchor` (:1165-1195) and `set_clock_format`
   (:1198-1206) go with it — they have no other caller.
   `activate_plugin_copy`, `enable_plugin_once`, `sync_plugin_dir`,
   `dir_modes`, `reload_plugins` and the `_HYPRCONF_PLUGIN_WAIT` seam (:62-65)
   are **shared with the other three plugin stages** — delete them only once
   `bar-workspaces`, `bar-active-window` and `bar-resources` have landed too.
2. `plugins/hyprconf-clock/` — the copy this module was built from. Delete
   after wiring, and drop the folder from `PAYLOAD` in
   `tests/unit/test_omarchy_install.py`.
3. Tests: `tests/unit/test_omarchy_install.py` —
   `test_the_clock_copy_is_enabled_and_formatted_once` (:1948),
   `test_the_documented_clock_revert_undoes_what_the_stage_applied` (:1977),
   `test_shell_json_edits_wait_for_the_shells_asynchronous_writes` (:1803) with
   its `SHELL_MODEL`, and the four anchor tests (:2094-2166) are all covered
   here. `tests/unit/test_plugins.py` —
   `test_clock_plugin_tracks_omarchys_stock_clock` (:292, one of the two CI
   skips) and `test_the_documented_clock_revert_names_both_undo_steps` (:595)
   move here; `test_installed_plugins_pass_omarchy_plugin_validate` (:488)
   becomes per-module (`test_the_installed_link_passes_omarchy_plugin_validate`
   here).
   **AGENTS' "exactly two tests skip in CI" line needs rewriting**: this module
   alone carries three tests that need the installed Omarchy — the validator,
   the `BarWidget.qml` parity diff and the `Model.js` subset diff — and each
   further plugin module adds its own. The rule that still holds is "every skip
   in CI is a named needs-the-installed-Omarchy test"; `-rs` names them.
4. `README.md`: row 86 (the clock stage), row 140 (the widget row), the
   sentence at :145 about the byte+mode sync (now a link), and the clock half
   of Reverting to stock (:382-387) — replace with a pointer to
   `modules/bar-clock/README.md` and `modules/bar-clock/plugin/README.md`.
5. `AGENTS.md`: the Clock row in the integration map, the deliberate-choices
   row "`hyprconf.clock` shipped as `plugins/hyprconf-clock` … synced every
   run" (the mechanism is now a symlink), and the `omarchy plugin clone`
   quirk's `follow_center_anchor` sentence. The layout's planned quirk line —
   "a symlinked plugin folder needs an explicit rescan" — belongs there now.
6. `docs/CONTRIBUTING.md`: the tree line at :35 and the `test_plugins.py`
   description at :84-85.

## Cross-module facts

- The three other plugin modules are this one minus the format and the anchor.
  If they copy anything from here, copy `anchor()`/`on_bar()` too or drop them;
  a module must run from its own directory alone.
- The module needs `jq` and Omarchy's own commands only — no packages, no
  sudo, so no `HYPRCONF_NO_SUDO` or TTY gate. It never prompts, so
  `OMARCHY_UPDATE_LOGGED` is irrelevant to it.
- **For `tests/test_core.py`**: a run of every module with the shared fakes
  (`omarchy-plugin-list` exits 0 printing nothing) makes this module sit
  through its 2 s discovery wait plus a 2 s settle, because a fake that answers
  with nothing looks like a slow shell rather than an absent one. Stub
  `omarchy-plugin-list` to `exit 1` (the real command's no-shell behaviour) or
  to list the ids — see `shell()` in `test_bar_clock.py` for a model of the
  live shell that keeps the whole file at 0.6 s.
- Marker name unchanged: `~/.local/state/hyprconf/clock-applied`, so an
  existing box does not re-apply.

## Deviations from the reference `install` in final-layout.md

1. **A bounded wait instead of `sleep 1`** before the anchor read-modify-write
   (`settled()`, 40 × 0.05 s — Omarchy's own bound). Reason: the miss is
   unrecoverable behind the set-once marker, the poll returns as soon as the
   write lands, and it is skipped when `omarchy-bar set` failed. This is what
   install-core.4#6's verifier note asked to keep.
2. **The anchor block moved out of the marker entirely**, so the stock →
   clone follow also re-runs: if the settle ever times out, the next run
   finishes the job instead of leaving the bar off-centre for good. It only
   ever writes an anchor while `hyprconf.clock` is on the bar — with the
   reference's unconditional follow, a dumb-fake run (enable returns 0, no swap
   lands) pointed the anchor at a widget the bar did not carry.
3. **The dangling test is narrower** than the reference's `! on_bar "$a"`:
   also `gone "$a"` (on no installed plugin, and only when a shell answered).
   install-core.4#12's verifier: a bare off-the-bar test would silently
   re-point an anchor the user aimed at a widget they merely disabled.
4. `[[ … ]] && cmd` statements that would leave a non-zero status or read
   badly are written as `if` blocks.

## Live verification still owed (nothing here can prove it)

1. The widget under the 4.0.3 `PluginBarApi` / `PluginShellApi` facades:
   `omarchy restart shell`, then the label ticks seconds, right-click cycles
   formats and the choice persists, the calendar opens and a week-start change
   is written under `hyprconf.clock` (the panel is Omarchy's own file, so this
   also proves delta 2 and the Model.js trim in the running shell).
2. Enable / disable / `omarchy plugin remove` against the **symlinked** folder,
   and that a `git pull` in the checkout reaches the bar after this module's
   rescan.
3. This laptop's own `~/.config/omarchy/shell.json` carries a dangling
   `<user>.clock` anchor and a `.<user>.clock.bak.*` folder. The repair here
   fixes the anchor on the first run of the new installer (per decision 14 the
   code fix is what lands; the leftover folder is the user's to delete).
