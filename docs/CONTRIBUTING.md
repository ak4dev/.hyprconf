# Contributing to hyprconf

Read [`AGENTS.md`](../AGENTS.md) first — its rules bind every change;
`README.md` is the user contract. This file holds the tree, the tests, the
publish flow and the website upload.

## Repository Layout

```
.hyprconf/
├── install.sh                  # The overlay installer — idempotent stages, the only entry point; served by hyprconf.sh, clones itself on the curl path
├── packages                    # Official-repo packages, installed via omarchy-pkg-add (Firefox and VS Code go through Omarchy's installers instead)
│
├── hypr/
│   ├── bindings.lua            # Hotkeys (o.bind with descriptions; unbind-then-rebind)
│   ├── input.lua               # Input/gesture deltas from Omarchy's defaults
│   ├── looknfeel.lua           # Look'n'feel deltas from Omarchy's defaults
│   ├── pcMonitors.bedroom.lua  # Preset "bedroom"  (SUPER+SHIFT+B), desc:-keyed
│   ├── pcMonitors.kitchen.lua  # Preset "kitchen"  (SUPER+SHIFT+K), desc:-keyed
│   └── laptopMonitors.lua      # Preset "laptop"
│
├── bin/                        # Tools installed by install.sh (→ ~/.local/bin, @HYPRCONF_DIR@ substituted); the hotkeys bind the first two by name
│   ├── hyprconf-monitor-preset #   copy a preset into Omarchy's toggles dir (~/.local/state/omarchy/toggles/hypr), reload, rehome workspaces; `stock` removes it
│   ├── hyprconf-gaps           #   SUPER+SHIFT+= / - via hyprctl eval
│   ├── hyprconf-yubikey        #   FIDO2 unlock of the LUKS2 root at boot (status/enroll/sudo/disable/remove); a limine-entry-tool drop-in, the way Omarchy adds kernel parameters
│   ├── hyprconf-vulkan-gpu     #   Dual-GPU box: pin Vulkan (Steam/Proton) to the display GPU — or one you pick — via uwsm env.d (status/prompt/fix/use/toggle/run/alt/ignore/remove)
│   ├── hyprconf-firefox-theme  #   launcher for firefox_theme.py (apply / --status)
│   ├── hyprconf-install-service-protonvpn  # Proton VPN via omarchy-pkg-add; run by the menu row stage_menu adds
│   └── hyprconf-help           #   every add-on at a glance, derived from the checkout at run time (tools' header one-liners, widget manifests, theme and hook dirs)
│
├── lib/hyprconf/               # Python package, used in place via PYTHONPATH (theme-set hook, hyprconf-firefox-theme)
│   ├── firefox_theme.py        # Omarchy's rendered userChrome.css into Firefox/LibreWolf profiles + user.js prefs (theme-set hook)
│   └── __init__.py             # __version__ (bumped by scripts/publish)
│
├── plugins/                    # Omarchy bar-widget plugins, each folder a plugin on its own (manifest.json at its root, README.md, NOTICE where the code is Omarchy's — › Publishing a plugin), synced by install.sh into ~/.config/omarchy/plugins/
│   ├── hyprconf-clock/         #   Omarchy's own clock (BarWidget.qml + Model.js) ticking seconds — clonedFrom omarchy.clock, the three deltas named in its header
│   ├── hyprconf-resources/     #   cpu/mem/net/temp + GPU readout: Widget.qml draws, Service.qml (kinds bar-widget + service — loaded once, not per bar surface) owns its two feeders in bin/ (hyprconf-stats, hyprconf-gpu-info), run by absolute path from the folder
│   ├── hyprconf-workspaces/    #   replaces omarchy.workspaces (clonedFrom): only the workspaces that exist, two lines
│   └── hyprconf-active-window/ #   replaces omarchy.active-window (clonedFrom): the title on two lines
├── themes/dracula/             # Omarchy user theme (colors.toml + backgrounds/)
├── themed/userChrome.css.tpl   # Omarchy user template (→ ~/.config/omarchy/themed/), rendered by omarchy-theme-set-templates on every theme set
├── wallpapers/                 # Extra backgrounds, filed per Omarchy theme
├── zsh/                        # zshrc.block (managed ~/.zshrc block), .p10k.zsh
├── kitty/hyprconf.conf         # kitty include
├── fastfetch/config.jsonc      # Greeting layout
├── hooks/post-update.d/10-hyprconf   # Re-applies the overlay after omarchy-update (installed with omarchy hook install)
├── hooks/theme-set.d/10-hyprconf     # Runs firefox_theme.py after every omarchy theme set
├── infra/firefox/policies.json # System Firefox policy (extensions, search engine, privacy + UI settings), installed merged over Omarchy's default/firefox/policies.json
├── infra/udev/70-keychron.rules # hidraw uaccess for Keychron (0x3434) / Lemokey (0x362d), so the WebHID launcher can reach the boards
│
├── tests/                      # Unit + integration (see below)
├── scripts/publish             # Lint + test → promote dev → stable
├── docs/                       # This file, hyprland-reference.md, quickshell-reference.md
├── .github/                    # CI workflow
├── web/, assets/               # index.html + favicon.svg (static landing page); banner.svg, screenshot.svg (placeholder shown by the README and the page)
├── Makefile, pyproject.toml    # Test/lint targets; pytest/ruff config
├── .gitignore                  # Python caches, `.vscode/`, editor swap files and Claude Code's local session state
├── .claude/settings.json       # Agent deny/ask rules — the layer bypass permission mode still honours
└── AGENTS.md, CLAUDE.md, README.md   # CLAUDE.md is a symlink to AGENTS.md — Claude Code reads CLAUDE.md, not AGENTS.md
```

What reaches a user's machine, and how, is `README.md` › Repository layout.
The `hypr/*.lua` override files are **symlinked** into `~/.config/hypr/` — the
checkout's copies are the live files (`AGENTS.md` › Live files).

---

## Testing

Two suites, both hermetic (the contract is in `AGENTS.md` › Tests); CI runs
them in an `archlinux:latest` container, as root.

```
tests/                            # lib/ is on sys.path through pyproject's `pythonpath`
├── unit/
│   ├── test_config_exec_targets.py  # every hyprconf-* command a shipped hypr/*.lua binds ships in bin/, bound by name
│   ├── test_firefox.py           #   infra/firefox/policies.json: the captured settings, both force-installed extensions, every pref against Firefox's own allowlist, and the merge as a superset of the installed Omarchy policy (read-only; the install suite's fixture of it elsewhere)
│   ├── test_firefox_theme.py     #   lib/hyprconf/firefox_theme.py (profiles, copy, user.js merge, the missing-render error, --status) + the hook + the template's render
│   ├── test_gaps.py              #   bin/hyprconf-gaps (fake hyprctl, real jq)
│   ├── test_help.py              #   bin/hyprconf-help (the header one-liner convention every bin tool must carry, the listing, the @HYPRCONF_DIR@ fallback; jq real when present)
│   ├── test_hypr_overrides.py    #   hypr/*.lua parse (luac), state the deltas the README promises (natural scroll, Steam tiled), restate none of Omarchy's binds, leave the OSD keys alone, describe every bind, use its launcher idiom
│   ├── test_monitor_preset.py    #   bin/hyprconf-monitor-preset (the toggle-file contract, stock, workspace rehoming)
│   ├── test_no_pii.py            #   every file in the checkout (on-disk walk), identities derived at runtime
│   ├── test_omarchy_install.py   #   install.sh: every stage (curl bootstrap, banner, menu block, the `omarchy refresh` guard, the plugin sync and its `omarchy plugin add` checkout guard …), the post-update hook end to end, restraint invariants, idempotency; bin/hyprconf-install-service-protonvpn; `bash -n` and the dead-hyprctl / pacman token scans over every shipped bash file; real qmllint on plugins/*/*.qml and omarchy-plugin-validate on the installed plugin dirs
│   ├── test_plugins.py           #   plugins/*: omarchy-plugin-validate's checks in Python (CI has no Omarchy), the publishable shape (README, NOTICE, nothing of the overlay's, exec bits), Omarchy 4.0.2's Text.PlainText rule over every QML, the clock's parity with the installed stock clock (skips without Omarchy), the resources feeders' capped-backoff restart shape
│   ├── test_stats_tools.py       #   plugins/hyprconf-resources/bin/{hyprconf-stats,hyprconf-gpu-info} (fake proc/sysfs trees, nvidia-smi and the `sleep` between ticks; a bare-PATH run pins hyprconf-stats' fork-free tick)
│   ├── test_supply_chain.py      #   the published trust surface: web/ self-contained, https-only one-liners, sha-pinned least-privilege CI, the .claude guardrail entries
│   ├── test_vulkan_gpu.py        #   bin/hyprconf-vulkan-gpu (fake sysfs, gum and vulkaninfo; uwsm env.d / environment.d seams)
│   ├── test_yubikey.py           #   bin/hyprconf-yubikey (fake sudo/cryptenroll/limine-mkinitcpio; the limine drop-in, /etc/default/limine read for the mapper and never rewritten; real shellcheck on the mkinitcpio drop-in)
│   └── test_zshrc_block.py       #   zsh/zshrc.block: the hyprsync alias finds a relocated checkout
└── integration/
    ├── test_plugin_split.py      #   `git subtree split` of every plugins/<name> in a throwaway repository, the split's root held to test_plugins.py's contract (› Publishing a plugin)
    └── test_publish_pipeline.py  #   scripts/publish --help, --dry-run and the real promotion against a throwaway bare origin
```

### Running tests

```bash
make check               # the three commit gates: lint + shellcheck + test

make test                # both suites in parallel (pytest -n auto)
make test-unit
make test-integration

# Lint gates
make lint                # ruff check + ruff format --check
make shellcheck          # every bash script, severity=warning; plus SC2086 (info-level) on install.sh and hyprconf-yubikey — unquoted words in root-writing code
make fmt                 # ruff format + safe fixes
make clean
```

The gates need `ruff`, `shellcheck`, `python-pytest` and `python-pytest-xdist`
— official repos, the same Arch packages CI installs, so the versions match:
`omarchy pkg add ruff shellcheck python-pytest python-pytest-xdist`. `jq`,
`luac` and `qmllint` are used real by the tests that need them and skipped
when absent; `git` is required. CI's own package list, with the reason each
entry is there, lives in `.github/workflows/test.yml`; the two tests that
skip in CI, and the recipe for reproducing a container-only failure, are in
`AGENTS.md` › Gates and CI.

### Writing hermetic tests

- Every path a script reads is under `$HOME` (relocated wholesale by the
  suite) or behind an env seam — in `install.sh`, `OMARCHY_PATH` (Omarchy's own
  variable, not `_HYPRCONF_*`) for the Omarchy tree and `_HYPRCONF_*` for
  binaries and the other non-`$HOME` paths (`PKG_ADD`, `ZSH_BIN`, `ZSH`,
  `KITTY_BIN`, `FIREFOX_POLICIES`, `UDEV_RULES`, `ASSUME_TTY`, `PLUGIN_WAIT`); `_HYPRCONF_*` in
  `bin/hyprconf-yubikey` for the boot files it reads and writes (`MKINITCPIO_D`,
  `LIMINE_DEFAULT`, `LIMINE_CONF_D`, `LIMINE_ENTRY_CONF`, `LIMINE_USR_D`,
  `FIDO2_DROPIN`, `INITCPIO_INSTALL`, `MODULES_DIR`, `VCONSOLE`, `MACHINE_ID`,
  `EFI_DIR`);
  `_HYPRCONF_*` in `bin/hyprconf-vulkan-gpu` for the sysfs trees and env
  files it reads (`SYS_PCI`, `SYS_DRM`, `VULKANINFO`, `UWSM_ENV_D`, `UWSM_ENV`,
  `ENVIRONMENT_D`, `STATE`, `ASSUME_TTY`),
  `HYPRCONF_STATS_*` in `plugins/hyprconf-resources/bin/hyprconf-stats`
  (`NET_ROOT`, `PROC_STAT`, `PROC_MEMINFO`, `PROC_ROUTE`, `HWMON_ROOT`,
  `INTERVAL`, `ITERATIONS`, and `SLEEP_BUILTIN` — the loadable sleep's path,
  pointed at a file that is not there so a PATH `sleep` fake runs between
  ticks) and `HYPRCONF_GPU_*` in its sibling `hyprconf-gpu-info` (`INTERVAL`,
  `DRM_ROOT`, `ITERATIONS`, `PCI_IDS`) — pointed at `tmp_path`. Never make
  such a variable `readonly`.
- The fake bins (`AGENTS.md` › Tests): `omarchy-*`, `hyprctl`, `sudo`, `chsh`,
  `fc-list`, `systemd-cryptenroll`, `limine-mkinitcpio`, `gum`, `udevadm` (the real
  one would re-apply rules on the developer's own machine), `vulkaninfo` (it
  would answer for the host's GPUs), `nvidia-smi` (likewise), `sleep` (the
  feeders' hook between ticks: it advances the fake counters and mutates the
  fake trees, then runs the real sleep), `git` (a clone only makes its directory —
  the curl-path tests let a clone of a local directory run the real git — the
  pinned fetch/checkout/rev-parse dance against the two third-party shell
  dirs is faked through marker files, and a pull is a no-op; the real git
  otherwise runs only inside a throwaway checkout under `tmp_path`, never
  the repository the suite runs from) …
  `/usr/bin` carries
  every `omarchy-*` command (427 on Omarchy 4.0.2-1 — `pacman -Ql omarchy | grep -c /usr/bin/omarchy-`; 432 with `omarchy-settings`' and `omarchy-nvim`'s), so a PATH of fakes plus
  `/usr/bin` keeps none of them out: stub every one the code path can call
  (`OMARCHY_STUBS` and `_setup` in `test_omarchy_install.py` list the
  installer's, and `test_every_omarchy_command_install_sh_calls_has_a_fake`
  holds `install.sh`'s code to that list;
  `test_firefox_theme.py` stubs the three theme commands to prove the Firefox
  bridge calls none). Real when present, skipped otherwise: `jq`, `luac`,
  `qmllint`, `shellcheck`, `sh`, `/usr/share/omarchy/bin/omarchy-plugin-validate`
  (reads a manifest, changes nothing), the installed clock plugin's files
  (`test_plugins.py` reads them for parity) and, for the one test that builds a PATH
  without `gum` (`test_vulkan_gpu.py`), `bash`, `awk`, `grep`, `sed`,
  `readlink`, `cat`, `mkdir`, `rm`.
  A test that reads a file of the installed Omarchy falls back to a
  fixture instead of skipping (`test_firefox.py` reuses `OMARCHY_FIREFOX_POLICY`
  and, with Omarchy present, checks it against the real file). Never invoke
  `pacman` (it exists in the container).

### CI

`.github/workflows/test.yml` runs two jobs on every push and PR to any branch,
both inside `archlinux:latest` as root, in a runner-owned workspace with no
git-trust step: **Lint** (`make shellcheck` + `make lint`) and **Unit +
Integration** (`make test`, the target `scripts/publish` gates on). Both must
be green before a publish; the recipe for reproducing a container-only
failure is in `AGENTS.md` › Gates and CI.

---

## Security

The overlay is published: strangers clone `stable` and run `install.sh` with their own sudo. Three trust boundaries, each held by mechanical pins (AGENTS.md hard rule 8):

1. **Unprivileged → root, on the local box.** The four sudo stages, `hyprconf-yubikey`'s `run_root` surface, and `hyprconf-install-service-protonvpn`'s package install (rule 6 names all of them) are the only privileged paths. Root coreutils calls keep the `--` end-of-options shape (pinned in `test_yubikey.py`'s restraint scan); installed tools are rendered beside the target and `mv`'d, never truncated in place; the `packages` file holds plain package names only (`test_packages_file_lines_are_plain_package_names`). A new root write or sudo stage names itself in README (rule 6) and lands with a pin.
2. **Untrusted content → local execution.** Window titles and feeder strings render as plain text (`textFormat: Text.PlainText`, stock parity); nothing shipped fetches-and-executes — `test_overlay_never_fetches_and_executes` forbids curl/wget/pipe-to-shell/`base64 -d`/`eval` in shipped bash, with the allowed exceptions written down in full inside the test. A new exception is added there verbatim, with its why, or the change does not land.
3. **Publish pipeline → strangers' boxes.** The bootstrap is https-only (`--proto '=https'`; `test_published_one_liners_are_https_only`, `test_bootstrap_defaults_are_pinned_https_and_stable` — schemeless, curl's first request is plaintext port 80 and an on-path attacker answers it before the redirect exists). Oh My Zsh and powerlevel10k are pinned to reviewed commits in `stage_shell` — bumping a pin is a deliberate commit through the publish gates, never an auto-pull (`test_shell_third_party_repos_are_pinned_and_never_pulled`) — and `zsh/zshrc.block` disables the updater that ships inside Oh My Zsh itself (`zstyle ':omz:update' mode disabled`, pinned in `test_supply_chain.py`), which would otherwise re-open the channel with one keypress. CI actions are sha-pinned under a read-only token (`test_ci_workflow_is_least_privilege`); `scripts/publish` refuses `--skip-tests` outside the harness marker; `web/` stays self-contained (`test_web_page_is_self_contained`); secret-shaped material anywhere in the tree fails `test_no_secret_material_anywhere`; `install.sh` refuses to run as root (the curl|bash sudo-prefix habit half-installs into /root).

The checklist for any change: does it add a network touch, execute anything it did not ship with, widen a root path or a udev match, or move bytes from an untrusted source toward a shell, QML or root sink? Then the matching pin above changes in the same commit, its reasoning beside it. A pin loosened without its why is a finding, not a diff.

## Branches

| Branch | Purpose |
|--------|---------|
| `dev` | All active development |
| `stable` | What users clone; written only by `scripts/publish` |

## Publishing to stable

```bash
bash scripts/publish            # from a clean, pushed `dev` checkout
```

1. Verifies the working branch, a clean tree, and that local `dev` matches its remote
2. Lint gates: `make lint` + `make shellcheck`
3. Test suites: `make test`
4. Bumps the version in `lib/hyprconf/__init__.py`, commits it and pushes the commit to `origin/dev` (after the suite is green)
5. Creates the annotated tag `v<version>` and promotes `HEAD` to `origin/stable`
6. **When the user asks for a deploy, right after: upload `stable`'s
   `install.sh` and invalidate CloudFront** (the objects under "Updating the
   website" below). `scripts/publish` deploys nothing, so until that upload
   `hyprconf.sh` keeps serving the previous release's `install.sh` to curl —
   whatever that file does.

Nothing is packaged: users `git clone -b stable`, so the promoted branch is the release.

| Flag | Effect |
|------|--------|
| `--patch` / `--minor` / `--major` | Which version component to bump (default: patch) |
| `--skip-bump` | Skip the version bump (version must be pre-bumped manually) |
| `--skip-tests` | Skip the lint gates and test suites (nested harness calls only — the suite must still have passed) |
| `--skip-tag` | Skip annotated release-tag creation |
| `--dry-run` | Run every gate and resolve the tag, but push nothing (the version bump is reverted) |

`tests/integration/test_publish_pipeline.py` runs the script end to end
against a throwaway bare origin (a recording `make` stub stands in for the
gates): `--help`, `--dry-run` (gates run, bump reverted, nothing pushed), the
real promotion (bump commit on `origin/dev`, `origin/stable` == `dev`,
annotated tag), the bump flags, the dirty-tree / off-branch refusals, and the
resume of a publish that died after its bump commit (`--skip-bump`; a plain
rerun is refused so the tag is never cut twice).

## Publishing a plugin

`omarchy plugin add <url>` clones a repository and expects `manifest.json` at
its root — `bin/omarchy-plugin-add` (Omarchy 4.0.2-1): `git clone`,
`omarchy-plugin-validate`, then a move to `~/.config/omarchy/plugins/<id>/`
— so the monorepo cannot be added as it is. Each `plugins/<name>` folder is
published as a repository of its own, split out of `dev`'s history with git's
own tool (history and the `100755` modes travel with it):

```bash
git subtree split --prefix=plugins/hyprconf-resources -b plugins/hyprconf-resources
git push git@github.com:ak4dev/omarchy-hyprconf-resources.git plugins/hyprconf-resources:main
```

Never run here: a push is the user's, on request, like every other. The
folder is the whole plugin — everything a split needs lives inside it:
`manifest.json`, `README.md` (the install line, dependencies, settings, what
`omarchy plugin disable` / `remove` do to it), `NOTICE` where the code is
Omarchy's (MIT requires its notice on every copy), and any script the widget
runs, under `bin/`, resolved from the plugin's own directory and never from
`PATH`. `tests/unit/test_plugins.py` pins that shape and the validator's own
checks; `tests/integration/test_plugin_split.py` runs the split in a
throwaway repository and holds the result to the same contract. The
manifest's `version` (SemVer) is bumped once per set of changes that reaches
a consumer and is never left behind a shipped one — a series of commits on
`dev` takes one bump between publishes, not one each. A published plugin is
listed on the community directory,
<https://omarchyplugins.com>; the URL each README names,
`https://github.com/ak4dev/omarchy-hyprconf-<name>`, is the placeholder until
the repositories exist. The overlay keeps syncing the same folders from the
checkout, and `install.sh` leaves a folder that is a git checkout (`omarchy
plugin add`'s) to `omarchy plugin update`.

## Updating the website

`hyprconf.sh` is the `hyprconf-sh` S3 bucket behind a CloudFront distribution
that routes on the User-Agent: browsers get the `index.html` object, `curl` and
`wget` get the `install.sh` object — which is what makes
`bash <(curl -fsSL --proto '=https' https://hyprconf.sh)` work. That router is existing infrastructure
outside this repo, managed by hand; there is no deploy tooling (`aws` comes
from `omarchy-pkg-add aws-cli-v2`, an official `extra` package), and the upload
happens only when the user asks for a deploy. Four objects, and the `install.sh`
one must be the **`stable`** branch's — upload it after `scripts/publish`, never
the `dev` copy. The page itself is fixed in shape: the `assets/banner.svg` art
as the brand (inline SVG, never scrolls), a tiling glyph and a `user@omarchy`
prompt on the install block, one centred GitHub button, compact, no JS and no
external requests:

| Key | Source | Content-Type |
|---|---|---|
| `install.sh` | `git show stable:install.sh` | `text/plain; charset=utf-8`, `Cache-Control: no-cache, no-store` |
| `index.html` | `web/index.html` | `text/html; charset=utf-8`, `Cache-Control: public, max-age=300` — without a max-age browsers keep the previous page for days (heuristic freshness) |
| `favicon.svg` | `web/favicon.svg` | `image/svg+xml`, `Cache-Control: public, max-age=31536000, immutable` |
| `screenshot.svg` | `assets/screenshot.svg` | `image/svg+xml`, `Cache-Control: public, max-age=300` — the placeholder; the real capture replaces it under the same key. If that capture is a raster, the key, `web/index.html`'s `src` and the README path change together |

```bash
git show stable:install.sh | aws s3 cp - s3://hyprconf-sh/install.sh \
  --content-type 'text/plain; charset=utf-8' --cache-control 'no-cache, no-store'
aws s3 cp web/index.html        s3://hyprconf-sh/index.html     --content-type 'text/html; charset=utf-8' --cache-control 'public, max-age=300'
aws s3 cp web/favicon.svg       s3://hyprconf-sh/favicon.svg    --content-type image/svg+xml --cache-control 'public, max-age=31536000, immutable'
aws s3 cp assets/screenshot.svg s3://hyprconf-sh/screenshot.svg --content-type image/svg+xml --cache-control 'public, max-age=300'

DIST=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items,'hyprconf.sh')].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*"
```

Verify both routes once the invalidation has completed — the curl UA must get
`stable`'s installer, a browser UA the page:

```bash
curl -fsSL https://hyprconf.sh | cmp - <(git show stable:install.sh) && echo installer-ok
curl -fsSL -A 'Mozilla/5.0' https://hyprconf.sh | cmp - web/index.html && echo page-ok
curl -sSI -A 'Mozilla/5.0' https://hyprconf.sh/screenshot.svg | grep -i '^content-type: image/svg+xml'
```
