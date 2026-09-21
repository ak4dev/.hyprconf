# Agent instructions

The one directive file (`CLAUDE.md` links to it; Claude Code reads that), loaded into every session: keep it short. `README.md` is the user contract; `modules/<name>/README.md` is the one home for what a module does, needs, changes and undoes; `docs/CONTRIBUTING.md` holds the tree, the harness, publish and the website. One home per fact: link, never restate.

## What hyprconf is

- A lean overlay on a stock [Omarchy](https://omarchy.org): `install.sh` runs every `modules/*/install` — self-contained, idempotent, order-free, each with its own `install undo`, README, tests and payload (the four bar modules also source `modules/bar-plugin.sh`, which a cone-mode sparse checkout brings along) — through Omarchy's own seams (map below). It is the only entry point; with no payload beside it (the curl path) it clones `stable` and hands over. Nothing is packaged: the promoted branch is the release.
- Verified against Omarchy 4.0.4-1 (Hyprland 0.56.2, quickshell 0.3.1, uwsm 0.26.7, Firefox 155.0.1-1, git 2.55, Bash 5.3). This line is the pin; a version in a code comment or a test is that fact's own provenance and stays as written.
- A personal config shared as-is, not a product; no `LICENSE`, deliberately. `web/` is one static page: no build, no JS, no external requests.

## Hard rules

1. **Omarchy's own tools first.** Check `omarchy commands --json`, `/usr/share/omarchy/bin/` and the map's seams before any custom mechanism; a hand-rolled replacement for something Omarchy does is a drift bug. A custom path exists only where Omarchy has no tool, and its comment says what was checked.
2. **Never work from memory about Omarchy.** `/usr/share/omarchy/` is authoritative: read it (`grep -R`; `bin/` is symlinks into `/usr/bin`), never edit it; diff `default/hypr/*.lua` before adding a value, read `bin/` for what a command really does and `shell/` for the plugin contract. Cite file:line beside each claim, name the Omarchy version in the commit, and derive lists of its commands, plugins or themes at runtime.
3. **Packages: official Arch repos, through `omarchy-pkg-add`**, one `packages` file per module (`install.sh` installs nothing); `[omarchy]` only where an Omarchy installer owns the package (`omarchy-install-editor-vscode`, `omarchy-install-browser firefox`). Never `pacman`, `yay`, `paru`, `makepkg` or Omarchy's AUR wrappers (`omarchy-pkg-aur-*`, `omarchy-update-aur-pkgs`); never `omarchy-pkg-drop`; an AUR-only need is raised with the user, not implemented. Confirm with `pacman -Si`; nothing in Omarchy's base is listed.
4. **No PII in tracked files**: names, emails, hostnames, IPs, MACs, serials, keys, AWS ids, `/home/<user>` paths, commit messages included; use `~`, `$HOME`, `$USER`, `testuser`. `tests/test_no_pii.py` derives the identities and walks every file on disk. The `Co-Authored-By: … <noreply@anthropic.com>` / `Claude-Session:` trailers are allowed.
5. **Idempotent, reversible, set-once.** Every module re-runs byte-stably — the post-update hook runs `hyprconf --no-update --no-packages` after every `omarchy-update`; a user choice (font, default apps, idle, clock, widget enables) is applied once behind its own marker `~/.local/state/hyprconf/<choice>-applied`, never merged, never re-asserted; every module has a stock-restoring `install undo`, and `hyprconf --undo` runs them all in reverse. Nothing lands in `$HOME` by hand: every file ships in a module, wired through its `install`.
6. **Restraint.** The least code that holds the contract — every line ships into a user's `$HOME`: delete before adding, take the shorter idiom, no single-use indirection, no guard for a state that cannot occur, one parametrized test over N copies, comments for why and never for what. Never `chsh` (why: `modules/shell-zsh`). `install.sh` never writes outside `$HOME`; a module does only through its gate — packages (`terminal-kitty`, `shell-zsh`, `font`, `vscode`), `firefox`'s policy, `keychron`'s udev rule, the user-run `hyprconf-yubikey` (two drop-ins, `limine-mkinitcpio`, the LUKS keyslots) — each named in its README. `sudo` only there, behind `--no-packages` (`HYPRCONF_NO_SUDO`, which the hook passes): with it or without a terminal the module bows out in one line, exit 0; a failed `omarchy-pkg-add` still fails it. Never rewrite `kitty.conf` beyond one `include` per module, switch the active theme, touch `monitors.lua`, overwrite a seeded preset or point `omarchy-default-terminal` at an absent terminal; `tests/test_core.py`, `test_scans.py` and each `test_<name>.py` assert these.
7. **Code, tests and docs move together, in one commit.** A changed module, flag, script, path, package, hotkey, preset or plugin updates its tests, its README and the root README's index row; nothing may describe what no longer exists. Never weaken a test for a green run: an intended behaviour change updates the test to the new contract and says so in the commit. Never alter the README branding block (banner + badges; `tests/test_docs.py` pins its bytes).
8. **Security is a gated invariant, not a review note.** Nothing an unprivileged process can write may steer a root action; untrusted content (window titles, feeder output, network bytes) is data, never code; what ships to strangers is clone-only over https and pinned (CI actions by sha, third-party repos by commit; a pin bump is a deliberate release). The floor: the fetch-and-execute and secret scans, the root-write `--` shape, the bootstrap/https, CI least-privilege and settings-guardrail pins (`tests/test_supply_chain.py`, `tests/test_scans.py`); a new network touch, root write, wider udev match or `eval` updates its pin in the same commit or does not land. Checklist: CONTRIBUTING › Security.

## Integration map (module → Omarchy seam; the mechanism, packages, settings and undo are in each README)

| Module | Omarchy seam |
|---|---|
| [hypr](modules/hypr/README.md) | `~/.config/hypr/{bindings,input,looknfeel}.lua` after Omarchy's defaults; `o.bind` after `hl.unbind`; presets via `~/.local/state/omarchy/toggles/hypr/` |
| [bar-workspaces](modules/bar-workspaces/README.md) | `~/.config/omarchy/plugins/<id>` + a `clonedFrom` manifest; `omarchy-plugin-enable`; `omarchy-shell shell rescanPlugins`; `bar` is the `Ui/PluginBarApi.qml` facade |
| [bar-active-window](modules/bar-active-window/README.md) | as above; placed by `barWidget.defaultSection` |
| [bar-clock](modules/bar-clock/README.md) | as above, on Omarchy's `panels/clock`; `omarchy-bar set`; `bar.centerAnchor` (a plain id) |
| [bar-resources](modules/bar-resources/README.md) | as bar-workspaces without `clonedFrom` (no stock widget); placed by `barWidget.defaultSection`; `kinds: ["service"]` behind `PluginShellApi`, once per session |
| [terminal-kitty](modules/terminal-kitty/README.md) | `omarchy-default-terminal` (checks nothing: `omarchy-pkg-present` first); one `include` in `~/.config/kitty/kitty.conf` |
| [shell-zsh](modules/shell-zsh/README.md) | one grep-guarded `source` line in `~/.zshrc` (`/etc/skel/.bashrc`'s idiom) reading `default/bash/{env-bootstrap,envs,aliases}`; its own kitty include |
| [fastfetch](modules/fastfetch/README.md) | none — `~/.config/fastfetch/config.jsonc` is Omarchy's About screen, so `~/.config/hyprconf/fastfetch.jsonc`, read by `shell-zsh` |
| [font](modules/font/README.md) | `omarchy-font-set` |
| [idle](modules/idle/README.md) | `shell.json` `idle.screensaver` via the sourceable `omarchy-shell-config` |
| [firefox](modules/firefox/README.md) | `omarchy-install-browser firefox`; `/etc/firefox/policies/` (Omarchy writes only `distribution/`); `omarchy-default-browser` |
| [firefox-theme](modules/firefox-theme/README.md) | `~/.config/omarchy/themed/*.tpl`, rendered on every theme set; the `theme-set.d` hook |
| [vscode](modules/vscode/README.md) | `omarchy-install-editor-vscode`, `omarchy-default-editor` |
| [themes](modules/themes/README.md) | `~/.config/omarchy/themes/`, `~/.config/omarchy/backgrounds/<theme>/` |
| [keychron](modules/keychron/README.md) | `/etc/udev/rules.d/`, the shape of `install/hardware/framework/qmk-hid.sh` |
| [vulkan-gpu](modules/vulkan-gpu/README.md) | `~/.config/uwsm/env.d/`, named by `/usr/share/uwsm/env.d/10-omarchy` |
| [yubikey](modules/yubikey/README.md) | `/etc/limine-entry-tool.d/` + `/etc/mkinitcpio.conf.d/` drop-ins, as `omarchy-hibernation-setup` does |
| the core | `omarchy-hook-install post-update hooks/10-hyprconf`; `~/.local/bin` (on the session PATH) for `hyprconf` and each `bin/hyprconf-*`, bound by name |

## Deliberate non-Omarchy choices, and why

- `modules/hypr/*.lua` **copied** (cmp-gated) into `~/.config/hypr/`, not symlinked; `hyprconf hypr` after an edit: an `omarchy refresh` or a migration lands on the copy and the next run puts it back — no clobber guard, no template cache, a clean checkout.
- Each `modules/bar-*/plugin` **symlinked** into `~/.config/omarchy/plugins/`, not cloned: `omarchy plugin clone` hardcodes `<username>.<id>` (PII) and a copy freezes at the release that made it; the link makes `git pull` the update.

## The Hyprland copies

Every save of `modules/hypr/*.lua` must parse (`luac -p`), state only deltas from `/usr/share/omarchy/default/hypr/`, and bind only commands already on PATH (`command -v` first: `test_hypr.py` covers both halves, Omarchy's only on a box that has it; Hyprland runs a missing target as a silent no-op). `mainMod` is `SUPER`; every key Omarchy also binds goes through `rebind()`, which unbinds the keysym and the keycode form before `o.bind`; never restate a bind Omarchy already has (`SUPER+P`, arrows, scroll, mouse drag). A program outside Omarchy's base goes in the owning module's `packages`. A new preset is one more `*Monitors*.lua` file (the seed and `-h` derive from the glob), a README row and a `test_hypr.py` case; desk presets are `desc:`-keyed, serial-free and end on the `output = ""` catch-all (pinned there).

## Scripts

- `#!/usr/bin/env bash` and `set -euo pipefail`; a script that deviates (the two hooks and `hyprconf-yubikey` drop `-e`, `hyprconf-stats` is `set -u`) says why; `tests/test_scans.py` holds that list.
- Runtime Hyprland changes go through `hyprctl eval` and `hyprctl dispatch 'hl.dsp.…'` (`hyprctl keyword` is a no-op under the Lua parser, `dispatch dpms on` an error; forms: `modules/hypr/README.md`). A hotkey-launched script speaks through `omarchy-osd` / `omarchy-notification-send` or not at all. No `pkill` / `killall`.
- Anything outside `$HOME` a script reads or writes sits behind a `: "${_HYPRCONF_X:=/default}"` seam (the Omarchy tree through Omarchy's own `OMARCHY_PATH`, the feeders through `HYPRCONF_STATS_*` / `HYPRCONF_GPU_*`), never `readonly`. Grep them, never list them (CONTRIBUTING › Writing hermetic tests).

## References

- Omarchy: the installed tree, `omarchy commands --json`, `omarchy <group> --help`, the skill it ships at `$OMARCHY_PATH/default/agents/skills/omarchy/`; <https://omarchy.org/manual/> for user-facing behaviour.
- Hyprland Lua: `modules/hypr/README.md`, then `/usr/share/hypr/stubs/hl.meta.lua` and `/usr/share/hypr/hyprland.lua`, then <https://wiki.hypr.land>.
- Bar plugins: each `modules/bar-*/plugin/README.md` › Host contract, then `/usr/share/omarchy/shell/README.md`, `shell/plugins/bar/README.md`, the facades `shell/Ui/PluginBarApi.qml` and `shell/services/PluginShellApi.qml`, and `/usr/lib/qt6/qml/Quickshell/**/*.qmltypes`. Link, never copy: no repo-local cheatsheet.

## Branches, publish, deploy

`dev` is the working branch; `stable` is what users clone and `hyprconf.sh` serves. Only `scripts/publish` writes `stable` (CONTRIBUTING › Publishing to stable), only when the user says "publish", with CI green on `dev`. Never push unless the user asks; commit when asked. Nothing in the repo deploys: the website upload is by hand, only when the user says "deploy", after a publish, always `origin/stable`'s `install.sh`, never the local branch's (CONTRIBUTING › Updating the website).

## Commits and versions

[Conventional Commits](https://www.conventionalcommits.org/): `<tag>(<scope>): <message>`, subject ≤ 140 chars; tags `feat fix docs style refactor perf test build ci chore revert`; `!` or a `BREAKING CHANGE:` footer for a break — the user must act (a removed or renamed hotkey, module, flag, plugin id or path) or a root/boot command turns destructive (wipes, overwrites or stops restoring what it kept before); name the Omarchy version verified against. [SemVer](https://semver.org/) in `VERSION`, bumped by hand in the commit that earns it (minor for a `feat`, major for a break).

## Tests

- One hermetic suite in two places, `modules/<name>/test_<name>.py` beside each `install` and `tests/`, collected in one run; what needs a live session is verified by hand and recorded in the commit.
- Hermetic: green in a bare `archlinux:latest` container as an unprivileged user — no Hyprland, shell, hardware, real `$HOME` or ambient state, never mutating the box; there is no root axis (`install.sh` refuses root, CI runs unprivileged). Every command that could touch the desktop or the system is a fake first on PATH; the pure tools (`conftest.py`'s `PURE_TOOLS`) are real when present; `git` is required (throwaway trees under `tmp_path` only).
- Harness: the repo-root `conftest.py`'s `box` fixture — a throwaway machine with a recording fake for every `omarchy-*` name the tree carries, derived from it — which also exports the session's git identity, so no test passes `-c user.*`. New tests use it (CONTRIBUTING › Writing hermetic tests).

## Gates and CI

Before every commit: `make check` = `make lint` (ruff check + format) + `make shellcheck` (by shebang; fails on finding nothing) + `make test`, the gates `scripts/publish` runs. `.github/workflows/test.yml` runs the same on every push, in `archlinux:latest`, as an unprivileged `ci` user it creates. Nine tests skip there today, each with the one reason the budget allows — `needs the installed Omarchy`; any other skip is a regression, which `conftest.py::pytest_sessionfinish` matches on that reason and turns red, and `-rs` names each. `OMARCHY_PATH=$(mktemp -d) make test` reproduces them here, since every such probe keys on that one seam. Read a red run from its `::error::` annotation, the one part the public API hands back (why: the comment at the workflow's tee step). Reproduce a container-only failure: CONTRIBUTING › Running tests.

## Known quirks (cross-cutting; a module's own live beside its code)

- `omarchy-update` re-execs under `script(1)` with `OMARCHY_UPDATE_LOGGED=1`, so every hook child has a pty: gate anything printed or asked there on that variable, never on `[[ -t 1 ]]`. Nothing does today.
- A prompt runs only on a TTY: every one has a non-interactive path, and `_HYPRCONF_ASSUME_TTY` for the suite. `hyprconf-yubikey` is the only tool that asks.
- A symlinked plugin folder is scanned but never watched, so the explicit `rescanPlugins` on every run is what picks a `git pull` up (citations: `modules/bar-plugin.sh`'s header). Bar widgets never size off `parent` (a binding loop QML drops): bind `implicitWidth` / `implicitHeight` to content.
- Bash 5.3: `$(< file 2>/dev/null)` returns empty; use `read -r var < file` or `$(cat file 2>/dev/null)`. Never `git update-index --skip-worktree`.
- Branding: `.hyprconf` (leading dot), except the domain `hyprconf.sh`, binaries `hyprconf-*` and plugin ids `hyprconf.*`.

## How to work here

Read this file, the module README and the comments beside what you touch, and run `make check` here before every commit — CI on the push is the container gate. `.claude/settings.json` denies rule 3's package tools and edits under `/usr/share/omarchy`, and asks before a push, `scripts/publish`, `aws`, `sudo` and `hyprconf-yubikey`: a speed bump matching command text, not a boundary.
