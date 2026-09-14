# NOTES — modules/firefox-theme (for the integrator; delete this file)

Payload: `install`, `hook`, `userChrome.css.tpl`, `README.md` (40 lines),
`test_firefox_theme.py` (34 tests). Gates run green here: `pytest
modules/firefox-theme -q`, `shellcheck --severity=warning` + `--include=SC2086`
on both scripts, `bash -n`, `ruff check` / `ruff format --check`.

## Findings landed

- **firefox.0#10** — `lib/hyprconf/firefox_theme.py` (421) + `bin/hyprconf-firefox-theme` (21) +
  `tests/unit/test_firefox_theme.py` (724) are replaced by `hook` (111 lines, ~55 of them code) and
  396 test lines. Kept, as the "do" asks: the `[Install<hash>]` → `Default=1` → first-listed profile
  ladder, the three `user_pref` lines, `cmp` before every write, one `omarchy-notification-send`.
- **firefox.0#18** — `--status` is gone entirely, with the launcher that existed to expose it. The
  hook's per-profile stdout line and the restart notification are the status.
- **firefox.0#15** — landed as the *rewrite*, not as the widening to every profile: the module brief
  specifies the ladder, and it is load-bearing on Firefox 155.0.1-1 — a stock `profiles.ini` here has
  `[Install<hash>] Default=<A>` while a *different* profile carries `Default=1`, and Firefox starts A.
  41 configparser lines → 15 lines of awk.
- **firefox.0#17** — the O_EXCL/fsync/chmod/BaseException writer is `cmp -s` + `install -Dm644` (the
  CSS) and `cmp -s` + `cat > "$js"` (user.js, so a symlinked user.js still keeps its link).
- **firefox.0#14** — the custom line splitter and `surrogateescape` are gone and the byte-exactness is
  *stronger*: `LC_ALL=C grep -a -Ev` filters bytes, never decoding, so latin-1 and U+2028 round-trip
  untouched. One deliberate difference: on a CRLF `user.js` the foreign lines keep their CRLF but the
  three lines this hook writes are LF (Firefox's pref parser takes either).
- **firefox.0#12** — LibreWolf dropped. Evidence: in the pre-module tree it appears only inside the
  bridge's own five files (`grep -ril librewolf`), never in `packages`, `README.md` or a stage, and
  `modules/firefox` installs Firefox. (It is now in `extra`, so the reason is "unused here", not
  "AUR".) README says the one line that brings it back.
- **firefox.0#4 / docs.1#20** — self-contained: no `@HYPRCONF_DIR@`, no `PYTHONPATH`, no `lib/`, no
  `python3` (pinned by a test). The module folder installs alone; README carries the sparse-checkout
  line. The `/etc/firefox` policy half of that finding belongs to `modules/firefox`, not here.
- **firefox.0#1 / .0#2 / .0#6** — moot by deletion: there is no launcher and no second entry point.
  (.0#6 says so itself: "If firefox.0#10 lands first this finding disappears".)
- **firefox.0#5** — the four-line abort justification and the blanket `exit 0` are gone. The hook keeps
  `set -uo pipefail` with one line saying why there is no `-e`, and now returns a real status that
  `install` warns on.
- **firefox.0#3 / docs.1#21** — one home: `modules/firefox-theme/README.md`. The `hook`, `install` and
  `.tpl` headers carry Omarchy/Firefox `file:line` citations and nothing restated.
- **firefox.1#1 + firefox.0#25** — the two disagree; both were re-derived against the installed
  firefox 155.0.1-1 (`unzip` of `/usr/lib/firefox/omni.ja` and `browser/omni.ja`) and **.1#1 is
  right**: nine declarations deleted, `--hyprconf-theme-mode` plus `--toolbar-field-background-color`
  (urlbar.tokens.css:13, urlbar-searchbar.css:1145), `--toolbar-field-focus-color` (smartbar.css:43)
  and `--focus-outline-color` (23 stylesheets) kept. `.0#25` wanted three of the nine kept and is
  wrong on all three: `--toolbar-color` does **not** exist in FF 155 (the only matches are
  `--toolbar-color-scheme`), and `--lwt-accent-color` / `--lwt-text-color` are read only inside
  `:root[lwtheme]` blocks (browser-shared.css:176,828; toolbar.css:24-41) plus tabs.css's deliberately
  invisible stack bottom (tabs.css:641-652 says so in its own comment). A parametrised test pins all
  nine as absent and the three as present.
- **install-core.5#7** — one stage: the hook is run by hand **only** when no `omarchy-theme-refresh`
  ran, because a refresh is `omarchy-theme-set` and that ends in `omarchy-hook theme-set`
  (omarchy-theme-set:341). The `omarchy-theme-refresh` fake in the test does exactly that, so the
  suite can see the double-apply; `test_a_refreshed_run_does_not_run_the_hook_a_second_time` pins it.
- **install-core.5#4** — the comments are Omarchy citations and the one non-obvious mechanic
  (omarchy-hook-install installs under the *basename*, so the file is copied to `10-hyprconf` first).
- **install-core.5#5** — `cmp -s … || install -Dm644 …`, once for the template, once for the render.
- **install-core.5#6** — no `command -v omarchy-theme-refresh` guard; the call's own failure warns.

- **install-core.0#1 (its theme-set half)** — the `hook` header is four items and nothing else: what it
  is, the seam it runs from (`omarchy-hook theme-set`, bin/omarchy-hook:22-27, called by
  omarchy-theme-set:341) with rule 1's citation that Omarchy themes Chromium only
  (omarchy-theme-set-browser:8-13), why there is no `set -e` (bin/omarchy-hook:26 already reports a
  failing hook), and the copy-not-link mechanic that makes the file stand alone. No recursion guard is
  documented because none exists: the hook calls no theme command at all
  (`test_every_omarchy_command_the_module_calls_has_a_fake` pins the whole call set). The "runs twice
  on purpose" narrative belongs to the **post-update** hook, i.e. to the core.
- **firefox.0#11** — landed as the finding's own proposal: one `## Verified against Omarchy 4.0.3-1`
  line, in `README.md`, and nowhere else does a *version* stand in for provenance. Two deliberate
  departures, both from the module contract: `file:line` citations stay (the contract asks for "what +
  the Omarchy file:line it rests on"), and `Firefox 155.0.1-1` is named in the `hook`, `.tpl` and test
  headers where the fact *is* a Firefox-version observation (which variables 155 reads, `inApp: true`)
  rather than provenance for an Omarchy fact.
- **firefox.0#13** — moot by rewrite: there is no `_PREF_RE`. The `managed` pattern matches only up to
  the pref name's closing quote and the comma, so anything after the `;` — trailing spaces, a tab, a
  comment — is filtered out and the line is rewritten in place rather than duplicated.
- **firefox.0#21 / .0#22 / .0#23** — moot: `tests/unit/test_firefox_theme.py` (724 lines, 33 tests) is
  deleted whole, so its duplicate fixtures, its `THEME_COMMANDS` "prove none of them ran" stubs and
  its private-helper tests go with it. The new suite has no in-process half — every test runs the real
  scripts in a box — so the structurally-impossible assertions cannot recur. One coverage item from
  0#23's verifier note is **not** carried over and is a deliberate gap: a commented-out
  `// user_pref("ui.systemUsesDarkTheme", 0);` and a bare `pref(...)` line survive the merge (the
  `managed` pattern anchors on `^[[:space:]]*user_pref\(`), but no test pins it.
- **firefox.0#24** — landed as its surviving half: the 17 verbatim rendered lines and the three
  `css.count` totals are gone; `test_the_template_renders_with_no_token_left_over` renders the
  template with a fixed palette and asserts no `{{` is left and every value appears. The "renderer" is
  one `str.replace` per key — the same substitution `add_template_value` emits at
  bin/omarchy-theme-set-templates:200 (`s|{{ key }}|value|g`), no second bash fake of it.

## Findings not landed here

- **firefox.0#9** — `VERSION` already exists at the repo root (7.0.0) from the foundation phase and
  nothing in this module touches `lib/`. Deleting `lib/` is yours at integration.
- **install-core.5#8** — it is about `stage_update` and `hooks/post-update.d/10-hyprconf`, which the
  core owns. Nothing in this module restates the post-update rationale; land it with the core.
- **firefox.0#16 (HIGH — deliberately overridden, do not reopen)** — "delete the user.js half
  entirely: the XDG appearance portal already carries light/dark to Firefox". The module keeps all
  three prefs because BRIEF "Decisions already taken" #7 says so in as many words: the bash hook
  "keeps writing `extensions.activeThemeID` … `ui.systemUsesDarkTheme` … and
  `toolkit.legacyUserProfileCustomizations.stylesheets`". The finding's own reasoning is sound for the
  first two (omarchy-theme-set-gnome:18-25 sets the GNOME colour scheme on every theme set and
  xdg-desktop-portal-gtk serves it to Firefox), and the third is only *partly* covered by the policy —
  see the cross-module note below. Two things to carry if it is ever reopened: dropping
  `--hyprconf-theme-mode` from the template would go with it, and removing `extensions.activeThemeID`
  does **not** revert a profile that already has it on its user branch — the user has to pick
  "System theme — auto" once, which the README would have to say.

## What to delete or rewire in the legacy tree

1. `install.sh`: delete `stage_themed` (1419-1450), `stage_theme_apps` (1458-1467) and their calls in
   `main()` (1511-1514, including the "Before stage_theme_apps" comment); call
   `bash "$HERE/modules/firefox-theme/install"` instead. `stage_hooks` (1388-1401) loops over
   `hooks/*.d/*` — once `hooks/theme-set.d/` is deleted it installs only the post-update hook, so keep
   it until the core's own `omarchy-hook-install post-update` replaces it.
2. Delete the payload: `hooks/theme-set.d/10-hyprconf`, `themed/userChrome.css.tpl` (and the empty
   `themed/`), `bin/hyprconf-firefox-theme`, `lib/hyprconf/firefox_theme.py`,
   `tests/unit/test_firefox_theme.py`.
3. `tests/unit/test_omarchy_install.py`: the launcher test (959-971) and its entry in the shipped-tool
   list (2142); the theme-set hook tests (1388-1424 — 1405 asserts `--toolbar-bgcolor`, a variable the
   new template no longer sets); `_themed_checkout` (1432-1440); the static hook scan (1488-1506);
   narrow the `@HYPRCONF_DIR@` substitution assertion (1305-1317) to the post-update hook; drop
   `themed`, and later `lib`, from `PAYLOAD`.
4. `pyproject.toml`: drop `pythonpath = ["lib"]`; `testpaths = ["modules", "tests"]`. **Do that in the
   same commit that deletes `tests/unit/test_firefox_theme.py`** — two files of that basename with no
   `__init__.py` make pytest's prepend import mode error out on collection.
5. `README.md`: the `hooks` row's theme-set half (90), the `themed` (91) and `theme_apps` (92) rows,
   `hyprconf-firefox-theme` in the bin row (84), the whole `## Theme → Firefox` section (275-294), the
   `#theme--firefox` cross-link at 263, the revert lines (391-392), and `themed/` + `lib/hyprconf/` in
   the payload sentence (117) → one table row pointing at `modules/firefox-theme/README.md`.
6. `AGENTS.md`: the Theme row of the integration map (the `themed/` + hook + `lib/hyprconf/` half — the
   `themes/dracula` half is `modules/themes`'), the Hooks row's `theme-set.d`, the "Python in
   `lib/hyprconf/`" deliberate-choice row, and the Firefox quirk bullet's pointers to
   `lib/hyprconf/firefox_theme.py` / `tests/unit/test_firefox_theme.py` → `modules/firefox-theme/`.
7. `docs/CONTRIBUTING.md`: the tree lines for `themed/`, `lib/`, `bin/hyprconf-firefox-theme` and every
   `--status` mention (27, 31-32, 41, 47, 78, 159).

## Cross-module facts

- `modules/firefox` owns the package, `/etc/firefox/policies/policies.json` and
  `omarchy-default-browser`. This module never installs Firefox and is a no-op until a profile exists.
- **firefox.0#8's other half is `modules/firefox`'s, and is recorded nowhere else**: drop the
  four-line `toolkit.legacyUserProfileCustomizations.stylesheets` block from that module's
  `policies.json`, plus its policy-fixture assertion and its README row. This module is the half that
  keeps the pref, per the finding's `do`: the policy needs sudo and a terminal, is skipped under
  `--no-packages` (which the post-update hook always passes), is Firefox-only, and its
  `Status: "default"` seeds the default branch alone — a profile where the pref was ever toggled off
  keeps it off, while the `user.js` write puts it on the user branch at every theme set. If the policy
  block is left in place nothing breaks; the two agree. Never do the reverse.
- `install undo` now exits with the hook's own status when the hook's `--undo` failed (a profile it
  could not write), after removing the template, the hook and the render regardless. Keep the core
  loop's `bash … undo || true`.
- The **post-update** hook is the core's (`hooks/10-hyprconf`). This module installs only the
  **theme-set** hook, and under the basename `10-hyprconf` — the name the pre-module overlay used, so
  an existing install is replaced rather than joined by a second copy. Nothing else in the tree may
  install a `theme-set.d` hook under that basename.
- No packages, no sudo, no marker, no `_HYPRCONF_*` seam, nothing written outside `$HOME`, so the
  `HYPRCONF_NO_SUDO` and no-TTY gates have nothing to gate. Order-free.
- It calls `omarchy-theme-refresh`, i.e. a full `omarchy-theme-set` of the current theme, when the
  template changed or the render is missing. If a later module also re-sets the theme, both are
  idempotent.

## Live verification (none of it was run against the real session)

1. `bash modules/firefox-theme/install` once on a real box, then `omarchy theme set <other>`: the
   started profile's `chrome/userChrome.css` follows and one restart notification appears.
2. Firefox 155.0.1-1 with the trimmed template: confirm the chrome still paints (the direct
   `#navigator-toolbox` / `#nav-bar` / `#urlbar-background` / `#sidebar-box` rules) and that dropping
   the nine variables changed nothing visible — the urlbar field and focus ring are the three kept.
3. A light theme: the render must carry `--hyprconf-theme-mode: light;` and `user.js` must flip to
   `firefox-compact-light@mozilla.org` / `ui.systemUsesDarkTheme 0`.
4. `install undo` on a box with a real profile, then a Firefox restart: stock chrome back, the user's
   own `user.js` lines intact.
5. A profile whose `user.js` cannot be rewritten (chown it to root, or make the profile directory
   read-only): the hook must exit non-zero, say so, and leave the file exactly as it was — and
   `install undo` must still take the template, the hook and the render away.
