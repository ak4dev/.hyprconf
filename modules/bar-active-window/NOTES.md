# NOTES for the integrator — modules/bar-active-window (delete this file)

## Findings landed

- **plugins-bar.0#11** — `barWidget.displayName` / `.description` /
  `.allowMultiple` dropped from `plugin/manifest.json` (shell.qml:1402-1405 falls
  back to the manifest's own `name` / `description` and to `allowMultiple` false,
  verified on 4.0.3-1). `version` 1.1.0 → 1.2.0. Pinned by
  `test_the_manifest_is_the_clone_contract_and_nothing_the_shell_defaults`.
- **plugins-bar.0#7** — `plugin/README.md` is the one home for the behaviour list
  and the `maxWidth` budget. The behaviour list is gone from the QML header; the
  module `install` header keeps only the reasoning (why the enable carries no
  placement, why a symlink, why one marker) with the Omarchy file:line beside it.
- **plugins-bar.0#5** — `plugin/ActiveWindow.qml` header cut from 20 lines to a
  three-delta list, and delta 3 now names the merged middle/right-click branch as
  a **source-only** difference plus a "refresh when Omarchy changes the widget"
  recipe (the clock's shape, since this widget has no parity test).

## Not landed here

- **plugins-bar.0#10** (test-economy) — its corrected `do` edits
  `tests/unit/test_omarchy_install.py:2507-2533` and keeps
  `test_plugins.py`'s `validator_problems`; both files are outside this module.
  The module test parses the manifest **once** and pins `id` / `clonedFrom` /
  `entryPoints` / `defaultSection` there, which is what that finding wanted.
- **core install-core.4#5 / 4#17** (collapse the four plugin stages into one
  loop; trim the stage comments) — moot: each plugin is now its own module with
  its own install. The surviving reasoning from `install.sh:1280-1293` is in the
  module install header.
- **test-install-a.1#4 / .2#5 / .2#9** — relocation of the plugin QML/manifest
  pins out of the install suite. The active-window half is carried by
  `test_bar_active_window.py`; the other three widgets' halves belong to their
  modules, and what is left over is the shared suite's to keep or drop.

## Delete / rewire in the legacy tree

- `install.sh`: `stage_window_title` (the comment + function, ~1280-1298) and its
  `main()` call (~1509). The shared helpers `sync_plugin_dir`, `dir_modes`,
  `enable_plugin_once`, `activate_plugin_copy`, `reload_plugins` and the
  `_HYPRCONF_PLUGIN_WAIT` seam (~62-65) go only once **all four** bar modules
  have landed — bar-clock/-workspaces/-resources still use them.
- `plugins/hyprconf-active-window/` — the payload was **copied**, not moved.
  Delete the old folder. Note `plugin/README.md`'s by-hand install path now says
  `modules/bar-active-window/plugin`.
- `README.md`: the `window_title` stage row (~88), the `hyprconf.active-window`
  widget row (~143) → one clause plus a link to the module README, the
  "four plugins … synced on every run" sentence (~145, shared with the other bar
  modules: they are **symlinked** now, not synced), and the revert line (~386).
- `AGENTS.md`: the Bar-widgets integration-map row still says
  `plugins/hyprconf-{clock,resources,workspaces,active-window}` "synced every
  run"; it becomes one row per module, symlinked.
- `tests/unit/test_omarchy_install.py`:
  `test_the_window_title_clone_is_enabled_never_the_stock_widget` (~2058-2068),
  the `"active-window"` entries in
  `test_bar_widget_enables_retry_until_the_shell_can_answer` (~2031, and its
  `count(...) == 4`), the id list at ~1812.
- `tests/unit/test_plugins.py`: `MANIFEST_PINS["hyprconf-active-window"]` and
  `test_window_title_widget_keeps_the_stock_behaviours` (~547-556) are covered
  here now. **`PLUGINS = REPO_ROOT / "plugins"` (line 27) must be repointed** at
  `modules/*/plugin` before `plugins/` is deleted, or every scan in that file
  silently stops covering anything (several of its asserts would fail loudly —
  `assert qml` — but `plugin_folders()` parametrisation would just collect zero).
- `docs/CONTRIBUTING.md` test-tree lines for both suites.

## Cross-module facts

- **Order-free with bar-workspaces.** Omarchy 4.0.3's default bar carries no
  `omarchy.active-window` entry at all (`config/omarchy/shell.json .bar.layout`:
  left is `omarchy.menu`, `omarchy.workspaces`), so this widget is placed by
  `defaultSection: left` + the `barTarget` anchor after `omarchy.workspaces`
  (`PluginRegistry.qml:270-275`). That anchor resolves to `hyprconf.workspaces`
  when that copy already holds the slot and to the stock id otherwise — the same
  index either way, so alphabetical module order is fine.
- The manifest trim (plugins-bar.0#11) applies to **all four** manifests; the
  clock/workspaces/resources modules each carry their own.
- `tests/unit/test_omarchy_install.py:2197` asserts the *clock*'s
  `barWidget.displayName`; that one is bar-clock's to delete.

## Live verification (nothing here touched the live desktop)

1. The PluginBarApi facade on 4.0.3: tooltip, left-click focus, middle- and
   right-click close, the two-line elide, and `omarchy bar set
   hyprconf.active-window maxWidth 400` taking effect.
2. A **symlinked** plugin folder end to end: `omarchy-shell shell rescanPlugins`
   picking up a `git pull`, `omarchy plugin disable` restoring stock, and
   `omarchy plugin remove hyprconf.active-window` unlinking rather than deleting
   the checkout (`omarchy-plugin-remove:99-101`).
3. On this laptop `~/.config/omarchy/plugins/hyprconf.active-window` is still the
   pre-module **real directory**: the first module run moves it to
   `.hyprconf.active-window.bak.<ts>`, which the user can then delete. The marker
   name is unchanged (`active-window-applied`), so an existing install is not
   re-enabled.
