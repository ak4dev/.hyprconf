# modules/vscode — notes for the integrator (delete this file)

Replaces `install.sh`'s `stage_editor` and the **editor half** of `stage_defaults`. No payload, no
`packages` file. Verified against Omarchy 4.0.3-1 (`omarchy 4.0.3-1`, `/usr/bin/omarchy-*`).

## Findings landed

- **install-core.2#9** — the 21-line `stage_editor` header is now ~7 lines in the module: the Omarchy
  citation (`bin/omarchy-install-editor-vscode:6,27,29`, no `set -e` → always exits 0), the one sentence
  that justifies the read-back, and the not-set-once note. The nine-line Code - OSS paragraph is gone
  from code; it lives once, user-facing, in `modules/vscode/README.md` › What.
- **install-core.3#2** (marker split) — `editor-applied` is the module's own marker; the browser's seed
  is `modules/firefox`'s. The legacy `defaults-applied` counts as applied for one release and is **not
  deleted** on install or undo (the firefox module reads the same file). Beyond the finding: the seed is
  on the always-run path (outside the sudo/TTY gates and outside the already-installed early return), so
  the post-update hook's `--no-packages` run still seeds it — the placement the verifier note demanded.
- **install-core.3#3** (read the setter back, never its status) — already fixed in the legacy stage;
  carried over unchanged and pinned by `test_editor_is_seeded_once_on_the_value_read_back_not_the_setters_status`.
- **install-core.0#10 / .2#8** (the shared `need_tty` helper) — not applicable: a module is
  self-contained and must not source anything, so the gate is four lines in place (BRIEF: "a `die` is one
  line"). `install-core.2#6` was rejected upstream for the same reason; recorded here so it is not
  re-raised.

## Behaviour change from the legacy stages (please keep, and say so in the commit)

`stage_defaults` seeded `code` whether or not VS Code was installed, so a `--no-packages` first run
pointed `omarchy-launch-editor` (and `SUPER+C`) at an absent binary **and**, once the read-back fix
landed, wrote the marker so it was never retried. The module seeds only when
`omarchy-pkg-present visual-studio-code-bin` succeeds and otherwise leaves the default alone with no
marker, so the next run with a terminal seeds it. Rule 6's "never point `omarchy-default-terminal` at an
absent terminal" is the same rule, one app over.

## Delete from the legacy tree when wiring this module in

- `install.sh`: `stage_editor` (with its 21-line header) and its call in `main`; `stage_defaults` — the
  whole stage if `modules/firefox` carries the browser seed, otherwise only its editor half, its
  `defaults-applied` marker write and the `seeded` bookkeeping.
- `tests/unit/test_omarchy_install.py`: the "VS Code — Omarchy's own installer, nothing removed ahead of
  it" section and its `_packages()` helper; `test_default_apps_are_seeded_once_and_the_marker_waits_for_the_seed`
  and `test_defaults_marker_survives_the_setters_failing_notification` (both editor halves are covered
  here — the browser halves belong to `modules/firefox`); `_default_app_stub`'s editor uses, and the
  `omarchy-default-editor` stub in `_setup` (conftest's `box` fakes it).
- `README.md`: the `editor` stage row (72) and the `defaults` row (76) — the defaults row's editor half
  and its `defaults-applied` marker sentence; row 27's "set as the default browser and editor once"
  becomes the two module rows; the revert-recipe line 402 comment about VS Code moves to this README.
- `AGENTS.md`: the integration-map "Firefox, VS Code" row's `stage_editor` half → `modules/vscode`; the
  rule-3 mention of `omarchy-install-editor-vscode` stays (it is the rule's own example).
- `docs/CONTRIBUTING.md`: any stage list naming `stage_editor` / `stage_defaults`.
- `packages`: the comment block at :33-35 naming `stage_editor`.

## Cross-module facts

- `modules/firefox` owns `omarchy-default-browser firefox` behind `browser-applied` and must honour the
  same legacy `defaults-applied` file — and must not delete it either, or this module re-seeds.
- Marker names are final: `editor-applied`, `browser-applied`, legacy `defaults-applied`. One release
  after 8.0.0 the legacy branch (`install`:26,52 — the `legacy` marker) and its test go.
- `bindings.lua`'s `SUPER+C` launches `omarchy-launch-editor`, which resolves this default — nothing in
  `modules/hypr` needs to know the editor's name.

## Live verification (not done here — no sudo, no real desktop)

1. On a box without VS Code, from a terminal: `bash modules/vscode/install` installs the package and
   opens VS Code once (Omarchy's own `gtk-launch`), then `omarchy default editor` prints `code`.
2. The same run over SSH / on a TTY with no notification daemon: `omarchy-default-editor code` exits 1
   while the value lands — the marker must still be written (that is the whole point of the read-back).
3. `bash modules/vscode/install undo` → `omarchy default editor` prints `nvim`; VS Code still installed.
4. On this laptop, which already has `~/.local/state/hyprconf/defaults-applied`: the first module run
   must call no `omarchy-default-editor <name>` and must create `editor-applied`.
