# Contributing to hyprconf

hyprconf is an overlay for [Omarchy](https://omarchy.org) — `README.md` opens
with the contract. Read [`AGENTS.md`](../AGENTS.md) first — its rules (use
Omarchy's own tools, never work from memory about Omarchy, the package rule,
no PII, hermetic tests) bind every change.

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
│   ├── pcMonitors.lua          # Preset "pc"
│   ├── pcMonitors.bedroom.lua  # Preset "bedroom"  (SUPER+SHIFT+B)
│   ├── pcMonitors.kitchen.lua  # Preset "kitchen"  (SUPER+SHIFT+K)
│   ├── pcMonitors.K.lua        # Preset "K"
│   └── laptopMonitors.lua      # Preset "laptop"
│
├── bin/                        # Tools installed by install.sh (→ ~/.local/bin, @HYPRCONF_DIR@ substituted); the hotkeys bind the first two by name
│   ├── hyprconf-monitor-preset #   copy a preset into Omarchy's toggles dir (~/.local/state/omarchy/toggles/hypr), reload, rehome workspaces; `stock` removes it
│   ├── hyprconf-gaps           #   SUPER+SHIFT+= / - via hyprctl eval
│   ├── hyprconf-stats          #   cpu/mem/net/temp JSON stream for the bar widget
│   ├── hyprconf-gpu-info       #   GPU JSON stream (nvidia-smi --loop or AMD sysfs)
│   ├── hyprconf-yubikey        #   FIDO2 unlock of the LUKS2 root at boot (enroll/disable/remove/status); a limine-entry-tool drop-in, the way Omarchy adds kernel parameters
│   ├── hyprconf-vulkan-gpu     #   Dual-GPU box: pin Vulkan (Steam/Proton) to the display GPU via uwsm env.d (status/prompt/fix/alt/ignore/remove)
│   ├── hyprconf-firefox-theme  #   launcher for firefox_theme.py (apply / --status)
│   └── hyprconf-install-service-protonvpn  # Proton VPN via omarchy-pkg-add; run by the menu row stage_menu adds
│
├── lib/hyprconf/               # Python package, used in place via PYTHONPATH (theme-set hook, hyprconf-firefox-theme)
│   ├── firefox_theme.py        # Omarchy's rendered userChrome.css into Firefox/LibreWolf profiles + user.js prefs (theme-set hook)
│   └── __init__.py             # __version__ (bumped by scripts/publish)
│
├── plugins/hyprconf-resources/ # Omarchy bar-widget plugin (manifest.json + Widget.qml)
├── plugins/hyprconf-workspaces/ # Omarchy bar-widget plugin replacing omarchy.workspaces (clonedFrom)
├── plugins/hyprconf-active-window/ # Omarchy bar-widget plugin replacing omarchy.active-window (two-line title)
├── themes/dracula/             # Omarchy user theme (colors.toml + backgrounds/)
├── themed/userChrome.css.tpl   # Omarchy user template (→ ~/.config/omarchy/themed/), rendered by omarchy-theme-set-templates on every theme set
├── wallpapers/                 # Extra backgrounds, filed per Omarchy theme
├── zsh/                        # zshrc.block (managed ~/.zshrc block), .p10k.zsh
├── kitty/hyprconf.conf         # kitty include
├── fastfetch/config.jsonc      # Greeting layout
├── hooks/post-update.d/10-hyprconf   # Re-applies the overlay after omarchy-update (installed with omarchy hook install)
├── hooks/theme-set.d/10-hyprconf     # Runs firefox_theme.py after every omarchy theme set
├── infra/firefox/policies.json # System Firefox privacy policy, installed merged over Omarchy's default/firefox/policies.json
│
├── tests/                      # Unit + integration (see below)
├── scripts/publish             # Lint + test → promote dev → stable
├── docs/                       # This file, hyprland-reference.md, quickshell-reference.md
├── .github/                    # CI workflow
├── web/, assets/               # index.html + favicon.svg (static landing page); banner.svg, screenshot.svg (placeholder shown by the README and the page)
├── Makefile, pyproject.toml    # Test/lint targets; pytest/ruff/coverage config
├── .editorconfig, .gitignore   # Editor indent/EOL defaults per file type; caches and artefacts git ignores
└── AGENTS.md, README.md
```

Files the installer writes live in `$HOME` only (plus the Firefox policy under
`/etc/firefox/policies/`; Firefox and VS Code themselves are installed by
Omarchy's own `omarchy-install-browser` / `omarchy-install-editor-vscode`). The
`hypr/*.lua` override files are **symlinked** into `~/.config/hypr/`, so the
checkout's copies are the live files — edit them there and re-run `bash install.sh`.

---

## Testing

Two suites, both hermetic — no Hyprland or Omarchy shell, no host tool that
touches the desktop, no real `$HOME`. They run in an `archlinux:latest` container in CI, as root.
There are no VM or install suites: behaviour that needs a live Omarchy session
is verified by hand and recorded in the commit message.

```
tests/                            # lib/ is on sys.path through pyproject's `pythonpath`
├── unit/
│   ├── test_config_exec_targets.py  # every hyprconf-* command and ~/-anchored path a shipped config references ships
│   ├── test_firefox.py           #   infra/firefox/policies.json; the merge is a superset of the installed Omarchy policy (read-only; the install suite's fixture of it elsewhere)
│   ├── test_firefox_theme.py     #   lib/hyprconf/firefox_theme.py (profiles, copy, user.js merge, the missing-render error, --status) + the hook + the template's render
│   ├── test_gaps.py              #   bin/hyprconf-gaps (fake hyprctl, real jq)
│   ├── test_hypr_overrides.py    #   hypr/*.lua state the deltas the README promises (Steam tiled …), restate none of Omarchy's binds, use its launcher idiom
│   ├── test_monitor_preset.py    #   bin/hyprconf-monitor-preset (the toggle-file contract, stock, workspace rehoming, hyprlang refusal)
│   ├── test_no_pii.py            #   every tracked file, identities derived at runtime
│   ├── test_omarchy_install.py   #   install.sh: every stage (curl bootstrap, banner, menu block, monitors.lua migration …), restraint invariants, idempotency; bin/hyprconf-install-service-protonvpn; real qmllint on plugins/*/*.qml and omarchy-plugin-validate on the installed plugin dirs
│   ├── test_stats_tools.py       #   bin/hyprconf-stats, bin/hyprconf-gpu-info
│   ├── test_vulkan_gpu.py        #   bin/hyprconf-vulkan-gpu (fake sysfs, gum and vulkaninfo; uwsm env.d / environment.d seams)
│   ├── test_yubikey.py           #   bin/hyprconf-yubikey (fake sudo/cryptenroll/limine-update; the limine drop-in, /etc/default/limine read-only, the v4.0.0–v4.2.0 inline-parameter migration; real shellcheck on the mkinitcpio drop-in)
│   └── test_zshrc_block.py       #   zsh/zshrc.block: the hyprsync alias finds a relocated checkout
└── integration/
    └── test_publish_pipeline.py  #   scripts/publish --help, --dry-run and the real promotion against a throwaway bare origin
```

### Running tests

```bash
make test                # both suites in parallel (pytest -n auto)
make test-unit
make test-integration
make test-seq            # both suites sequentially (clearer output)

# Coverage (optional, local only — needs python-pytest-cov; config in pyproject.toml)
pytest tests/unit/ tests/integration/ --cov=hyprconf --cov-report=term-missing

# Lint gates
make lint                # ruff check + ruff format --check
make shellcheck          # every bash script, severity=warning
make fmt                 # ruff format + safe fixes
make clean
```

Python deps for the suite: `python-pytest`, `python-pytest-xdist` (official
repos). `jq`, `shellcheck`, `luac`, `qmllint` and `git` are used real by the
tests that need them and skipped when absent — CI installs `jq`, `shellcheck`,
`lua` and `qt6-declarative` (`qmllint`, under `/usr/lib/qt6/bin`) so none of
those skip there, plus `diffutils` for the `cmp` `install.sh` runs (Omarchy has
it through mkinitcpio; the bare `archlinux:latest` container does not). The
one test CI does skip is `test_installed_plugins_pass_omarchy_plugin_validate`
(it needs the installed `/usr/share/omarchy/bin/omarchy-plugin-validate`,
which no package provides in the container); it runs on every Omarchy box.
Every other test runs in CI — a second skip there is a regression.

### Writing hermetic tests

- Every path a script reads is under `$HOME` (relocated wholesale by the
  suite) or behind an env seam — `_HYPRCONF_*` in `install.sh` for binaries and
  non-`$HOME` paths (`OMARCHY_PATH`, `PKG_ADD`, `ZSH_BIN`, `ZSH`, `KITTY_BIN`,
  `FIREFOX_POLICIES`, `ASSUME_TTY`, `PLUGIN_WAIT`), `_HYPRCONF_*` in
  `bin/hyprconf-yubikey` for the boot files it reads and writes (`MKINITCPIO_D`,
  `LIMINE_DEFAULT`, `LIMINE_CONF_D`, `LIMINE_ENTRY_CONF`, `LIMINE_USR_D`,
  `FIDO2_DROPIN`, `VCONSOLE`, `MACHINE_ID`, `EFI_DIR`, …),
  `_HYPRCONF_*` in `bin/hyprconf-vulkan-gpu` for the sysfs trees and env
  files it reads (`SYS_PCI`, `SYS_DRM`, `VULKANINFO`, `UWSM_ENV_D`, `UWSM_ENV`,
  `ENVIRONMENT_D`, `STATE`, `ASSUME_TTY`),
  `HYPRCONF_STATS_*` / `HYPRCONF_GPU_*` in the feeders — pointed at
  `tmp_path`. Never make such a variable `readonly`.
- Every command that could touch the desktop or the system — `omarchy-*`,
  `hyprctl`, `sudo`, `chsh`, `fc-list`, `systemd-cryptenroll`, `limine-update`,
  `gum`, `vulkaninfo` (it would answer for the host's GPUs), `git clone`/`pull` …
  — is **always** a fake bin first on `PATH`; a test must
  never reach a real binary that changes the desktop. `/usr/bin` carries a
  copy of every `omarchy-*` command (426 on Omarchy 4.0.0-1), so a PATH of
  fakes plus `/usr/bin` does not keep the real ones out: stub every
  `omarchy-*` the code path can call (`_setup` in `test_omarchy_install.py`
  lists the installer's; `test_firefox_theme.py` stubs Omarchy's three theme
  commands to prove the Firefox bridge calls none of them). Pure tools are real when
  present and the test skips otherwise: `jq`, `luac`, `qmllint`, `cp`, `python3`,
  `shellcheck`, `/usr/share/omarchy/bin/omarchy-plugin-validate` (reads a
  manifest, changes nothing), and `git` `init`/`add`/`commit`/`checkout` — plus, for the curl-path tests, a
  `clone` whose source is a local directory — inside a throwaway clone under
  `tmp_path`; never the repository the suite runs from. A test that reads a
  file of the installed Omarchy falls back to a fixture of it instead of
  skipping (`test_firefox.py` reuses the install suite's `OMARCHY_FIREFOX_POLICY`
  and, with Omarchy present, checks the fixture against the real file). Never invoke `pacman`
  (it exists in the container). `tests/unit/test_omarchy_install.py` shows the
  pattern: fake `omarchy-*` binaries that record their calls, a throwaway
  `HOME`, and assertions about what the installer must *not* do.
- CI runs as root, which bypasses DAC checks — reproduce permission-sensitive
  tests with `unshare -r python -m pytest <file>`.
- `tests/unit/test_no_pii.py` scans every tracked file for the login name, home
  directory, hostname and git email, derived at runtime. Use `~`, `$HOME`,
  `testuser` in fixtures.
- Never weaken a test to get green: an intended behaviour change updates the
  test to the new contract, in the same commit, and says so.

### CI

`.github/workflows/test.yml` runs two jobs on every push and PR, both inside
`archlinux:latest`: **Lint** (`make shellcheck` + `make lint`) and **Unit +
Integration** (`make test`). Both must be green before a publish. Reproduce
the test job in the same container before a push (`docker` works the same):

```bash
podman run --rm -v "$PWD":/repo -w /repo archlinux:latest bash -c \
  'pacman -Syu --noconfirm --needed git make python python-pytest python-pytest-xdist jq shellcheck diffutils lua qt6-declarative &&
   make test'
```

---

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
6. **By hand, right after — upload `stable`'s `install.sh` and invalidate
   CloudFront** (the objects under "Updating the website" below), before
   anything points users at `bash <(curl -fsSL hyprconf.sh)`: `scripts/publish`
   deploys nothing, so until that upload `hyprconf.sh` keeps serving the
   previous release's `install.sh` to curl — whatever that file does.

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
annotated tag), the bump flags, and the dirty-tree / off-branch refusals.

## Updating the website

`hyprconf.sh` is the `hyprconf-sh` S3 bucket behind a CloudFront distribution
that routes on the User-Agent: browsers get the `index.html` object, `curl` and
`wget` get the `install.sh` object — which is what makes
`bash <(curl -fsSL hyprconf.sh)` work. That router is existing infrastructure
outside this repo, managed by hand; there is no deploy tooling (`aws` comes
from `omarchy-pkg-add aws-cli-v2`, an official `extra` package). Four objects,
and the `install.sh` one must be the **`stable`** branch's — upload it after
`scripts/publish`, never the `dev` copy:

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
curl -fsSL hyprconf.sh | cmp - <(git show stable:install.sh) && echo installer-ok
curl -fsSL -A 'Mozilla/5.0' hyprconf.sh | cmp - web/index.html && echo page-ok
curl -sSI -A 'Mozilla/5.0' https://hyprconf.sh/screenshot.svg | grep -i '^content-type: image/svg+xml'
```
