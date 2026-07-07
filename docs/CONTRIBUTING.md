# Contributing to hyprconf

## Repository Layout

```
.hyprconf/
├── packages                  # Arch packages to install (one per line, comments ok)
├── setup.sh                  # Local bootstrap + sync entry point
│
├── assets/                   # Shared project assets
│   ├── banner.sh             # print_banner() — glitch palette + logo
│   └── banner.svg            # README header banner
│
├── docs/
│   ├── CONTRIBUTING.md       # This file
│   ├── hyprland-reference.md # Hyprland config syntax cheatsheet
│   └── security-hardening.md # Threat model + hardening reference (sysctls, SB, LUKS)
│
├── infra/
│   └── firefox/policies.json # System Firefox privacy policy (installed by setup.sh)
│
├── install/
│   └── install.sh            # Self-contained installer
│
├── scripts/
│   └── publish               # Run tests, promote dev → stable, build release archive
│
└── stow/                     # GNU Stow packages — symlinked into $HOME
    ├── hypr/
    │   ├── .config/hypr/
    │   │   ├── hyprland.conf           # Animations, layout, env vars
    │   │   ├── keybinds.conf           # All keybindings
    │   │   ├── gestures.conf
    │   │   ├── hyprpaper.conf
    │   │   ├── hyprlock.conf
    │   │   ├── hypridle.conf
    │   │   ├── laptopMonitors.conf
    │   │   ├── pcMonitors.conf / .bedroom / .kitchen
    │   │   ├── pcMonitors.K             # Desktop alt preset (monitorv2 block syntax)
    │   │   ├── conf.d/
    │   │   │   ├── 00-hyprconf.conf        # Source guard (includes conf.d glob)
    │   │   │   └── 99-hyprconf-local.conf  # Machine-local overrides (hyprconf set)
    │   │   └── scripts/
    │   │       ├── hyprconf-tui/main.py    # Textual TUI
    │   │       ├── switch_monitor.sh
    │   │       ├── toggle-native-display   # Toggle built-in laptop screen (eDP-1)
    │   │       └── theme-switcher/
    │   │           ├── switch_theme.py
    │   │           └── themes/             # Theme JSON files
    │   └── .local/
    │       ├── bin/hyprconf               # CLI entry point → ~/.local/bin/
    │       ├── bin/hyprconf-vpn           # NetworkManager VPN control + kill-switch
    │       ├── bin/yubikey-fido2-setup    # FIDO2+PIN enrolment (sudo/TTY/DM/SSH/LUKS)
    │       ├── bin/hyprconf-secureboot    # Signed-UKI Secure Boot setup + verify
    │       ├── bin/hyprconf-power-monitor # AC/battery power-profile switcher (udev target)
    │       ├── bin/…                      # + idle-action, autorotate, touch-panel*, wvkbd-*
    │       └── lib/hyprconf/              # Shared Python library
    │           ├── schema.py              # OPTION_SCHEMA — all Hyprland keys + types + defaults
    │           ├── config.py              # Read/write 99-hyprconf-local.conf
    │           ├── paths.py               # XDG path constants (single source of truth)
    │           ├── hyprctl.py             # hyprctl IPC wrapper
    │           ├── autodetect.py          # First-run config migration
    │           ├── cli.py                 # Python CLI backend
    │           ├── file_edit.py           # Atomic file operations
    │           ├── block_conf.py          # Generic block-format config parser
    │           ├── keybinds.py            # Keybind read/write
    │           ├── rules.py               # Window/workspace rule read/write
    │           ├── monitors.py            # Monitor config read/write
    │           ├── hyprlock.py            # hyprlock block read/write
    │           ├── hypridle.py            # hypridle block read/write
    │           ├── hyprpaper.py           # hyprpaper read/write
    │           └── __init__.py
    ├── btop/   kitty/   dunst/   fastfetch/   code-oss/
    └── quickshell/ wallpaper/
theme/                          # Vendor extension payloads (NOT under stow/)
    ├── firefox/extensions/
    └── .vscode-oss/extensions/
```

---

## Testing

hyprconf uses a **5-tier test architecture**. Tiers 1–3 require only Python and run without a Hyprland session; Tiers 4–5 are opt-in and require KVM.

```
tests/
├── conftest.py              # shared fixtures (isolated config dirs, mock hyprctl)
├── unit/                    # Tier 1 — pure Python, no Hyprland
├── integration/             # Tier 2 — Python CLI layer with mock hyprctl
├── tui/                     # Tier 3 — Textual Pilot (headless, no terminal needed)
├── vm/                      # Tier 4 — live Hyprland in QEMU/KVM (opt-in)
└── install/                 # Tier 5 — full Arch install smoke test (opt-in)
```

### Running tests

```bash
# Tier 1 — unit tests (fastest, no deps beyond pytest)
pytest tests/unit/

# Tier 2 — integration tests (mock hyprctl)
pytest tests/integration/

# Tier 3 — TUI tests (requires python-pytest-asyncio + python-textual)
pytest tests/tui/

# Tiers 1–3 together with coverage
pytest tests/unit/ tests/integration/ tests/tui/ --cov=stow/hypr/.local/lib/hyprconf

# Tier 4 — live Hyprland in QEMU (requires KVM; sudo modprobe kvm_amd first)
bash tests/vm/run_vm.sh           # start VM, wait for SSH
pytest tests/vm/ --run-vm -v

# Tier 5 — full Arch install smoke test
bash tests/install/build_image.sh   # first time only; ~20 min
bash tests/install/run_install_vm.sh
pytest tests/install/ --run-install -v

# Convenience via Makefile
make test            # Tiers 1–3
make test-vm         # Tier 4 (VM must be running)
make test-install    # Tier 5 (image must be built)
make build-vm-image  # runs build_image.sh
```

### Tier 5 install image

`build_image.sh` runs Packer to build a full Arch+hyprconf image (exercising `install.sh` end-to-end) and writes `tests/vm/arch-hyprconf.meta` with the build date and commit. The VM launches on port 2223 via `run_install_vm.sh` using a **COW overlay**, so the base image is never dirtied by test runs.

`scripts/publish` decides automatically whether to rebuild: it reuses the existing image **only** when the install-relevant paths (`install/`, `setup.sh`, `packages`) are byte-identical between `HEAD` and the commit the image was built from; any change there (or an unknown build commit) triggers a rebuild (~20 min, no prompt).

### Key fixtures (`tests/conftest.py`)

- `hypr_dir` — isolated `~/.config/hypr` in a `tmp_path`, monkeypatches all 9 module-level path constants so each test gets a clean slate
- `mock_hyprctl` — patches `subprocess.run` with canned JSON responses; tests pass even without `HYPRLAND_INSTANCE_SIGNATURE`

### CI

`.github/workflows/test.yml` — a lint job (`make shellcheck` + `make lint`) and Tiers 1–3 run on every push/PR via GitHub Actions, all inside `archlinux:latest` containers. Tiers 4–5 require a self-hosted runner with KVM (`.github/workflows/iso-watchdog.yml` runs the install tier weekly against the latest Arch ISO when such a runner is registered).

**Test packages** (`packages`): `python-pytest`, `python-pytest-asyncio`, `python-coverage`

---

## Branches

| Branch | Purpose |
|--------|---------|
| `dev` | All active development — tests, docs, scripts, configs |
| `stable` | Release-ready source branch with normal shared git history |

The model is `dev` → `stable` with shared history. User installs use a sparse checkout of `stable`; release archives are exported from the same commit via `git archive`.

---

## Publishing to stable

```bash
bash scripts/publish
```

`scripts/publish` handles the full pipeline automatically:

1. Verifies `dev` branch, a clean working tree, **and** that local `dev` is
   byte-identical to `origin/dev` (commit *and push* before publishing)
2. **Lint gates**: runs `make lint` (ruff check + format) and `make shellcheck`
   — a release can never be cut with a red lint job
3. Runs test tiers 1–3 (`make test`; aborts on any failure)
4. **Tier 5 — install image decision** (automatic, no prompt): reuses
   `tests/vm/arch-hyprconf.qcow2` only when `install/`, `setup.sh`, and
   `packages` are unchanged since the image's build commit; otherwise rebuilds
   via Packer (~20 min, exercising `install.sh` end-to-end)
5. Starts the tier-4 VM (if needed) and runs tier 4, then starts the tier-5 VM
   on port 2223 via COW overlay and runs tier 5; both are stopped on exit
6. **Version bump** (after the suite is green): bumps patch/minor/major in
   `__init__.py`, commits, and pushes to `origin/dev`
7. Builds a filtered release archive from `HEAD` using `git archive` + `.gitattributes`
8. Creates the annotated tag `v<hyprconf.__version__>` (unless it already points at `HEAD`)
9. Pushes `HEAD` to `origin/stable` (`--force-with-lease`) and pushes the tag

Files excluded from the release archive: `tests/` `scripts/` `.github/` `web/` `docs/` `AGENTS.md` `Makefile` `.editorconfig` `pyproject.toml` `__pycache__/` `*.pyc`

| Flag | Effect |
|------|--------|
| `--patch` / `--minor` / `--major` | Which version component to bump (default: patch) |
| `--skip-bump` | Skip the version bump (version must be pre-bumped manually) |
| `--skip-tests` | Skip the lint gates and all test tiers (nested harness calls only — the suite must still have passed before any real publish) |
| `--skip-tag` | Skip annotated release-tag creation |
| `--dry-run` | Build the release archive locally but do not push branches/tags |

## Updating the website

The landing page (`web/index.html`) is served from S3 + CloudFront at
`hyprconf.sh` — the CloudFront UA-router sends `curl`/`wget` to `install.sh` and
browsers to the page. There is no deploy tooling (the CDK app and `hyprconf
deploy` were removed); push changes manually:

```bash
aws s3 cp web/index.html    s3://hyprconf-sh/index.html    --content-type text/html
aws s3 cp web/hyprconf.webp s3://hyprconf-sh/hyprconf.webp --content-type image/webp
# refresh the installer too when install.sh changes:
aws s3 cp install/install.sh s3://hyprconf-sh/install.sh

# then invalidate the cache (distribution looked up by domain):
DIST=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?contains(Aliases.Items,'hyprconf.sh')].Id" --output text)
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*"
```
