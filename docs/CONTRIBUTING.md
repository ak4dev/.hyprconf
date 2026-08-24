# Contributing to hyprconf

hyprconf is a lean deployment mechanism — `install.sh` plus the shipped
payload — that ports the hyprconf configuration suite's functionality onto a
stock [Omarchy](https://omarchy.org) install through Omarchy's own tools and
seams. Read [`AGENTS.md`](../AGENTS.md) first — its rules (use Omarchy's own tools, never
work from memory about Omarchy, official repos only, no PII, hermetic tests)
bind every change.

## Repository Layout

```
.hyprconf/
├── install.sh                  # The overlay installer — idempotent stages, the only entry point
├── packages                    # Official-repo packages, installed via omarchy-pkg-add
│
├── hypr/
│   ├── bindings.lua            # Hotkeys (o.bind with descriptions; unbind-then-rebind)
│   ├── input.lua               # Input/gesture deltas from Omarchy's defaults
│   ├── looknfeel.lua           # Look'n'feel deltas from Omarchy's defaults
│   ├── pcMonitors.lua          # Preset "pc"
│   ├── pcMonitors.bedroom.lua  # Preset "bedroom"  (SUPER+SHIFT+B)
│   ├── pcMonitors.kitchen.lua  # Preset "kitchen"  (SUPER+SHIFT+K)
│   ├── pcMonitors.K.lua        # Preset "K"
│   ├── laptopMonitors.lua      # Preset "laptop"
│   └── scripts/
│       ├── switch_monitor.sh   # Symlink a preset over monitors.lua, reload, rehome workspaces
│       └── adjust-gaps         # SUPER+SHIFT+= / - via hyprctl eval
│
├── bin/                        # Tools installed by install.sh (→ ~/.local/bin), e.g.
│   ├── hyprconf-stats          #   cpu/mem/net/temp JSON stream for the bar widget
│   └── hyprconf-gpu-info       #   GPU JSON stream (nvidia-smi --loop or AMD sysfs)
│
├── lib/hyprconf/               # Python package (→ ~/.local/lib/hyprconf)
│   ├── firefox_theme.py        # Firefox/LibreWolf chrome from Omarchy's theme (theme-set hook)
│   └── __init__.py             # __version__ (bumped by scripts/publish)
│
├── plugins/hyprconf-resources/ # Omarchy bar-widget plugin (manifest.json + Widget.qml)
├── plugins/hyprconf-workspaces/ # Omarchy bar-widget plugin replacing omarchy.workspaces (clonedFrom)
├── plugins/hyprconf-active-window/ # Omarchy bar-widget plugin replacing omarchy.active-window (two-line title)
├── themes/hyprconf/            # Omarchy user theme (colors.toml + backgrounds/)
├── wallpapers/                 # Extra backgrounds, filed per Omarchy theme
├── zsh/                        # zshrc.block (managed ~/.zshrc block), .p10k.zsh
├── kitty/hyprconf.conf         # kitty include
├── fastfetch/config.jsonc      # Greeting layout
├── hooks/post-update.d/10-hyprconf   # Re-applies the overlay after omarchy-update
├── hooks/theme-set.d/10-hyprconf     # Bridges a theme change to apps Omarchy does not theme
├── infra/firefox/policies.json # System Firefox privacy policy
│
├── tests/                      # Unit + integration (see below)
├── scripts/publish             # Lint + test → promote omarchy → stable
├── docs/                       # This file, hyprland-reference.md, quickshell-reference.md
├── .github/                    # CI workflow, copilot-instructions.md
├── web/, assets/               # Static landing page; banner + screenshot
├── Makefile, pyproject.toml    # Test/lint targets; pytest/ruff/coverage config
└── AGENTS.md, README.md
```

Files the installer writes live in `$HOME` only (plus the Firefox policy under
`/etc/firefox/policies/`). The `hypr/*.lua` override files are **symlinked** into
`~/.config/hypr/`, so the checkout's copies are the live files — edit them there
and re-run `bash install.sh`.

---

## Testing

Two suites, both hermetic — no Hyprland or Omarchy shell, no host tools, no real
`$HOME`. They run in an `archlinux:latest` container in CI, as root.

```
tests/
├── conftest.py              # puts lib/ on sys.path
├── unit/                    # install.sh, shipped scripts and bin/ tools, firefox_theme, guards
└── integration/             # publish pipeline plumbing (git archive, publish --dry-run)
```

### Running tests

```bash
make test                # both suites in parallel (pytest -n auto)
make test-unit
make test-integration
make test-seq            # both suites sequentially (clearer output)

# Coverage (what CI reports)
pytest tests/unit/ tests/integration/ --cov=lib/hyprconf --cov-report=term-missing

# Lint gates
make lint                # ruff check + ruff format --check
make shellcheck          # every bash script, severity=warning
make fmt                 # ruff format + safe fixes
make typecheck           # mypy lib/hyprconf (informational)
make clean
```

Python deps for the suite: `python-pytest`, `python-pytest-xdist`,
`python-pytest-cov` (all official repos; `pyproject.toml`'s `test` extra lists
the same set for a venv).

### Writing hermetic tests

- Every system path a script reads is env-overridable (`_HYPRCONF_*` in
  `install.sh`, `HYPRCONF_STATS_*` / `HYPRCONF_GPU_*` in the feeders) — point it
  at `tmp_path`. Never make such a variable `readonly`.
- Stub every external command with a fake bin on `PATH` (`omarchy-*`, `hyprctl`,
  `git`, `jq`, `fc-list`, `sudo`). `tests/unit/test_omarchy_install.py` shows the
  pattern: fake `omarchy-*` binaries that record their calls, a throwaway `HOME`,
  and assertions about what the installer must *not* do.
- CI runs as root, which bypasses DAC checks — reproduce permission-sensitive
  tests with `unshare -r python -m pytest <file>`.
- `tests/unit/test_no_pii.py` scans every tracked file for the login name, home
  directory, hostname and git email, derived at runtime. Use `~`, `$HOME`,
  `testuser` in fixtures.

### CI

`.github/workflows/test.yml` runs two jobs on every push and PR, both inside
`archlinux:latest`: **Lint** (`make shellcheck` + `make lint`) and **Unit +
Integration** (with coverage). Both must be green before a publish.

---

## Branches

| Branch | Purpose |
|--------|---------|
| `omarchy` | All active development |
| `stable` | What users clone; written only by `scripts/publish` |

## Publishing to stable

```bash
bash scripts/publish            # from a clean, pushed `omarchy` checkout
```

1. Verifies the working branch, a clean tree, and that local `omarchy` matches its remote
2. Lint gates: `make lint` + `make shellcheck`
3. Test suites: `make test`
4. Bumps the version in `lib/hyprconf/__init__.py` and commits it (after the suite is green)
5. Builds a filtered release archive with `git archive` + `.gitattributes` `export-ignore`
   (excludes `tests/`, `scripts/`, `.github/`, `web/`, `docs/`, `AGENTS.md`, `Makefile`,
   `.editorconfig`, `pyproject.toml`, `__pycache__/`, `*.pyc`)
6. Creates the annotated tag `v<version>` and promotes `HEAD` to `origin/stable`

| Flag | Effect |
|------|--------|
| `--patch` / `--minor` / `--major` | Which version component to bump (default: patch) |
| `--skip-bump` | Skip the version bump (version must be pre-bumped manually) |
| `--skip-tests` | Skip the lint gates and test suites (nested harness calls only — the suite must still have passed) |
| `--skip-tag` | Skip annotated release-tag creation |
| `--dry-run` | Build the release archive locally but do not push branches/tags |

`tests/integration/test_publish_pipeline.py` and `tests/unit/test_release.py`
pin the archive contents, the semver string and the branch constants.

## Updating the website

`web/index.html` is served from S3 + CloudFront at `hyprconf.sh`. There is no
deploy tooling; push changes manually:

```bash
aws s3 cp web/index.html    s3://hyprconf-sh/index.html    --content-type text/html
aws s3 cp web/hyprconf.webp s3://hyprconf-sh/hyprconf.webp --content-type image/webp

DIST=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items,'hyprconf.sh')].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*"
```
