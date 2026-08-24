# Contributing to hyprconf

hyprconf is an overlay for [Omarchy](https://omarchy.org). Read
[`AGENTS.md`](../AGENTS.md) first — its rules (use Omarchy's own tools, never
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
│   ├── hyprland.block.lua      # Managed block appended to ~/.config/hypr/hyprland.lua
│   │                           #   (loadfile()s conf.d/{local,windowrules,workspacerules}.lua)
│   ├── pcMonitors.lua          # Preset "pc"
│   ├── pcMonitors.bedroom.lua  # Preset "bedroom"  (SUPER+SHIFT+B)
│   ├── pcMonitors.kitchen.lua  # Preset "kitchen"  (SUPER+SHIFT+K)
│   ├── pcMonitors.K.lua        # Preset "K"
│   ├── laptopMonitors.lua      # Preset "laptop"
│   └── scripts/
│       ├── switch_monitor.sh   # Symlink a preset over monitors.lua, reload, rehome workspaces
│       └── adjust-gaps         # SUPER+SHIFT+= / - via hyprctl eval
│
├── bin/
│   ├── hyprconf                # TUI launcher (→ ~/.local/bin)
│   ├── hyprconf-stats          # cpu/mem/net/temp JSON stream for the bar widget
│   └── hyprconf-gpu-info       # GPU JSON stream (nvidia-smi --loop or AMD sysfs)
│
├── lib/hyprconf/               # Python library (→ ~/.local/lib/hyprconf)
│   ├── schema.py               # OPTION_SCHEMA + SECTION_ORDER — single source of truth
│   ├── config.py               # conf.d/local.lua reader/writer
│   ├── keybinds.py             # bindings.lua reader/writer
│   ├── rules.py                # window/workspace rule reader/writer
│   ├── monitors.py             # monitors.lua reader/writer
│   ├── hyprctl.py              # hyprctl IPC wrapper
│   ├── file_edit.py            # Atomic line-editing primitives
│   ├── block_conf.py           # Generic block-format parser
│   ├── lua_syntax.py           # Lua comment/value/single-line-call primitives
│   ├── paths.py                # XDG path constants
│   └── __init__.py             # __version__
├── tui/main.py                 # Textual TUI (→ ~/.config/hypr/scripts/hyprconf-tui)
│
├── plugins/hyprconf-resources/ # Omarchy bar-widget plugin (manifest.json + Widget.qml)
├── plugins/hyprconf-workspaces/ # Omarchy bar-widget plugin replacing omarchy.workspaces (clonedFrom)
├── themes/hyprconf/            # Omarchy user theme (colors.toml + backgrounds/)
├── wallpapers/                 # Extra backgrounds, filed per Omarchy theme
├── zsh/                        # zshrc.block (managed ~/.zshrc block), .p10k.zsh
├── kitty/hyprconf.conf         # kitty include
├── fastfetch/config.jsonc      # Greeting layout
├── hooks/post-update.d/10-hyprconf   # Omarchy post-update hook
├── infra/firefox/policies.json # System Firefox privacy policy
│
├── tests/                      # Tiers 1-3 (see below)
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

Three tiers, all hermetic — no Hyprland or Omarchy shell, no host tools, no real
`$HOME`. They run in an `archlinux:latest` container in CI, as root.

```
tests/
├── conftest.py              # hypr_dir fixture: isolated ~/.config/hypr in tmp_path
├── unit/                    # Tier 1 — library modules, shipped scripts, install.sh, guards
├── integration/             # Tier 2 — publish pipeline plumbing (git archive, publish --dry-run)
└── tui/                     # Tier 3 — Textual Pilot, headless
```

### Running tests

```bash
make test                # tiers 1-3 in parallel (pytest -n auto)
make test-unit           # tier 1
make test-integration    # tier 2
make test-tui            # tier 3 (needs python-textual + python-pytest-asyncio)
make test-seq            # all tiers sequentially (clearer output)

# Coverage (what CI reports for tiers 1-2)
pytest tests/unit/ tests/integration/ --cov=lib/hyprconf --cov-report=term-missing

# Lint gates
make lint                # ruff check + ruff format --check
make shellcheck          # every bash script, severity=warning
make fmt                 # ruff format + safe fixes
make typecheck           # mypy lib/hyprconf (informational)
make clean
```

Python deps for the suite: `python-pytest`, `python-pytest-xdist`,
`python-pytest-asyncio`, `python-pytest-cov`, `python-textual` (all official
repos; `pyproject.toml`'s `test` extra lists the same set for a venv).

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

`.github/workflows/test.yml` runs three jobs on every push and PR, all inside
`archlinux:latest`: **Lint** (`make shellcheck` + `make lint`), **Unit +
Integration** (tiers 1-2 with coverage) and **TUI** (tier 3). All three must be
green before a publish.

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
3. Tiers 1-3: `make test`
4. Bumps the version in `lib/hyprconf/__init__.py` and commits it (after the suite is green)
5. Builds a filtered release archive with `git archive` + `.gitattributes` `export-ignore`
   (excludes `tests/`, `scripts/`, `.github/`, `web/`, `docs/`, `AGENTS.md`, `Makefile`,
   `.editorconfig`, `pyproject.toml`, `__pycache__/`, `*.pyc`)
6. Creates the annotated tag `v<version>` and promotes `HEAD` to `origin/stable`

| Flag | Effect |
|------|--------|
| `--patch` / `--minor` / `--major` | Which version component to bump (default: patch) |
| `--skip-bump` | Skip the version bump (version must be pre-bumped manually) |
| `--skip-tests` | Skip the lint gates and test tiers (nested harness calls only — the suite must still have passed) |
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
