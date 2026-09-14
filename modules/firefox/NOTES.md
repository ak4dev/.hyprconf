# modules/firefox — notes for the integrator (delete this file)

## Findings landed

| id | how |
|---|---|
| firefox.0#7 | `infra/firefox/policies.json` → `modules/firefox/policies.json`, beside its own install/README. `infra/` now holds only the Keychron rule (modules/keychron's copy). |
| firefox.0#8 | `toolkit.legacyUserProfileCustomizations.stylesheets` is **dropped** from the policy. It has one home now: `modules/firefox-theme`'s per-profile `user.js` (the half that needs no sudo, survives `--no-packages`, and covers LibreWolf). Pinned by `test_the_stylesheet_pref_belongs_to_the_theme_module_not_the_policy`. **Cross-module: firefox-theme MUST keep writing that pref** (BRIEF decision 7 says it does; final-layout's one-liner for firefox-theme mentions only two prefs — the third is this one). |
| install-core.2#1 | the 37-line stage comment is gone; `install`'s header is ~20 lines of citations and README.md carries the user contract. |
| install-core.2#3 | self-contained: `OMARCHY_PATH`, `_HYPRCONF_FIREFOX_POLICIES`, `_HYPRCONF_ASSUME_TTY` defaulted inline, own `info`/`warn`, sources nothing. |
| install-core.2#4 | one `mktemp` with one `trap cleanup EXIT` (never `trap … RETURN`); the `[[ -f $theirs ]]` layers array is gone — the omarchy package always ships the file and a miss lands on the existing jq-failure warn. |
| install-core.2#5 | `sudo install -Dm644 -- "$tmp" "$dst"` and `sudo rm -f -- "$dst"` in undo (rule 8's `--`), citing `bin/omarchy-hibernation-setup:42-43`. **`tests/test_scans.py` must scan `modules/*/install` for the `--` shape** — today's pin is `test_yubikey.py`'s, over one file. |
| install-core.3#2 | per-app marker `browser-applied`; the editor's outcome can no longer re-assert the browser. |
| install-core.3#3 | the setter's exit status is ignored and `omarchy-default-browser` (no args) is read back (already fixed in dev's `stage_defaults`; carried over verbatim). |
| docs.1#19 | README is a 40-line table + one paragraph; the mechanism (allowlist, `Type`, uiCustomization seeding, SearchEngines-on-release) lives in `test_firefox.py` with its sources, and the README links there. |
| install-core.0#10 / 2#8 (partial) | one `interactive()` helper, named after `bin/omarchy-plugin-add:22` but stdin-only, feeding one `sudo_ok "<what>"` gate that also covers `HYPRCONF_NO_SUDO`. One site in this module. |
| test-install-a.0#7 | `_merge` and `test_merged_with_omarchys_policy_it_keeps_every_omarchy_pref` are not carried over (tautological); the merge is exercised with the **real jq through the module** (`test_policy_is_omarchys_merged_under_ours_through_sudo`, `test_ours_wins_on_a_shared_key`). The surviving fixture-drift assert is in `test_omarchy_still_ships_the_policy_this_module_merges_under`, now checking `conftest.OMARCHY_TREE`'s stand-in against the installed file. The repo's only cross-test-module import goes with it. |

## Not landed here

- **firefox.0#1, .0#2…** and everything about `bin/hyprconf-firefox-theme`, `themed/userChrome.css.tpl`, `lib/hyprconf/firefox_theme.py`, `hooks/theme-set.d`: `modules/firefox-theme`'s.
- **install-core.2#20 / 2#22** (sync/setup split, marker helpers): BRIEF decision 6 keeps one marker per choice; there is one marker here and no boilerplate to share.
- **The default-browser seed is deliberately OUTSIDE the sudo/TTY gates.** Finding install-core.3#2's verifier note is the reason: `stage_firefox` ran only under `do_packages` and the post-update hook passes `--no-packages`, so a seed inside the gate would never run on the only path a settled box takes. Do not "tidy" it into the gated block.

## Delete / rewire in the legacy tree

- `install.sh`: `stage_firefox` (the 37-line comment + the function, ~525-607 on dev), `stage_defaults` (~782-830) **and its editor half** — hand the editor half to `modules/vscode` (marker `editor-applied`, same legacy-marker honouring); the `_HYPRCONF_FIREFOX_POLICIES` constant (~56-60); `main()`'s `stage_firefox` / `stage_defaults` calls. Keep `_HYPRCONF_ASSUME_TTY` until every sudo stage is gone.
- `infra/firefox/` (the whole directory) once this module lands; `infra/` itself once `modules/keychron` lands.
- `tests/unit/test_firefox.py` — entirely (moved here; drop the `from tests.unit.test_omarchy_install import OMARCHY_FIREFOX_POLICY` line with it).
- `tests/unit/test_omarchy_install.py`: `OMARCHY_FIREFOX_POLICY` + `SHARED_PREF` + `OMARCHY_POLICY` (~49-67), `test_the_omarchy_firefox_policy_fixture_names_no_pref_omarchy_dropped` (~484-492), `_policy_env` (~1566-1573), `test_firefox_policy_is_omarchys_merged_under_ours_via_sudo_when_interactive`, `test_firefox_is_installed_through_omarchys_installer_when_absent`, `test_a_failed_firefox_install_leaves_no_policy_behind`, `test_default_apps_are_seeded_once_and_the_marker_waits_for_the_seed` (~1030-1060; its editor half goes to modules/vscode), the `default/firefox/policies.json` seeding in `_setup` (~265-269), and the `"infra"` entry in `PAYLOAD` (~399). `test_every_sudo_stage_bows_out_without_a_terminal` and `test_keychron_rule_is_installed_via_sudo_when_interactive` both use `_policy_env` — rewire them before deleting it.
- `README.md`: the `firefox` and `defaults` stage rows (~71, ~27), the whole `## Firefox settings` section (~251-273), the `sudo rm /etc/firefox/policies/policies.json` lines in Reverting (~399-400) and the `infra/firefox/policies.json` links. The 17-row module table gets one firefox row pointing at `modules/firefox/README.md`.
- `AGENTS.md`: the "Firefox, VS Code" integration-map row, the `/etc/firefox/policies/policies.json` deliberate-choices row, and the Firefox bullet in Known quirks (the quirks now live in `modules/firefox/test_firefox.py` and `modules/firefox-theme`'s tests — AGENTS keeps only cross-cutting ones).
- `docs/CONTRIBUTING.md`: the `infra/firefox` tree line and the `_HYPRCONF_FIREFOX_POLICIES` seam line (the seam survives, at its new home); the Security section's root-write `--` paragraph should now name `modules/*/install`.

## Cross-module facts

- `modules/vscode` owns the editor half of the old `stage_defaults`: marker `editor-applied`, same read-back, same honouring of the legacy `defaults-applied` marker for one release. Both modules must honour it or an upgraded box re-asserts one of the two.
- `modules/firefox-theme` owns `toolkit.legacyUserProfileCustomizations.stylesheets` (see above) and is a no-op until a profile exists.
- The policy is one of the overlay's two writes outside `$HOME`; the other is `modules/keychron`'s udev rule. Both now carry the `--` shape.

## Live verification (not done — no sudo, no real /etc here)

1. `bash modules/firefox/install` on each machine from a terminal: the merged policy lands at `/etc/firefox/policies/policies.json` and, on the box that has the old file, differs from it by exactly the dropped `toolkit.legacyUserProfileCustomizations.stylesheets` block — so the first run after the overhaul **does** rewrite it once (expected, and the only non-no-op).
2. After that rewrite, confirm `userChrome.css` still loads: `modules/firefox-theme`'s hook must have put the pref on the profile's user branch. Check `about:support` → `toolkit.legacyUserProfileCustomizations.stylesheets` = true before restarting Firefox, or the chrome theming silently stops.
3. `omarchy default browser` reads back `firefox` and `~/.local/state/hyprconf/browser-applied` exists; the legacy `defaults-applied` marker on these boxes means neither runs — delete it only after `modules/vscode` has also seeded.
4. The Firefox allowlist was re-derived against 155.0.1 during the pin bump; re-derive on the next major with the recipe in `test_firefox.py`.
