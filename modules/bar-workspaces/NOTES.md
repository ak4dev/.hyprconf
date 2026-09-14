# bar-workspaces — notes for the integrator (delete this file)

## Findings landed

- **plugins-bar.1#2** — `plugin/NOTICE`: the "(re-verified against 4.0.2)"
  parenthetical is gone, `release 4.0.0` and the file→file mapping stay.
- **plugins-bar.1#3** — the widget's rationale now has two homes only
  (`plugin/Workspaces.qml`'s header and `plugin/README.md`); `install`'s header
  carries install facts only (link vs copy, rescan-per-run, enable-once, the
  empty placement) and points at the plugin README for the rest.
- **plugins-bar.1#6** — `plugin/README.md`'s disable/remove mechanics and the
  overlay-sync paragraph are two sentences plus a one-line pointer at the
  overlay. `omarchy plugin remove`'s backup naming is gone (stock behaviour;
  the command prints the path itself).
- **plugins-bar.1#7** — the QML header says what the file is (a replacement
  sharing `focusWorkspace` and the id loop, not a copy), keeps the three
  deltas and the `Omarchy 4.0.0-1` provenance, and the clonedFrom/moduleName
  paragraph is two lines with the PluginRegistry citations re-verified on
  4.0.3-1 (`:530-534`, `:555`, `restoreCloneSource:441`). NOTICE's mapping line
  says "replacement" too.
- **plugins-bar.1#8** — `flow: Grid.LeftToRight` deleted; `lineHeightScale`
  replaced by a literal `lineHeight: 1.0` with the why moved onto that line;
  `rowSpacing: 0` kept beside the explicit `columnSpacing`, per the verifier.
- **plugins-bar.1#9** — `barWidget.description` and `allowMultiple: false`
  dropped from `plugin/manifest.json`; `displayName`, `category` and `author`
  kept (Omarchy's documented manifest shape, `shell/README.md:51-72`). No
  `defaultSection`: the clonedFrom swap inherits the stock widget's slot.
- **install-core.4#5 / #6 / #7 / #9 / #17** (the `core.json` entries naming
  `stage_workspaces`): the stage is now a module — one script, no shared
  helpers; the folder is a **symlink**, not a synced copy (so `sync_plugin_dir`
  / `dir_modes` / the staging dance are gone with it); one rescan per run
  instead of the sync's rescan plus `activate_plugin_copy`'s; the discovery
  poll is kept (omarchy-plugin-add:163-171's own shape) with
  `_HYPRCONF_PLUGIN_WAIT` dropped — the tests stub `omarchy-plugin-list`
  instead; `reload_plugins`' shell-restart fallback is gone in favour of
  Omarchy's own best-effort form `omarchy-shell -q` (install-core.4#8's `do`).
- **plugins-shared.1#13 / #15 / #16** as they touch this plugin: the module's
  own `test_bar_workspaces.py` holds the whole plugin contract (no second
  file), and the 140-line QML text-format scanner is the ~12-line block-match
  rule the finding names. #13's `do` (delete the `omarchy-plugin-validate`
  port) is **partly** followed: BRIEF decision 12 keeps the port because CI has
  no Omarchy, so a ~45-line trimmed port (`validator_problems`, one kind
  instead of the six-kind table, cited line by line to
  `bin/omarchy-plugin-validate`) rides in the module test beside the
  real-validator test it is the CI half of — plus a self-check that the port
  refuses a manifest with a required field removed. Without it nothing in CI
  holds `schemaVersion`, `name` or `version` in the manifest (no code here
  reads them). **Integrator's call**: if a shared copy in `tests/test_scans.py`
  is preferred once all four bar modules land, delete `validator_problems` and
  the two tests named after it from each module test and parametrize the
  shared one over `modules/*/plugin/`; nothing else in this file depends on it.

## Findings not landed here

- **plugins-bar.1#4, #5** — already applied to `plugins/hyprconf-workspaces/README.md`
  before this phase (the `--yes` caveat and the by-hand install path); carried
  over, with the clone path repointed at `modules/bar-workspaces/plugin`.
- **plugins-shared.1#10, #11, #12, #17, #18, plugins-bar.0#2-#4** — they are
  about `tests/unit/test_plugins.py`, `tests/integration/test_plugin_split.py`
  and `docs/quickshell-reference.md`, none of which are this module's files.
  Of #17: the Pac-Man codepoint pin and the `Math.ceil` columns regex are NOT
  carried into the module test — the header and README are their one home; the
  structural "no fixed pill set, no id cap, stock `moduleName`" assertions are.

## What to delete / rewire in the legacy tree

- `install.sh`: `stage_workspaces` with its comment block (1264-1278) and its
  call in `main()` (1508). The helpers it shared — `sync_plugin_dir`,
  `dir_modes`, `enable_plugin_once`, `activate_plugin_copy`, `reload_plugins`,
  the `_HYPRCONF_PLUGIN_WAIT` seam (62-65) — go when all four bar modules land.
- `plugins/hyprconf-workspaces/` (copied here; the copy carries the edits above).
- `tests/unit/test_plugins.py`: the `MANIFEST_PINS["hyprconf-workspaces"]` entry
  (465-471) and `test_workspaces_widget_shows_only_active_workspaces` (539-547).
- `tests/unit/test_omarchy_install.py`: the workspaces arms of the plugin
  tests — 1812, 1936, 2016, 2031, and `test_workspaces_widget_shows_only_active_workspaces_on_two_lines`
  (2494ff).
- `README.md`: the `workspaces` stage row (87), the `hyprconf.workspaces`
  widget row (141), the four-plugin sync paragraph (145, now wrong for this
  plugin: it is a link, not a bytes+modes sync), the revert line (384) and the
  bar-widgets summary row (24). `docs/CONTRIBUTING.md:37` (the tree line).
- `AGENTS.md`: the Bar-widgets integration-map row ("synced every run") and the
  deliberate-choices table need the link row the migration decided on.
- `packages`: nothing — this module installs none.
- **CI skip count**: AGENTS.md pins "exactly two skips". This module adds
  `test_the_installed_link_passes_omarchy_plugin_validate` (skips without the
  installed Omarchy), and the sibling bar modules will each add their own —
  update that sentence to the new count/shape in the docs pass.

## Corrections after the first pass

- `install undo` now removes the link only when it *is* a link
  (`[[ -L $link ]] && rm -f "$link"`, `rm -f "$marker"` unconditional). Before,
  an undo on a machine carrying a real directory at
  `~/.config/omarchy/plugins/hyprconf.workspaces` — the pre-module synced copy
  every current user has, and an `omarchy plugin add` checkout — died on
  `rm: cannot remove …: Is a directory` with exit 1. The apply path already
  guarded that shape (it moves the directory aside once). Pinned by
  `test_undo_leaves_a_real_directory_it_never_made`, and the module's undo
  never deletes a folder it did not create.
- The trimmed `omarchy-plugin-validate` port is in the module test (see the
  plugins-shared.1#13 bullet above).

## Cross-module facts

- Marker name unchanged (`workspaces-applied`), so a machine that already ran
  the legacy installer is not re-enabled.
- The link replaces a real directory ONCE, moving it to
  `~/.config/omarchy/plugins/.hyprconf.workspaces.bak.<ts>`; the user deletes
  that when they are happy (migration step 7).
- `bar-active-window` is anchored after `omarchy.workspaces`, which the shell
  clone-resolves to `hyprconf.workspaces` while this widget is on the bar
  (`PluginRegistry.qml` barTarget/findRelativeBarLocation → `activeCloneFor`):
  install order does not matter, but a run with this module disabled puts the
  title widget at the end of the left section instead.
- Every run calls `omarchy-shell -q shell rescanPlugins` even when nothing
  changed — a rescan is a full plugin reload, but with a symlinked folder the
  shell's `inotifywait -r` never sees a `git pull` (`PluginRegistry.qml:663-674`),
  so it is the only thing that picks one up. Second-run byte-stability is
  asserted; the rescan is the one non-mutating call that repeats.

## Live verification (not doable here)

1. Enable/disable/remove against a **symlinked** plugin folder on the real
   session: the swap into `omarchy.workspaces`' slot, `omarchy plugin disable`
   restoring the stock widget, `omarchy plugin remove` unlinking (it should say
   "Unlinked", not back up).
2. `git pull` in the checkout, then `hyprconf bar-workspaces` — the widget
   picks the new QML up on the rescan.
3. The PluginBarApi facade on 4.0.3-1: `bar.barForeground`, `bar.fontFamily`
   and `bar.run(...)` all answer for an installed third-party widget (shared
   with the other three bar modules; one `omarchy restart shell` covers all).
